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


def redirect_response(status: int, location: str, cache_seconds: int = 300) -> dict:
    reason = REDIRECT_REASONS.get(status, HTTPStatus(status).phrase)
    cache_control = "no-store" if cache_seconds <= 0 else f"public, max-age={cache_seconds}"
    return {
        "status": str(status),
        "statusDescription": reason,
        "headers": {
            "location": [{"key": "Location", "value": location}],
            "cache-control": [{"key": "Cache-Control", "value": cache_control}],
        },
    }


def fallback_response(status: int = 404, body: str | None = None) -> dict:
    reason = HTTPStatus(status).phrase
    response_body = body if body is not None else reason
    return {
        "status": str(status),
        "statusDescription": reason,
        "headers": {
            "content-type": [{"key": "Content-Type", "value": "text/plain; charset=utf-8"}],
            "cache-control": [{"key": "Cache-Control", "value": "no-store"}],
        },
        "body": response_body,
    }
