"""Parser for Apache-style redirect configuration files."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


VALID_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
STATUS_ALIASES = {
    "permanent": 301,
    "temp": 302,
    "temporary": 302,
    "seeother": 303,
}


class ConfigParseError(ValueError):
    """Raised when the redirect configuration cannot be parsed safely."""

    def __init__(self, message: str, line_number: int | None = None):
        if line_number is not None:
            message = f"line {line_number}: {message}"
        super().__init__(message)
        self.line_number = line_number


@dataclass(frozen=True)
class RewriteCond:
    test: str
    pattern: str
    flags: dict[str, str | bool] = field(default_factory=dict)
    line_number: int = 0


@dataclass(frozen=True)
class RedirectRule:
    status: int
    source: str
    target: str
    flags: dict[str, str | bool] = field(default_factory=dict)
    line_number: int = 0


@dataclass(frozen=True)
class RedirectMatchRule:
    status: int
    pattern: str
    target: str
    flags: dict[str, str | bool] = field(default_factory=dict)
    line_number: int = 0


@dataclass(frozen=True)
class RewriteRule:
    pattern: str
    target: str
    flags: dict[str, str | bool] = field(default_factory=dict)
    conditions: tuple[RewriteCond, ...] = ()
    line_number: int = 0


Rule = RedirectRule | RedirectMatchRule | RewriteRule


@dataclass
class VirtualHost:
    host_patterns: list[str]
    rules: list[Rule] = field(default_factory=list)
    line_number: int = 0


@dataclass
class RedirectConfig:
    virtual_hosts: list[VirtualHost] = field(default_factory=list)

    @classmethod
    def empty(cls) -> "RedirectConfig":
        return cls([])


def parse_config(text: str) -> RedirectConfig:
    """Parse an Apache-ish redirect config into an ordered config model."""

    config = RedirectConfig()
    current_vhost: VirtualHost | None = None
    pending_conditions: list[RewriteCond] = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = _strip_comments(raw_line).strip()
        if not line:
            continue

        if line.lower().startswith("<virtualhost"):
            if current_vhost is not None:
                raise ConfigParseError("nested VirtualHost blocks are not supported", line_number)
            current_vhost = _parse_virtual_host(line, line_number)
            pending_conditions.clear()
            continue

        if line.lower() == "</virtualhost>":
            if current_vhost is None:
                raise ConfigParseError("closing VirtualHost without an open block", line_number)
            config.virtual_hosts.append(current_vhost)
            current_vhost = None
            pending_conditions.clear()
            continue

        if current_vhost is None:
            raise ConfigParseError("directives must be inside a VirtualHost block", line_number)

        tokens = _tokenize(line)
        if not tokens:
            continue

        directive = tokens[0].lower()
        args = tokens[1:]

        if directive == "serveralias":
            if not args:
                raise ConfigParseError("ServerAlias requires at least one host pattern", line_number)
            current_vhost.host_patterns.extend(_normalize_host_pattern(arg) for arg in args)
            pending_conditions.clear()
            continue

        if directive == "redirect":
            current_vhost.rules.append(_parse_redirect(args, line_number))
            pending_conditions.clear()
            continue

        if directive == "redirectmatch":
            current_vhost.rules.append(_parse_redirect_match(args, line_number))
            pending_conditions.clear()
            continue

        if directive == "rewritecond":
            pending_conditions.append(_parse_rewrite_cond(args, line_number))
            continue

        if directive == "rewriterule":
            current_vhost.rules.append(_parse_rewrite_rule(args, pending_conditions, line_number))
            pending_conditions.clear()
            continue

        raise ConfigParseError(f"unsupported directive {tokens[0]!r}", line_number)

    if current_vhost is not None:
        raise ConfigParseError("missing closing </VirtualHost>", current_vhost.line_number)

    return config


def _parse_virtual_host(line: str, line_number: int) -> VirtualHost:
    if not line.endswith(">"):
        raise ConfigParseError("VirtualHost opening tag must end with >", line_number)

    inner = line[len("<VirtualHost") : -1].strip()
    if not inner:
        raise ConfigParseError("VirtualHost requires at least one host pattern", line_number)

    patterns = [_normalize_host_pattern(token) for token in _tokenize(inner)]
    return VirtualHost(host_patterns=patterns, line_number=line_number)


def _parse_redirect(args: list[str], line_number: int) -> RedirectRule:
    if len(args) < 2:
        raise ConfigParseError("Redirect requires source and target", line_number)

    status, remaining = _extract_status(args, default=302, line_number=line_number)
    if len(remaining) < 2:
        raise ConfigParseError("Redirect requires source and target", line_number)

    source, target = remaining[0], remaining[1]
    flags = _parse_optional_flags(remaining[2:], line_number)
    return RedirectRule(status=status, source=source, target=target, flags=flags, line_number=line_number)


def _parse_redirect_match(args: list[str], line_number: int) -> RedirectMatchRule:
    if len(args) < 2:
        raise ConfigParseError("RedirectMatch requires pattern and target", line_number)

    status, remaining = _extract_status(args, default=302, line_number=line_number)
    if len(remaining) < 2:
        raise ConfigParseError("RedirectMatch requires pattern and target", line_number)

    pattern, target = remaining[0], remaining[1]
    flags = _parse_optional_flags(remaining[2:], line_number)
    return RedirectMatchRule(
        status=status,
        pattern=pattern,
        target=target,
        flags=flags,
        line_number=line_number,
    )


def _parse_rewrite_cond(args: list[str], line_number: int) -> RewriteCond:
    if len(args) < 2:
        raise ConfigParseError("RewriteCond requires test string and pattern", line_number)
    flags = _parse_optional_flags(args[2:], line_number)
    return RewriteCond(test=args[0], pattern=args[1], flags=flags, line_number=line_number)


def _parse_rewrite_rule(
    args: list[str],
    pending_conditions: Iterable[RewriteCond],
    line_number: int,
) -> RewriteRule:
    if len(args) < 2:
        raise ConfigParseError("RewriteRule requires pattern and target", line_number)
    flags = _parse_optional_flags(args[2:], line_number)
    _normalize_rewrite_redirect_flag(flags, line_number)
    return RewriteRule(
        pattern=args[0],
        target=args[1],
        flags=flags,
        conditions=tuple(pending_conditions),
        line_number=line_number,
    )


def _extract_status(
    args: list[str],
    default: int,
    line_number: int,
) -> tuple[int, list[str]]:
    first = args[0].lower()
    status: int

    if first.isdigit() or first in STATUS_ALIASES:
        status = int(first) if first.isdigit() else STATUS_ALIASES[first]
        remaining = args[1:]
    else:
        status = default
        remaining = args

    if status not in VALID_REDIRECT_STATUSES:
        raise ConfigParseError(f"unsupported redirect status {status}", line_number)

    return status, remaining


def _parse_optional_flags(args: list[str], line_number: int) -> dict[str, str | bool]:
    if not args:
        return {}
    if len(args) != 1 or not args[0].startswith("[") or not args[0].endswith("]"):
        raise ConfigParseError("unexpected trailing tokens; flags must use [FLAG,FLAG=value]", line_number)
    return parse_flags(args[0], line_number)


def parse_flags(raw_flags: str, line_number: int | None = None) -> dict[str, str | bool]:
    if not raw_flags.startswith("[") or not raw_flags.endswith("]"):
        raise ConfigParseError("flags must be enclosed in square brackets", line_number)

    flags: dict[str, str | bool] = {}
    inner = raw_flags[1:-1].strip()
    if not inner:
        return flags

    for raw_flag in inner.split(","):
        item = raw_flag.strip()
        if not item:
            continue
        if "=" in item:
            key, value = item.split("=", 1)
            flags[key.lower()] = value
        else:
            flags[item.lower()] = True

    return flags


def _normalize_rewrite_redirect_flag(flags: dict[str, str | bool], line_number: int) -> None:
    key = "r" if "r" in flags else "redirect" if "redirect" in flags else None
    if key is None:
        return

    raw = flags[key]
    if raw is True:
        flags[key] = "302"
        return

    value = str(raw).lower()
    if value in STATUS_ALIASES:
        status = STATUS_ALIASES[value]
    elif value.isdigit():
        status = int(value)
    else:
        raise ConfigParseError(f"unsupported RewriteRule redirect status {raw}", line_number)

    if status not in VALID_REDIRECT_STATUSES:
        raise ConfigParseError(f"unsupported RewriteRule redirect status {status}", line_number)

    flags[key] = str(status)


def _normalize_host_pattern(host: str) -> str:
    host = host.strip().lower().rstrip(".")
    if host in {"*", "*:*"}:
        return "*"
    if ":" in host and not host.startswith("["):
        host = host.rsplit(":", 1)[0]
    return host


def _strip_comments(line: str) -> str:
    in_quote: str | None = None
    escaped = False
    result: list[str] = []

    for char in line:
        if escaped:
            result.append(char)
            escaped = False
            continue

        if char == "\\" and in_quote:
            result.append(char)
            escaped = True
            continue

        if char in {"'", '"'}:
            if in_quote is None:
                in_quote = char
            elif in_quote == char:
                in_quote = None
            result.append(char)
            continue

        if char == "#" and in_quote is None:
            break

        result.append(char)

    return "".join(result)


def _tokenize(line: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    in_quote: str | None = None
    escaped = False

    for char in line:
        if escaped:
            current.append(char)
            escaped = False
            continue

        if char == "\\" and in_quote:
            current.append(char)
            escaped = True
            continue

        if char in {"'", '"'}:
            if in_quote is None:
                in_quote = char
                continue
            if in_quote == char:
                in_quote = None
                continue

        if char.isspace() and in_quote is None:
            if current:
                tokens.append("".join(current))
                current = []
            continue

        current.append(char)

    if in_quote is not None:
        raise ConfigParseError("unterminated quoted string")

    if current:
        tokens.append("".join(current))

    return tokens
