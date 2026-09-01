"""
Logging estruturado (JSON lines) para stdout/stderr.

IMPORTANTE: nenhuma função de log neste projeto deve receber
access_token, refresh_token, client_secret, cco_password ou o
header Authorization. Os wrappers abaixo existem para forçar
esse hábito no restante do código.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any, Optional

_REDACTED = "***REDACTED***"
_SENSITIVE_KEYS = {
    "access_token",
    "refresh_token",
    "client_secret",
    "cco_password",
    "authorization",
    "password",
}


def _scrub(data: dict[str, Any]) -> dict[str, Any]:
    clean = {}
    for k, v in data.items():
        if k.lower() in _SENSITIVE_KEYS:
            clean[k] = _REDACTED
        else:
            clean[k] = v
    return clean


def configure_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("cisco_ccw_mcp")
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    return logger


logger = configure_logging()


def log_event(
    event: str,
    *,
    tool: Optional[str] = None,
    endpoint: Optional[str] = None,
    http_status: Optional[int] = None,
    duration_ms: Optional[float] = None,
    estimate_id: Optional[str] = None,
    **extra: Any,
) -> None:
    payload = {
        "ts": time.time(),
        "event": event,
        "tool": tool,
        "endpoint": endpoint,
        "http_status": http_status,
        "duration_ms": duration_ms,
        "estimate_id": estimate_id,
        **_scrub(extra),
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    logger.info(json.dumps(payload, ensure_ascii=False))
