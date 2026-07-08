"""Compile Apache-style redirect config into CloudFront Function fast-path data."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from parser import RedirectConfig, RedirectMatchRule, RedirectRule, RewriteCond, RewriteRule, Rule, parse_config
from security import SecurityPolicy, validate_config_security, validate_config_size

FASTPATH_VERSION = 1
KVS_VALUE_LIMIT_BYTES = 1000
SUPPORTED_CONDITION_VARIABLES = {
    "HTTP_HOST",
    "REQUEST_URI",
    "REQUEST_PATH",
    "URI",
    "QUERY_STRING",
    "REQUEST_SCHEME",
    "SCHEME",
    "HTTPS",
    "REQUEST_METHOD",
}
SUPPORTED_RULE_FLAGS = {
    "qsd",
    "qsdiscard",
    "qsa",
    "qsappend",
    "qspreserve",
    "nc",
    "l",
    "r",
    "redirect",
}
SUPPORTED_COND_FLAGS = {"nc", "or"}
UNSAFE_JS_REGEX_MARKERS = ("(?P<", "(?P=", "(?(", "(?<", "(?<=", "(?<!")


@dataclass
class CompileDiagnostic:
    line_number: int
    host_patterns: list[str]
    reason: str


@dataclass
class CompileResult:
    kvs: dict[str, str]
    diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    fast_rule_count: int = 0
    fallback_rule_count: int = 0
    host_count: int = 0

    def to_external_result(self) -> dict[str, str]:
        return {
            "kvs": json.dumps(self.kvs, sort_keys=True),
            "fast_rule_count": str(self.fast_rule_count),
            "fallback_rule_count": str(self.fallback_rule_count),
            "host_count": str(self.host_count),
            "diagnostics": json.dumps([diagnostic.__dict__ for diagnostic in self.diagnostics], sort_keys=True),
        }


def compile_text(text: str, security_policy: SecurityPolicy | None = None) -> CompileResult:
    if security_policy is not None:
        validate_config_size(text, security_policy)
    config = parse_config(text)
    if security_policy is not None:
        validate_config_security(config, security_policy)
    return compile_config(config)


def compile_config(config: RedirectConfig) -> CompileResult:
    result = CompileResult(kvs={})
    hosts: dict[str, list[dict[str, Any]]] = {}

    for vhost in config.virtual_hosts:
        exact_hosts = [host for host in vhost.host_patterns if _is_exact_host(host)]
        if not exact_hosts:
            result.fallback_rule_count += len(vhost.rules)
            result.diagnostics.append(
                CompileDiagnostic(vhost.line_number, vhost.host_patterns, "fast path supports exact VirtualHost/ServerAlias names only")
            )
            continue

        fast_rules: list[dict[str, Any]] = []
        blocked = False
        for rule in vhost.rules:
            if blocked:
                result.fallback_rule_count += 1
                continue

            compiled, reason = _compile_rule(rule)
            if compiled is None:
                blocked = True
                result.fallback_rule_count += 1
                result.diagnostics.append(CompileDiagnostic(getattr(rule, "line_number", 0), vhost.host_patterns, reason or "unsupported rule"))
                continue

            fast_rules.append(compiled)
            result.fast_rule_count += 1

        if not fast_rules:
            continue

        for host in exact_hosts:
            hosts.setdefault(host.lower(), []).extend(fast_rules)

    for host, rules in sorted(hosts.items()):
        value = _compact_json(rules)
        if len(value.encode("utf-8")) > KVS_VALUE_LIMIT_BYTES:
            result.fallback_rule_count += len(rules)
            result.fast_rule_count -= len(rules)
            result.diagnostics.append(
                CompileDiagnostic(0, [host], f"compiled host rules exceed CloudFront KeyValueStore {KVS_VALUE_LIMIT_BYTES} byte value limit")
            )
            continue
        result.kvs[f"h:{host}"] = value

    result.host_count = len([key for key in result.kvs if key.startswith("h:")])
    result.kvs["meta"] = _compact_json(
        {
            "version": FASTPATH_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "host_count": result.host_count,
            "fast_rule_count": result.fast_rule_count,
            "fallback_rule_count": result.fallback_rule_count,
        }
    )
    return result


def _compile_rule(rule: Rule) -> tuple[dict[str, Any] | None, str | None]:
    if isinstance(rule, RedirectRule):
        return _compile_redirect(rule)
    if isinstance(rule, RedirectMatchRule):
        return _compile_redirect_match(rule)
    if isinstance(rule, RewriteRule):
        return _compile_rewrite_rule(rule)
    return None, "unknown rule type"


def _compile_redirect(rule: RedirectRule) -> tuple[dict[str, Any] | None, str | None]:
    flags, reason = _compile_flags(rule.flags, SUPPORTED_RULE_FLAGS)
    if reason:
        return None, reason
    if not _target_is_supported(rule.target):
        return None, "target contains unsupported named backreference syntax"
    return {
        "t": "redirect",
        "s": rule.status,
        "src": rule.source,
        "dst": rule.target,
        "f": flags,
        "line": rule.line_number,
    }, None


def _compile_redirect_match(rule: RedirectMatchRule) -> tuple[dict[str, Any] | None, str | None]:
    flags, reason = _compile_flags(rule.flags, SUPPORTED_RULE_FLAGS)
    if reason:
        return None, reason
    if not _regex_is_supported(rule.pattern):
        return None, "regex uses syntax that is risky in CloudFront Function JavaScript"
    if not _target_is_supported(rule.target):
        return None, "target contains unsupported named backreference syntax"
    return {
        "t": "match",
        "s": rule.status,
        "p": rule.pattern,
        "dst": rule.target,
        "f": flags,
        "line": rule.line_number,
    }, None


def _compile_rewrite_rule(rule: RewriteRule) -> tuple[dict[str, Any] | None, str | None]:
    flags, reason = _compile_flags(rule.flags, SUPPORTED_RULE_FLAGS)
    if reason:
        return None, reason
    status = _rewrite_status(flags, rule.target)
    if status is None:
        return None, "internal rewrites stay on Lambda@Edge fallback"
    if not _regex_is_supported(rule.pattern):
        return None, "RewriteRule regex uses syntax that is risky in CloudFront Function JavaScript"
    if not _target_is_supported(rule.target):
        return None, "target contains unsupported named backreference syntax"

    conditions: list[dict[str, Any]] = []
    for condition in rule.conditions:
        compiled_condition, condition_reason = _compile_condition(condition)
        if compiled_condition is None:
            return None, condition_reason
        conditions.append(compiled_condition)

    return {
        "t": "rewrite",
        "s": status,
        "p": rule.pattern,
        "dst": rule.target,
        "f": flags,
        "c": conditions,
        "line": rule.line_number,
    }, None


def _compile_condition(condition: RewriteCond) -> tuple[dict[str, Any] | None, str | None]:
    flags, reason = _compile_flags(condition.flags, SUPPORTED_COND_FLAGS)
    if reason:
        return None, reason
    variables = re.findall(r"%\{([^}]+)\}", condition.test)
    for variable in variables:
        normalized = variable.upper()
        if normalized.startswith("HTTP:") or normalized.startswith("HTTP_"):
            continue
        if normalized not in SUPPORTED_CONDITION_VARIABLES:
            return None, f"RewriteCond variable {variable!r} is not fast-path supported"
    pattern = condition.pattern[1:] if condition.pattern.startswith("!") else condition.pattern
    if not pattern.startswith(("=", "!=", "-z", "-n")) and not _regex_is_supported(pattern):
        return None, "RewriteCond regex uses syntax that is risky in CloudFront Function JavaScript"
    return {"test": condition.test, "p": condition.pattern, "f": flags, "line": condition.line_number}, None


def _compile_flags(flags: dict[str, str | bool], supported: set[str]) -> tuple[dict[str, Any], str | None]:
    compiled: dict[str, Any] = {}
    for key, value in flags.items():
        normalized = key.lower()
        if normalized not in supported:
            return {}, f"flag [{key}] is not fast-path supported"
        if value is True:
            compiled[normalized] = True
        else:
            compiled[normalized] = str(value)
    return compiled, None


def _rewrite_status(flags: dict[str, Any], target: str) -> int | None:
    raw = flags.get("r", flags.get("redirect"))
    if raw is True:
        return 302
    if raw is not None:
        return int(raw)
    if target.startswith("http://") or target.startswith("https://"):
        return 302
    return None


def _regex_is_supported(pattern: str) -> bool:
    return not any(marker in pattern for marker in UNSAFE_JS_REGEX_MARKERS)


def _target_is_supported(target: str) -> bool:
    return "${" not in target


def _is_exact_host(host: str) -> bool:
    return host != "*" and not any(ch in host for ch in "*?[]")


def _compact_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)
