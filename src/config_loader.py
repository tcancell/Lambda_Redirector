"""S3-backed configuration loader with safe in-memory caching."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any

from parser import ConfigParseError, RedirectConfig, parse_config
from security import SecurityPolicy, SecurityValidationError, validate_config_security, validate_config_size

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ObjectFingerprint:
    etag: str | None
    version_id: str | None
    last_modified: str | None


class S3ConfigLoader:
    """Load and cache redirect config from S3 without letting bad config take down traffic."""

    def __init__(
        self,
        bucket: str,
        key: str,
        region: str,
        check_interval_seconds: int = 30,
        s3_client: Any | None = None,
        security_policy: SecurityPolicy | None = None,
    ) -> None:
        self.bucket = bucket
        self.key = key
        self.region = region
        self.check_interval_seconds = max(0, check_interval_seconds)
        self.s3 = s3_client or self._build_s3_client(region)
        self.security_policy = security_policy or SecurityPolicy()
        self._config: RedirectConfig | None = None
        self._fingerprint: ObjectFingerprint | None = None
        self._next_check_at = 0.0

    def get_config(self) -> RedirectConfig:
        now = time.time()
        if self._config is not None and now < self._next_check_at:
            return self._config

        self._next_check_at = now + self.check_interval_seconds

        fingerprint: ObjectFingerprint | None = None
        if self._config is not None:
            try:
                fingerprint = self._head_config()
            except Exception:
                logger.exception("Unable to check redirect config s3://%s/%s", self.bucket, self.key)
                return self._config

            if fingerprint == self._fingerprint:
                return self._config

        try:
            body, loaded_fingerprint = self._get_config()
            validate_config_size(body, self.security_policy)
            parsed = parse_config(body)
            validate_config_security(parsed, self.security_policy)
        except (ConfigParseError, SecurityValidationError):
            logger.exception("Redirect config validation failed; keeping previous known-good config")
            return self._config or RedirectConfig.empty()
        except Exception:
            logger.exception("Unable to load redirect config; keeping previous known-good config")
            return self._config or RedirectConfig.empty()

        self._config = parsed
        self._fingerprint = loaded_fingerprint or fingerprint
        logger.info(
            "Loaded redirect config s3://%s/%s with %s virtual host(s)",
            self.bucket,
            self.key,
            len(parsed.virtual_hosts),
        )
        return parsed

    def _head_config(self) -> ObjectFingerprint:
        response = self.s3.head_object(Bucket=self.bucket, Key=self.key)
        return _fingerprint_from_response(response)

    def _get_config(self) -> tuple[str, ObjectFingerprint]:
        response = self.s3.get_object(Bucket=self.bucket, Key=self.key)
        data = response["Body"].read()
        return data.decode("utf-8"), _fingerprint_from_response(response)

    @staticmethod
    def _build_s3_client(region: str) -> Any:
        import boto3
        from botocore.config import Config

        return boto3.client(
            "s3",
            region_name=region,
            config=Config(
                connect_timeout=2,
                read_timeout=2,
                retries={"max_attempts": 2, "mode": "standard"},
            ),
        )


def _fingerprint_from_response(response: dict) -> ObjectFingerprint:
    last_modified = response.get("LastModified")
    if hasattr(last_modified, "isoformat"):
        last_modified_value = last_modified.isoformat()
    elif isinstance(last_modified, str):
        try:
            last_modified_value = parsedate_to_datetime(last_modified).isoformat()
        except (TypeError, ValueError):
            last_modified_value = last_modified
    else:
        last_modified_value = None

    return ObjectFingerprint(
        etag=response.get("ETag"),
        version_id=response.get("VersionId"),
        last_modified=last_modified_value,
    )
