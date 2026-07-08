"""S3-triggered compiler that syncs fast-path redirect rules to CloudFront KVS."""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import unquote_plus

import boto3

from compiler import compile_text
from security import SecurityPolicy

logger = logging.getLogger()
logger.setLevel(logging.INFO)

KVS_KEY_PREFIXES = ("h:", "meta")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    config_key = os.environ["CONFIG_KEY"]
    kvs_arn = os.environ["KVS_ARN"]
    processed: list[dict[str, Any]] = []

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        if key != config_key:
            logger.info("Ignoring S3 object s3://%s/%s; expected key %s", bucket, key, config_key)
            continue
        processed.append(_compile_and_sync(bucket, key, kvs_arn))

    return {"processed": processed}


def _compile_and_sync(bucket: str, key: str, kvs_arn: str) -> dict[str, Any]:
    s3 = boto3.client("s3")
    response = s3.get_object(Bucket=bucket, Key=key)
    body = response["Body"].read().decode("utf-8")
    policy = SecurityPolicy.from_values(
        allowed_redirect_hosts=os.environ.get("ALLOWED_REDIRECT_HOSTS", ""),
        require_https_redirect_targets=os.environ.get("REQUIRE_HTTPS_REDIRECT_TARGETS", "true").lower() == "true",
        max_config_bytes=int(os.environ.get("MAX_REDIRECT_CONFIG_BYTES", "262144")),
    )
    compile_result = compile_text(body, policy)

    kvs = boto3.client("cloudfront-keyvaluestore")
    existing_keys = _list_managed_keys(kvs, kvs_arn)
    desired_keys = set(compile_result.kvs.keys())

    puts = [{"Key": key, "Value": value} for key, value in sorted(compile_result.kvs.items())]
    deletes = [{"Key": key} for key in sorted(existing_keys - desired_keys)]
    _apply_updates(kvs, kvs_arn, puts, deletes)

    logger.info(
        "Compiled s3://%s/%s to KVS: fast_rules=%s fallback_rules=%s hosts=%s diagnostics=%s",
        bucket,
        key,
        compile_result.fast_rule_count,
        compile_result.fallback_rule_count,
        compile_result.host_count,
        [diagnostic.__dict__ for diagnostic in compile_result.diagnostics],
    )
    return {
        "bucket": bucket,
        "key": key,
        "fast_rule_count": compile_result.fast_rule_count,
        "fallback_rule_count": compile_result.fallback_rule_count,
        "host_count": compile_result.host_count,
        "diagnostics": [diagnostic.__dict__ for diagnostic in compile_result.diagnostics],
    }


def _list_managed_keys(kvs: Any, kvs_arn: str) -> set[str]:
    keys: set[str] = set()
    kwargs: dict[str, Any] = {"KvsARN": kvs_arn, "MaxResults": 50}
    while True:
        response = kvs.list_keys(**kwargs)
        for item in response.get("Items", []):
            key = item.get("Key")
            if key and (key.startswith("h:") or key == "meta"):
                keys.add(key)
        next_token = response.get("NextToken")
        if not next_token:
            return keys
        kwargs["NextToken"] = next_token


def _apply_updates(kvs: Any, kvs_arn: str, puts: list[dict[str, str]], deletes: list[dict[str, str]]) -> None:
    pending_puts = list(puts)
    pending_deletes = list(deletes)
    while pending_puts or pending_deletes:
        batch_puts = pending_puts[:50]
        remaining = 50 - len(batch_puts)
        batch_deletes = pending_deletes[:remaining]
        pending_puts = pending_puts[len(batch_puts) :]
        pending_deletes = pending_deletes[len(batch_deletes) :]

        description = kvs.describe_key_value_store(KvsARN=kvs_arn)
        etag = _etag_from_response(description)
        kwargs: dict[str, Any] = {"KvsARN": kvs_arn, "IfMatch": etag}
        if batch_puts:
            kwargs["Puts"] = batch_puts
        if batch_deletes:
            kwargs["Deletes"] = batch_deletes
        if len(kwargs) > 2:
            response = kvs.update_keys(**kwargs)
            logger.info("Updated CloudFront KVS batch: puts=%s deletes=%s response=%s", len(batch_puts), len(batch_deletes), response)


def _etag_from_response(response: dict[str, Any]) -> str:
    etag = response.get("ETag")
    if etag:
        return etag
    headers = response.get("ResponseMetadata", {}).get("HTTPHeaders", {})
    if "etag" in headers:
        return headers["etag"]
    raise RuntimeError("CloudFront KVS response did not include an ETag")
