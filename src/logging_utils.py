import json
import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone

"""
Module for logging utilities
"""

def setup_logger(name="email_pipeline"):
    """
    Set up logging mechanism for the email pipeline
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        level = "INFO"
    logger.setLevel(level)
    logger.propagate = False
    return logger


def log_event(logger, event, **fields):
    """
    Log name and time of event
    """
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payload = {
        "event": event,
        "ts": ts,
    }
    payload.update(fields)
    logger.info(json.dumps(payload, sort_keys=True))


@contextmanager
def log_timing(logger, event, **fields):
    start = time.perf_counter()
    status = "ok"
    error = None
    try:
        yield
    except Exception as exc:
        status = "error"
        error = str(exc)
        raise
    finally:
        duration_ms = int((time.perf_counter() - start) * 1000)
        payload = {"status": status, "duration_ms": duration_ms}
        if error:
            payload["error"] = error
        payload.update(fields)
        log_event(logger, event, **payload)
