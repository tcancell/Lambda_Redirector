"""CloudFront-compatible response helpers."""

from __future__ import annotations

from http import HTTPStatus


REDIRECT_REASONS = {
    301: "Moved Permanently",
    302: "Found",
    303: "See Other",
    307: "Temporary Redirect",
    308: "Permanent Redirect",
}


def redirect_response(
    status: int,
    location: str,
    cache_seconds: int = 300,
    engine: str = "lambda-edge",
    include_diagnostic_header: bool = False,
) -> dict:
    reason = REDIRECT_REASONS.get(status, HTTPStatus(status).phrase)
    cache_control = "no-store" if cache_seconds <= 0 else f"public, max-age={cache_seconds}"
    headers = {
        "location": [{"key": "Location", "value": location}],
        "cache-control": [{"key": "Cache-Control", "value": cache_control}],
    }
    if include_diagnostic_header:
        headers["x-redirect-engine"] = [{"key": "X-Redirect-Engine", "value": engine}]
    return {
        "status": str(status),
        "statusDescription": reason,
        "headers": headers,
    }


def fallback_response(status: int = 404, body: str | None = None, include_diagnostic_header: bool = False) -> dict:
    reason = HTTPStatus(status).phrase
    response_body = body if body is not None else reason
    headers = {
        "content-type": [{"key": "Content-Type", "value": "text/plain; charset=utf-8"}],
        "cache-control": [{"key": "Cache-Control", "value": "no-store"}],
    }
    if include_diagnostic_header:
        headers["x-redirect-engine"] = [{"key": "X-Redirect-Engine", "value": "lambda-edge"}]
    return {
        "status": str(status),
        "statusDescription": reason,
        "headers": headers,
        "body": response_body,
    }
