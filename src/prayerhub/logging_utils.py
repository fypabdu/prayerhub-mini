from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


class LoggerFactory:
    @staticmethod
    def create(name: str, log_file: Optional[Path] = None) -> logging.Logger:
        root_logger = logging.getLogger()
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s - %(message)s"
        )

        if not root_logger.handlers:
            root_logger.setLevel(logging.INFO)
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(formatter)
            root_logger.addHandler(stream_handler)

        if log_file is not None:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            if not _has_file_handler(root_logger, log_path):
                file_handler = RotatingFileHandler(
                    log_path, maxBytes=1_000_000, backupCount=3
                )
                file_handler.setFormatter(formatter)
                root_logger.addHandler(file_handler)

        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        return logger


def _has_file_handler(logger: logging.Logger, log_path: Path) -> bool:
    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler):
            try:
                if Path(handler.baseFilename) == log_path:
                    return True
            except Exception:
                continue
    return False
