#!/usr/bin/env python3
"""Validate Apache-style redirect config syntax and report fast-path coverage."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from compiler import compile_text
from parser import ConfigParseError
from security import SecurityPolicy, SecurityValidationError


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate redirect config syntax.")
    parser.add_argument("config", type=Path, help="Path to Apache-style redirect config")
    parser.add_argument(
        "--github-annotations",
        action="store_true",
        help="Emit GitHub Actions annotations for errors and compiler diagnostics",
    )
    parser.add_argument(
        "--summary-json",
        action="store_true",
        help="Print machine-readable compile summary JSON",
    )
    parser.add_argument(
        "--allowed-redirect-host",
        action="append",
        default=None,
        help="Allowed absolute redirect destination host. Can be repeated. Defaults to ALLOWED_REDIRECT_HOSTS CSV.",
    )
    parser.add_argument(
        "--allow-http-targets",
        action="store_true",
        help="Allow absolute http:// redirect targets. HTTPS is required by default.",
    )
    parser.add_argument(
        "--max-config-bytes",
        type=int,
        default=int(os.environ.get("MAX_REDIRECT_CONFIG_BYTES", "262144")),
        help="Maximum redirect config size in bytes.",
    )
    args = parser.parse_args()

    try:
        text = args.config.read_text()
        allowed_hosts = args.allowed_redirect_host
        if allowed_hosts is None:
            allowed_hosts = os.environ.get("ALLOWED_REDIRECT_HOSTS", "")
        policy = SecurityPolicy.from_values(
            allowed_redirect_hosts=allowed_hosts,
            require_https_redirect_targets=not args.allow_http_targets,
            max_config_bytes=args.max_config_bytes,
        )
        result = compile_text(text, policy)
    except (ConfigParseError, SecurityValidationError) as exc:
        if args.github_annotations:
            line = exc.line_number or 1
            print(f"::error file={args.config},line={line}::Invalid redirect config: {exc}")
        else:
            print(f"Invalid redirect config: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        if args.github_annotations:
            print(f"::error file={args.config}::Unable to read redirect config: {exc}")
        else:
            print(f"Unable to read redirect config: {exc}", file=sys.stderr)
        return 1

    for diagnostic in result.diagnostics:
        message = f"Rule remains on Lambda@Edge fallback: {diagnostic.reason}"
        if args.github_annotations:
            line = diagnostic.line_number or 1
            print(f"::warning file={args.config},line={line}::{message}")
        else:
            print(f"warning: line {diagnostic.line_number}: {message}", file=sys.stderr)

    summary = {
        "config": str(args.config),
        "hosts": result.host_count,
        "fast_rules": result.fast_rule_count,
        "fallback_rules": result.fallback_rule_count,
        "diagnostics": [diagnostic.__dict__ for diagnostic in result.diagnostics],
    }

    if args.summary_json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(
            "Redirect config OK: "
            f"{summary['hosts']} fast-path host(s), "
            f"{summary['fast_rules']} fast-path rule(s), "
            f"{summary['fallback_rules']} fallback rule(s)."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
