"""
Structured JSON logging → /app/data/logs/mineru.log
Tail with: tail -f /app/data/logs/mineru.log | jq .
Or raw:    tail -f /app/data/logs/mineru.log
"""

import os
import json
import logging
import time
from logging.handlers import RotatingFileHandler

LOG_DIR = os.environ.get("LOG_DIR", "/app/data/logs")
LOG_FILE = os.path.join(LOG_DIR, "mineru.log")
os.makedirs(LOG_DIR, exist_ok=True)


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Merge any extra fields passed via logger.info("msg", extra={...})
        for key, val in record.__dict__.items():
            if key not in (
                "args", "asctime", "created", "exc_info", "exc_text", "filename",
                "funcName", "id", "levelname", "levelno", "lineno", "module",
                "msecs", "message", "msg", "name", "pathname", "process",
                "processName", "relativeCreated", "stack_info", "thread", "threadName",
            ):
                payload[key] = val
        return json.dumps(payload, default=str)


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("mineru")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    fmt = JSONFormatter()

    # Rotating file: 50MB × 5 files = 250MB max
    fh = RotatingFileHandler(LOG_FILE, maxBytes=50 * 1024 * 1024, backupCount=5)
    fh.setFormatter(fmt)
    fh.setLevel(logging.DEBUG)
    logger.addHandler(fh)

    # Console (stderr) — plain text for docker logs
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    ch.setLevel(logging.INFO)
    logger.addHandler(ch)

    return logger


log = setup_logging()
