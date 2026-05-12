"""
Structured logging for the simfea_api sidecar.

Pattern borrowed from @sim/logger in sim-main:
- createLogger(name) factory
- Colored output in development, JSON in production
- withMetadata() for child loggers with merged context
"""

import json
import os
import sys
import time
from typing import Any, Mapping


def _is_dev() -> bool:
    env = os.environ.get("SIMFEA_ENV", "").lower()
    if env in ("production", "prod"):
        return False
    if env in ("development", "dev"):
        return True
    return True


class Logger:
    def __init__(self, module: str, metadata: Mapping[str, Any] | None = None):
        self._module = module
        self._metadata = dict(metadata) if metadata else {}
        self._dev = _is_dev()

    def with_metadata(self, **extra: Any) -> "Logger":
        merged = {**self._metadata, **extra}
        child = Logger(self._module, merged)
        child._dev = self._dev
        return child

    def _write(self, level: str, message: str, **fields: Any) -> None:
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
        merged = {**self._metadata, **fields}

        if self._dev:
            colors = {"DEBUG": "\x1b[36m", "INFO": "\x1b[32m", "WARN": "\x1b[33m", "ERROR": "\x1b[31m"}
            reset = "\x1b[0m"
            meta_str = " ".join(f"{k}={v}" for k, v in merged.items()) if merged else ""
            prefix = f"[{self._module}]" if not merged else f"[{self._module}] [{meta_str}]"
            color = colors.get(level, "")
            print(f"{color}{timestamp} {level:5s} {prefix}{reset} {message}", flush=True)
        else:
            record = {
                "ts": timestamp,
                "level": level,
                "module": self._module,
                "msg": message,
                **merged,
            }
            print(json.dumps(record, ensure_ascii=False), flush=True)

    def debug(self, message: str, **fields: Any) -> None:
        self._write("DEBUG", message, **fields)

    def info(self, message: str, **fields: Any) -> None:
        self._write("INFO", message, **fields)

    def warn(self, message: str, **fields: Any) -> None:
        self._write("WARN", message, **fields)

    def error(self, message: str, **fields: Any) -> None:
        self._write("ERROR", message, **fields)


def create_logger(module: str, **metadata: Any) -> Logger:
    return Logger(module, metadata)
