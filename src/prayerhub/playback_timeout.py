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
        self._cache: dict[Path, tuple[tuple[int, int], float]] = {}

    def _stat_key(self, path: Path) -> Optional[tuple[int, int]]:
        try:
            stat = path.stat()
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    def duration_seconds(self, path: Path) -> Optional[float]:
        self._logger.info("ffprobe requested for %s", path)
        if not self.runner.which("ffprobe"):
            self._logger.warning("ffprobe unavailable; skipping %s", path)
            return None
        stat_key = self._stat_key(path)
        if stat_key is not None:
            cached = self._cache.get(path)
            if cached and cached[0] == stat_key:
                self._logger.info("ffprobe cache hit for %s", path)
                return cached[1]
            self._logger.info("ffprobe cache miss for %s", path)
        else:
            self._logger.warning("ffprobe cache disabled; stat failed for %s", path)
        try:
            self._logger.info(
                "ffprobe running for %s (timeout=%ss)", path, self.timeout_seconds
            )
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
            self._logger.warning("ffprobe returned non-positive duration for %s", path)
            return None
        self._logger.info("ffprobe duration for %s = %ss", path, duration)
        stat_key = stat_key or self._stat_key(path)
        if stat_key is not None:
            self._cache[path] = (stat_key, duration)
            self._logger.info("ffprobe cached duration for %s", path)
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
            self._logger.info(
                "Playback timeout resolved for %s using fixed strategy: %s",
                path,
                fallback,
            )
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
        self._logger.info(
            "Playback timeout resolved for %s using auto strategy: %s (duration=%s buffer=%s)",
            path,
            timeout,
            duration,
            self.buffer_seconds,
        )
        return timeout
