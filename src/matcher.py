"""Rule matching and rewrite-condition evaluation."""

from __future__ import annotations

import fnmatch
import logging
import re
from dataclasses import dataclass, field

from parser import (
    RedirectConfig,
    RedirectMatchRule,
    RedirectRule,
    RewriteCond,
    RewriteRule,
    Rule,
    VALID_REDIRECT_STATUSES,
    VirtualHost,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RequestContext:
    host: str
    path: str
    query: str = ""
    scheme: str = "https"
    headers: dict[str, list[str]] = field(default_factory=dict)
    method: str = "GET"

    @property
    def request_uri(self) -> str:
        return f"{self.path}?{self.query}" if self.query else self.path

    def header(self, name: str, default: str = "") -> str:
        values = self.headers.get(name.lower(), [])
        return values[0] if values else default


@dataclass(frozen=True)
class MatchResult:
    action: str
    status: int | None = None
    location: str | None = None
    uri: str | None = None
    querystring: str = ""
    rule_line: int = 0


@dataclass(frozen=True)
class _ConditionEvaluation:
    matched: bool
    last_match: re.Match[str] | None = None


def context_from_cloudfront_request(
    request: dict,
    trusted_edge_header_name: str = "",
    trusted_edge_header_value: str = "",
) -> RequestContext:
    headers = _normalize_headers(request.get("headers", {}))
    host_header = _first_header(headers, "host")
    redirect_host = _first_header(headers, "x-redirect-host")
    if _trusted_edge_headers(headers, trusted_edge_header_name, trusted_edge_header_value) and redirect_host:
        host_header = redirect_host
    host = _strip_host_port(host_header)
    scheme = _detect_scheme(headers)
    path = request.get("uri") or "/"
    query = request.get("querystring") or ""
    method = request.get("method") or "GET"
    return RequestContext(host=host, path=path, query=query, scheme=scheme, headers=headers, method=method)


def find_match(config: RedirectConfig, request: RequestContext) -> MatchResult | None:
    vhost = find_virtual_host(config, request.host)
    if vhost is None:
        logger.debug("No virtual host matched host=%s", request.host)
        return None

    for rule in vhost.rules:
        result = _match_rule(rule, request)
        if result is not None:
            logger.info("Matched %s from line %s for host=%s uri=%s", type(rule).__name__, result.rule_line, request.host, request.request_uri)
            return result

    logger.debug("No redirect rule matched host=%s uri=%s", request.host, request.request_uri)
    return None


def find_virtual_host(config: RedirectConfig, host: str) -> VirtualHost | None:
    normalized_host = _strip_host_port(host.lower().rstrip("."))
    wildcard_match: VirtualHost | None = None

    for vhost in config.virtual_hosts:
        for pattern in vhost.host_patterns:
            normalized_pattern = pattern.lower().rstrip(".")
            if normalized_pattern == "*":
                wildcard_match = wildcard_match or vhost
                continue
            if normalized_pattern.startswith("*."):
                suffix = normalized_pattern[1:]
                if normalized_host.endswith(suffix) and normalized_host != normalized_pattern[2:]:
                    return vhost
                continue
            if any(ch in normalized_pattern for ch in "*?[]"):
                if fnmatch.fnmatchcase(normalized_host, normalized_pattern):
                    return vhost
                continue
            if normalized_host == normalized_pattern:
                return vhost

    return wildcard_match


def evaluate_rewrite_conditions(
    conditions: tuple[RewriteCond, ...],
    request: RequestContext,
) -> _ConditionEvaluation:
    if not conditions:
        return _ConditionEvaluation(True, None)

    overall = True
    in_or_group = False
    group_value = False
    last_match: re.Match[str] | None = None

    for condition in conditions:
        matched, condition_match = _match_condition(condition, request)
        if condition_match is not None:
            last_match = condition_match

        if _flag_enabled(condition.flags, "or"):
            group_value = group_value or matched
            in_or_group = True
            continue

        if in_or_group:
            group_value = group_value or matched
            overall = overall and group_value
            in_or_group = False
            group_value = False
        else:
            overall = overall and matched

        if not overall:
            return _ConditionEvaluation(False, last_match)

    if in_or_group:
        overall = overall and group_value

    return _ConditionEvaluation(overall, last_match)


def _match_rule(rule: Rule, request: RequestContext) -> MatchResult | None:
    if isinstance(rule, RedirectRule):
        return _match_redirect(rule, request)
    if isinstance(rule, RedirectMatchRule):
        return _match_redirect_match(rule, request)
    if isinstance(rule, RewriteRule):
        return _match_rewrite_rule(rule, request)
    return None


def _match_redirect(rule: RedirectRule, request: RequestContext) -> MatchResult | None:
    if "*" in rule.source:
        pattern = "^" + re.escape(rule.source).replace("\\*", "(.*)") + "$"
        match = re.match(pattern, request.path)
        if not match:
            return None
        target = _expand_backrefs(rule.target, match)
    else:
        remainder = _redirect_prefix_remainder(rule.source, request.path)
        if remainder is None:
            return None
        target = rule.target + remainder if _should_append_remainder(rule.target, remainder) else rule.target

    location = _apply_query_policy(target, request.query, rule.flags)
    return MatchResult(action="redirect", status=rule.status, location=location, rule_line=rule.line_number)


def _match_redirect_match(rule: RedirectMatchRule, request: RequestContext) -> MatchResult | None:
    flags = re.IGNORECASE if _flag_enabled(rule.flags, "nc") else 0
    match = re.search(rule.pattern, request.path, flags)
    if not match:
        return None

    target = _expand_backrefs(rule.target, match)
    location = _apply_query_policy(target, request.query, rule.flags)
    return MatchResult(action="redirect", status=rule.status, location=location, rule_line=rule.line_number)


def _match_rewrite_rule(rule: RewriteRule, request: RequestContext) -> MatchResult | None:
    condition_result = evaluate_rewrite_conditions(rule.conditions, request)
    if not condition_result.matched:
        return None

    flags = re.IGNORECASE if _flag_enabled(rule.flags, "nc") else 0
    match = re.search(rule.pattern, request.path, flags)
    if not match and request.path.startswith("/"):
        match = re.search(rule.pattern, request.path[1:], flags)
    if not match:
        return None

    target = _expand_rewrite_target(rule.target, match, condition_result.last_match)
    if target == "-":
        return None

    redirect_status = _rewrite_redirect_status(rule.flags)
    if redirect_status is not None or _is_absolute_url(target):
        status = redirect_status or 302
        location = _apply_query_policy(target, request.query, rule.flags)
        return MatchResult(action="redirect", status=status, location=location, rule_line=rule.line_number)

    rewritten = _apply_query_policy(target, request.query, rule.flags)
    uri, query = _split_location(rewritten)
    if not uri.startswith("/"):
        uri = "/" + uri
    return MatchResult(action="rewrite", uri=uri, querystring=query, rule_line=rule.line_number)


def _match_condition(condition: RewriteCond, request: RequestContext) -> tuple[bool, re.Match[str] | None]:
    value = _expand_condition_test(condition.test, request)
    pattern = condition.pattern
    negated = False

    if pattern.startswith("!"):
        negated = True
        pattern = pattern[1:]

    if pattern.startswith("="):
        matched = value == pattern[1:]
        return (not matched if negated else matched), None

    if pattern.startswith("!="):
        matched = value != pattern[2:]
        return (not matched if negated else matched), None

    if pattern == "-z":
        matched = value == ""
        return (not matched if negated else matched), None

    if pattern == "-n":
        matched = value != ""
        return (not matched if negated else matched), None

    flags = re.IGNORECASE if _flag_enabled(condition.flags, "nc") else 0
    match = re.search(pattern, value, flags)
    matched = match is not None
    return (not matched if negated else matched), match


def _expand_condition_test(test: str, request: RequestContext) -> str:
    def replace(match: re.Match[str]) -> str:
        variable = match.group(1)
        return _condition_variable(variable, request)

    return re.sub(r"%\{([^}]+)\}", replace, test)


def _condition_variable(variable: str, request: RequestContext) -> str:
    name = variable.upper()

    if name == "HTTP_HOST":
        return request.host
    if name == "REQUEST_URI":
        return request.request_uri
    if name in {"REQUEST_PATH", "URI"}:
        return request.path
    if name == "QUERY_STRING":
        return request.query
    if name in {"REQUEST_SCHEME", "SCHEME"}:
        return request.scheme
    if name == "HTTPS":
        return "on" if request.scheme == "https" else "off"
    if name == "REQUEST_METHOD":
        return request.method
    if name.startswith("HTTP:"):
        header_name = name[5:].lower()
        if header_name == "host":
            return request.host
        return request.header(header_name)
    if name.startswith("HTTP_"):
        return request.header(name[5:].replace("_", "-").lower())

    logger.debug("Unsupported RewriteCond variable %s resolved to empty string", variable)
    return ""


def _redirect_prefix_remainder(source: str, path: str) -> str | None:
    if source == "/":
        return path[1:] if path.startswith("/") else path
    if path == source:
        return ""
    prefix = source.rstrip("/") + "/"
    if path.startswith(prefix):
        return path[len(source) :]
    return None


def _should_append_remainder(target: str, remainder: str) -> bool:
    if not remainder:
        return False
    return "$1" not in target and "${" not in target


def _expand_rewrite_target(
    target: str,
    rule_match: re.Match[str],
    condition_match: re.Match[str] | None,
) -> str:
    expanded = _expand_backrefs(target, rule_match, "$")
    if condition_match is not None:
        expanded = _expand_backrefs(expanded, condition_match, "%")
    return expanded


def _expand_backrefs(target: str, match: re.Match[str], prefix: str = "$") -> str:
    def numbered(re_match: re.Match[str]) -> str:
        index = int(re_match.group(1))
        try:
            return match.group(index) or ""
        except IndexError:
            return ""

    def named(re_match: re.Match[str]) -> str:
        name = re_match.group(1)
        try:
            return match.group(name) or ""
        except IndexError:
            return ""

    escaped_prefix = re.escape(prefix)
    target = re.sub(rf"{escaped_prefix}(\d+)", numbered, target)
    if prefix == "$":
        target = re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", named, target)
    return target


def _rewrite_redirect_status(flags: dict[str, str | bool]) -> int | None:
    if "r" not in flags and "redirect" not in flags:
        return None

    raw = flags.get("r", flags.get("redirect"))
    if raw is True:
        return 302

    status = int(str(raw))
    if status not in VALID_REDIRECT_STATUSES:
        raise ValueError(f"unsupported RewriteRule redirect status {status}")
    return status


def _apply_query_policy(target: str, original_query: str, flags: dict[str, str | bool]) -> str:
    base, target_query = _split_location(target)

    if _flag_enabled(flags, "qsd") or _flag_enabled(flags, "qsdiscard"):
        final_query = target_query
    elif _flag_enabled(flags, "qsa") or _flag_enabled(flags, "qsappend"):
        final_query = _join_query(target_query, original_query)
    elif _flag_enabled(flags, "qspreserve"):
        final_query = _join_query(target_query, original_query) if target_query else original_query
    elif target_query:
        final_query = target_query
    else:
        final_query = original_query

    return f"{base}?{final_query}" if final_query else base


def _split_location(location: str) -> tuple[str, str]:
    if "?" not in location:
        return location, ""
    base, query = location.split("?", 1)
    return base, query


def _join_query(first: str, second: str) -> str:
    parts = [part for part in (first, second) if part]
    return "&".join(parts)


def _flag_enabled(flags: dict[str, str | bool], *names: str) -> bool:
    return any(flags.get(name.lower()) is True for name in names)


def _is_absolute_url(target: str) -> bool:
    return target.startswith("http://") or target.startswith("https://")


def _normalize_headers(headers: dict) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    for name, values in headers.items():
        lowered = name.lower()
        normalized[lowered] = []
        for item in values or []:
            if isinstance(item, dict) and "value" in item:
                normalized[lowered].append(str(item["value"]))
            else:
                normalized[lowered].append(str(item))
    return normalized


def _first_header(headers: dict[str, list[str]], name: str, default: str = "") -> str:
    values = headers.get(name.lower())
    if not values:
        return default
    return values[0]


def _detect_scheme(headers: dict[str, list[str]]) -> str:
    for name in ("cloudfront-forwarded-proto", "x-forwarded-proto"):
        value = _first_header(headers, name).split(",", 1)[0].strip().lower()
        if value in {"http", "https"}:
            return value
    return "https"


def _strip_host_port(host: str) -> str:
    host = host.strip().lower().rstrip(".")
    if not host:
        return host
    if host.startswith("["):
        return host
    if ":" in host:
        return host.rsplit(":", 1)[0]
    return host


def _trusted_edge_headers(headers: dict[str, list[str]], name: str, expected_value: str) -> bool:
    if not name or not expected_value:
        return False
    return _first_header(headers, name) == expected_value
