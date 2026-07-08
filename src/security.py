"""Security validation for redirect configuration."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from parser import RedirectConfig, RedirectMatchRule, RedirectRule, RewriteCond, RewriteRule, Rule

MAX_VIRTUAL_HOSTS = 500
MAX_RULES = 5000
MAX_RULES_PER_HOST = 1000
MAX_CONDITIONS_PER_RULE = 25
MAX_PATTERN_LENGTH = 512
MAX_TARGET_LENGTH = 2048
MAX_HOST_PATTERN_LENGTH = 253

_REGEX_RISK_PATTERNS = (
    re.compile(r"\((?:[^()\\]|\\.){0,200}[+*](?:[^()\\]|\\.){0,200}\)\s*[+*{]"),
    re.compile(r"\((?:[^()\\]|\\.){0,200}\{\d+(?:,\d*)?\}(?:[^()\\]|\\.){0,200}\)\s*[+*{]"),
    re.compile(r"\.\*\.\*"),
)


class SecurityValidationError(ValueError):
    """Raised when a syntactically valid config violates production safety policy."""

    def __init__(self, message: str, line_number: int | None = None):
        if line_number is not None:
            message = f"line {line_number}: {message}"
        super().__init__(message)
        self.line_number = line_number


@dataclass(frozen=True)
class SecurityPolicy:
    allowed_redirect_hosts: tuple[str, ...] = ()
    require_https_redirect_targets: bool = True
    max_config_bytes: int = 262144
    max_virtual_hosts: int = MAX_VIRTUAL_HOSTS
    max_rules: int = MAX_RULES
    max_rules_per_host: int = MAX_RULES_PER_HOST
    max_conditions_per_rule: int = MAX_CONDITIONS_PER_RULE
    max_pattern_length: int = MAX_PATTERN_LENGTH
    max_target_length: int = MAX_TARGET_LENGTH

    @classmethod
    def from_values(
        cls,
        allowed_redirect_hosts: str | list[str] | tuple[str, ...] | None = None,
        require_https_redirect_targets: bool = True,
        max_config_bytes: int = 262144,
    ) -> "SecurityPolicy":
        return cls(
            allowed_redirect_hosts=_normalize_allowed_hosts(allowed_redirect_hosts),
            require_https_redirect_targets=bool(require_https_redirect_targets),
            max_config_bytes=int(max_config_bytes),
        )


def validate_config_size(text_or_bytes: str | bytes, policy: SecurityPolicy) -> None:
    size = len(text_or_bytes.encode("utf-8") if isinstance(text_or_bytes, str) else text_or_bytes)
    if size > policy.max_config_bytes:
        raise SecurityValidationError(f"redirect config is {size} bytes, exceeding limit {policy.max_config_bytes}")


def validate_config_security(config: RedirectConfig, policy: SecurityPolicy) -> None:
    if len(config.virtual_hosts) > policy.max_virtual_hosts:
        raise SecurityValidationError(f"config has too many VirtualHost blocks; limit is {policy.max_virtual_hosts}")

    total_rules = 0
    for vhost in config.virtual_hosts:
        for host_pattern in vhost.host_patterns:
            _validate_host_pattern(host_pattern, vhost.line_number)

        if len(vhost.rules) > policy.max_rules_per_host:
            raise SecurityValidationError(
                f"VirtualHost has too many rules; limit is {policy.max_rules_per_host}",
                vhost.line_number,
            )

        total_rules += len(vhost.rules)
        if total_rules > policy.max_rules:
            raise SecurityValidationError(f"config has too many rules; limit is {policy.max_rules}", vhost.line_number)

        for rule in vhost.rules:
            _validate_rule(rule, policy)


def _validate_rule(rule: Rule, policy: SecurityPolicy) -> None:
    if isinstance(rule, RedirectRule):
        _validate_target(rule.target, policy, rule.line_number)
        return

    if isinstance(rule, RedirectMatchRule):
        _validate_regex(rule.pattern, policy, rule.line_number)
        _validate_target(rule.target, policy, rule.line_number)
        return

    if isinstance(rule, RewriteRule):
        _validate_regex(rule.pattern, policy, rule.line_number)
        _validate_target(rule.target, policy, rule.line_number, allow_dash=True)
        if len(rule.conditions) > policy.max_conditions_per_rule:
            raise SecurityValidationError(
                f"RewriteRule has too many RewriteCond entries; limit is {policy.max_conditions_per_rule}",
                rule.line_number,
            )
        for condition in rule.conditions:
            _validate_condition(condition, policy)


def _validate_condition(condition: RewriteCond, policy: SecurityPolicy) -> None:
    pattern = condition.pattern[1:] if condition.pattern.startswith("!") else condition.pattern
    if pattern.startswith(("=", "!=", "-z", "-n")):
        return
    _validate_regex(pattern, policy, condition.line_number)


def _validate_regex(pattern: str, policy: SecurityPolicy, line_number: int) -> None:
    if len(pattern) > policy.max_pattern_length:
        raise SecurityValidationError(f"regex exceeds {policy.max_pattern_length} characters", line_number)

    try:
        re.compile(pattern)
    except re.error as exc:
        raise SecurityValidationError(f"invalid regex: {exc}", line_number) from exc

    for risky in _REGEX_RISK_PATTERNS:
        if risky.search(pattern):
            raise SecurityValidationError("regex has nested or ambiguous repetition that can cause excessive backtracking", line_number)


def _validate_target(target: str, policy: SecurityPolicy, line_number: int, allow_dash: bool = False) -> None:
    if allow_dash and target == "-":
        return

    if len(target) > policy.max_target_length:
        raise SecurityValidationError(f"redirect target exceeds {policy.max_target_length} characters", line_number)

    if any(ord(char) < 32 or ord(char) == 127 for char in target):
        raise SecurityValidationError("redirect target contains control characters", line_number)

    if target.startswith("//"):
        raise SecurityValidationError("protocol-relative redirect targets are not allowed", line_number)

    split = urlsplit(target)
    if not split.scheme:
        return

    scheme = split.scheme.lower()
    if scheme not in {"http", "https"}:
        raise SecurityValidationError(f"redirect target scheme {split.scheme!r} is not allowed", line_number)

    if policy.require_https_redirect_targets and scheme != "https":
        raise SecurityValidationError("absolute redirect targets must use HTTPS", line_number)

    host = (split.hostname or "").lower().rstrip(".")
    if not host:
        raise SecurityValidationError("absolute redirect target must include a hostname", line_number)

    if "$" in split.netloc or "%" in split.netloc:
        raise SecurityValidationError("dynamic redirect hostnames are not allowed", line_number)

    if policy.allowed_redirect_hosts and not _host_allowed(host, policy.allowed_redirect_hosts):
        raise SecurityValidationError(f"redirect target host {host!r} is not in the allowed host list", line_number)


def _validate_host_pattern(host_pattern: str, line_number: int) -> None:
    if len(host_pattern) > MAX_HOST_PATTERN_LENGTH:
        raise SecurityValidationError("VirtualHost host pattern is too long", line_number)
    if any(ord(char) < 32 or ord(char) == 127 for char in host_pattern):
        raise SecurityValidationError("VirtualHost host pattern contains control characters", line_number)


def _host_allowed(host: str, allowed_hosts: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(host, pattern) for pattern in allowed_hosts)


def _normalize_allowed_hosts(value: str | list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        items = value.split(",")
    else:
        items = list(value)
    normalized = []
    for item in items:
        host = str(item).strip().lower().rstrip(".")
        if host:
            normalized.append(host)
    return tuple(normalized)
