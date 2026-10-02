"""Structured JSON logging with secret redaction.

- Structured JSON with stable field names.
- Sanitizes fields that could contain credentials/tokens.
- Never emits raw access tokens, client secrets, or JWTs.
- UTC timestamps in RFC 3339.
- Logs go to stderr (stdout is reserved for the stdio MCP transport).
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

SENSITIVE_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "authorization",
        "access_token",
        "refresh_token",
        "token",
        "client_id",
        "client_secret",
        "password",
        "secret",
        "api_key",
        "cookie",
        "set-cookie",
        "sl_client_id",
        "sl_client_secret",
    }
)

REDACTED = "***REDACTED***"

_TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"Basic\s+[A-Za-z0-9+/=]+", re.IGNORECASE),
    re.compile(r"\beyJ[A-Za-z0-9._\-]+"),  # JWT-shaped
)


def _redact_value(key: str, value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _redact_value(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(key, v) for v in value]
    if key.lower() in SENSITIVE_FIELD_NAMES and value is not None:
        return REDACTED
    if isinstance(value, str):
        scrubbed = value
        for pattern in _TOKEN_PATTERNS:
            scrubbed = pattern.sub(REDACTED, scrubbed)
        return scrubbed
    return value


def redact(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``payload`` with sensitive fields/values masked."""
    return {k: _redact_value(k, v) for k, v in payload.items()}


class JsonFormatter(logging.Formatter):
    """Format log records as JSON with redacted extras."""

    _STD_FIELDS = frozenset(
        {
            "args", "asctime", "created", "exc_info", "exc_text", "filename",
            "funcName", "levelno", "levelname", "lineno", "message", "module",
            "msecs", "msg", "name", "pathname", "process", "processName",
            "relativeCreated", "stack_info", "thread", "threadName", "taskName",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in payload or key.startswith("_") or key in self._STD_FIELDS:
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
            payload["exc_msg"] = str(record.exc_info[1]) if record.exc_info[1] else None
        return json.dumps(redact(payload), separators=(",", ":"), default=str)


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON handler on the root logger; logs go to stderr."""
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel("DEBUG" if level.upper() == "DEBUG" else "WARNING")
