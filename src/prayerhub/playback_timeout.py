from __future__ import annotations

from dataclasses import dataclass
import logging
import math
from pathlib import Path
import subprocess
from typing import Optional, Protocol

from prayerhub.command_runner import CommandRunner


class AudioDurationProbe(Protocol):
    def duration_seconds(self, path: Path) -> Optional[float]:
        ...


@dataclass
class FfprobeDurationProbe:
    runner: CommandRunner
    timeout_seconds: int = 5

    def __post_init__(self) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)

    def duration_seconds(self, path: Path) -> Optional[float]:
        if not self.runner.which("ffprobe"):
            return None
        try:
            result = self.runner.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            self._logger.warning("ffprobe timed out for %s", path)
            return None
        if result.returncode != 0:
            self._logger.warning(
                "ffprobe failed for %s: %s",
                path,
                result.stderr.strip(),
            )
            return None
        raw = result.stdout.strip()
        try:
            duration = float(raw)
        except ValueError:
            self._logger.warning("Invalid ffprobe duration for %s: %s", path, raw)
            return None
        if duration <= 0:
            return None
        return duration


@dataclass
class PlaybackTimeoutPolicy:
    strategy: str
    fallback_seconds: int
    buffer_seconds: int = 0
    duration_probe: Optional[AudioDurationProbe] = None

    def __post_init__(self) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)

    def resolve(self, path: Path) -> Optional[int]:
        fallback = None if self.fallback_seconds == 0 else self.fallback_seconds
        if self.strategy != "auto":
            return fallback

        if self.duration_probe is None:
            self._logger.warning(
                "Auto playback timeout requested but no duration probe available; using fallback=%s",
                fallback,
            )
            return fallback

        duration = self.duration_probe.duration_seconds(path)
        if duration is None:
            self._logger.warning(
                "Auto playback timeout unavailable for %s; using fallback=%s",
                path,
                fallback,
            )
            return fallback

        timeout = math.ceil(duration + self.buffer_seconds)
        if timeout <= 0:
            return fallback
        return timeout
