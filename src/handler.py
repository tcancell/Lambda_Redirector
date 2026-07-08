"""Lambda@Edge entry point for CloudFront origin-request events."""

from __future__ import annotations

import logging
from typing import Any

import settings
from config_loader import S3ConfigLoader
from matcher import context_from_cloudfront_request, find_match
from response import fallback_response, redirect_response
from security import SecurityPolicy

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_loader: S3ConfigLoader | None = None


def handler(event: dict[str, Any], context: Any) -> dict:
    try:
        return _handle_request(event)
    except Exception:
        logger.exception("Unhandled redirect engine error; returning fallback response")
        try:
            request = event["Records"][0]["cf"]["request"]
            return _fallback_or_origin(request)
        except Exception:
            return fallback_response(500, "Redirect engine error.", settings.ENABLE_DIAGNOSTIC_HEADERS)


def _handle_request(event: dict[str, Any]) -> dict:
    request = event["Records"][0]["cf"]["request"]

    if not settings.CONFIG_BUCKET:
        logger.error("CONFIG_BUCKET is empty. Check Terraform packaging settings.")
        return _fallback_or_origin(request)

    config = _get_loader().get_config()
    request_context = context_from_cloudfront_request(
        request,
        trusted_edge_header_name=settings.TRUSTED_EDGE_HEADER_NAME,
        trusted_edge_header_value=settings.TRUSTED_EDGE_HEADER_VALUE,
    )
    match = find_match(config, request_context)

    if match is None:
        return _fallback_or_origin(request)

    if match.action == "redirect" and match.status and match.location:
        return redirect_response(
            match.status,
            match.location,
            settings.REDIRECT_CACHE_SECONDS,
            include_diagnostic_header=settings.ENABLE_DIAGNOSTIC_HEADERS,
        )

    if match.action == "rewrite" and match.uri is not None:
        request["uri"] = match.uri
        request["querystring"] = match.querystring
        return request

    logger.warning("Rule on line %s produced an unusable result; using fallback", match.rule_line)
    return _fallback_or_origin(request)


def _get_loader() -> S3ConfigLoader:
    global _loader
    if _loader is None:
        _loader = S3ConfigLoader(
            bucket=settings.CONFIG_BUCKET,
            key=settings.CONFIG_KEY,
            region=settings.CONFIG_REGION,
            check_interval_seconds=settings.CONFIG_CHECK_INTERVAL_SECONDS,
            security_policy=SecurityPolicy.from_values(
                allowed_redirect_hosts=settings.ALLOWED_REDIRECT_HOSTS,
                require_https_redirect_targets=settings.REQUIRE_HTTPS_REDIRECT_TARGETS,
                max_config_bytes=settings.MAX_REDIRECT_CONFIG_BYTES,
            ),
        )
    return _loader


def _fallback_or_origin(request: dict) -> dict:
    if settings.FALLBACK_BEHAVIOR == "pass_through":
        return request
    return fallback_response(settings.FALLBACK_STATUS_CODE, settings.FALLBACK_BODY, settings.ENABLE_DIAGNOSTIC_HEADERS)
