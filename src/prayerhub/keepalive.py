from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Optional

from apscheduler.triggers.interval import IntervalTrigger


@dataclass
class KeepAliveService:
    scheduler: object
    player: object
    bluetooth: Optional[object]
    audio_file: str
    volume_percent: int
    interval_minutes: int
    job_id: str = "keepalive_audio"

    def __post_init__(self) -> None:
        self._logger = logging.getLogger("prayerhub")

    def schedule(self) -> None:
        self.scheduler.add_job(
            self.run_once,
            trigger=IntervalTrigger(minutes=self.interval_minutes),
            id=self.job_id,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        self._logger.info(
            "Scheduled keepalive every %s minutes (job=%s)",
            self.interval_minutes,
            self.job_id,
        )

    def run_once(self) -> None:
        if getattr(self.player, "is_playing")():
            self._logger.info("Keepalive skipped; audio already playing")
            return

        if self.bluetooth is not None and not self.bluetooth.ensure_connected_once():
            self._logger.warning("Keepalive skipped; bluetooth not connected")
            return

        path = self._resolve(self.audio_file)
        if not path.exists():
            self._logger.warning("Keepalive audio missing: %s", path)
            return

        self._logger.info("Keepalive playback: %s", path)
        self.player.play(path, volume_percent=self.volume_percent)

    def _resolve(self, path_str: str) -> Path:
        path = Path(path_str)
        if path.is_absolute():
            return path
        return Path.cwd() / path
