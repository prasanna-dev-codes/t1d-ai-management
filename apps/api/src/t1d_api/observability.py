"""Allowlisted operational logs; no URLs, request bodies, tokens or exception text."""

import json
import logging
from datetime import UTC, datetime


class SafeJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, str | int | float] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "component": "api",
            "version": "0.1.0",
            "event": record.msg
            if record.msg in {"request_completed", "audit_unavailable"}
            else "request_completed",
        }
        for key in ("correlation_id", "status_code", "duration_ms"):
            value = getattr(record, key, None)
            if isinstance(value, (str, int, float)):
                payload[key] = value
        return json.dumps(payload, separators=(",", ":"))


def request_logger() -> logging.Logger:
    logger = logging.getLogger("t1d_api.requests")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(SafeJsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
