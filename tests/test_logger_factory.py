from __future__ import annotations

import logging
from pathlib import Path

from prayerhub.logging_utils import LoggerFactory


def test_logger_factory_writes_to_rotating_file(tmp_path: Path) -> None:
    log_path = tmp_path / "app.log"
    logger = LoggerFactory.create("test_logger", log_file=log_path)
    logger.info("hello log")

    for handler in logging.getLogger().handlers:
        handler.flush()
        handler.close()

    assert log_path.exists()
    assert "hello log" in log_path.read_text(encoding="utf-8")
