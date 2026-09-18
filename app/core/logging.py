import logging
import re
import sys
from typing import Any

import structlog

_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"(https://api\.telegram\.org/bot)[^/\s\"']+", re.IGNORECASE),
        r"\1<redacted>",
    ),
    (re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b"), "<redacted-telegram-token>"),
    (re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{10,}\b"), "<redacted-openai-key>"),
    (re.compile(r"\bgsk_[A-Za-z0-9_-]{10,}\b"), "<redacted-groq-key>"),
    (
        re.compile(r"(authorization:\s*bearer\s+)[^\s,;]+", re.IGNORECASE),
        r"\1<redacted>",
    ),
    (
        re.compile(
            r"(postgres(?:ql)?(?:\+asyncpg)?://[^:\s/]+:)[^@\s/]+(?=@)",
            re.IGNORECASE,
        ),
        r"\1<redacted>",
    ),
)


def redact_secrets(value: str) -> str:
    for pattern, replacement in _SECRET_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, dict):
        return {key: _redact_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    return value


def _redact_structlog_event(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    return {key: _redact_value(value) for key, value in event_dict.items()}


class _RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_secrets(super().format(record))


def configure_logging(level: str = "INFO") -> None:
    resolved_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=resolved_level,
        force=True,
    )
    for handler in logging.getLogger().handlers:
        handler.setFormatter(_RedactingFormatter("%(message)s"))

    # HTTPX logs full request URLs at INFO. Telegram authentication tokens are
    # embedded in those URLs, so request-level logs must stay disabled.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _redact_structlog_event,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(resolved_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def safe_error(error: Exception) -> str:
    """Log only exception type and message, never request/config objects."""
    return redact_secrets(f"{type(error).__name__}: {error}")
