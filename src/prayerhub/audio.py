from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from threading import Lock
from typing import Optional

from prayerhub.command_runner import CommandRunner


@dataclass
class AudioRouter:
    runner: CommandRunner

    def __post_init__(self) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)
        self._backend = self._detect_backend()

    @property
    def backend(self) -> Optional[str]:
        return self._backend

    def set_master_volume(self, percent: int, *, timeout_seconds: int = 3) -> None:
        if self._backend == "pipewire":
            volume = max(0, min(percent, 100)) / 100
            self.runner.run(
                ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", str(volume)],
                timeout=timeout_seconds,
            )
            return
        if self._backend == "pulseaudio":
            self.runner.run(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"],
                timeout=timeout_seconds,
            )
            return

        # No backend detected, so we can't set volume in a predictable way.
        self._logger.warning("No audio backend available for volume control")

    def _detect_backend(self) -> Optional[str]:
        # Prefer PipeWire when present because it is the default on Bookworm.
        if self.runner.which("wpctl"):
            return "pipewire"
        if self.runner.which("pactl"):
            return "pulseaudio"
        return None


class AudioPlayer:
    def __init__(self, runner: CommandRunner, router: AudioRouter) -> None:
        self._runner = runner
        self._router = router
        self._lock = Lock()
        self._logger = logging.getLogger(self.__class__.__name__)

    def play(self, path: Path, *, volume_percent: int, timeout_seconds: int = 30) -> bool:
        if not path.exists():
            # Fail fast so callers can fall back or alert the operator.
            self._logger.warning("Audio file missing: %s", path)
            return False

        if not self._lock.acquire(blocking=False):
            # Avoid overlapping playback to prevent mixer conflicts.
            self._logger.warning("Audio playback already in progress")
            return False

        try:
            self._router.set_master_volume(volume_percent)
            if not self._runner.which("mpg123"):
                # mpg123 is the preferred backend; warn so the device can be fixed.
                self._logger.error("mpg123 is not installed or not on PATH")
                return False

            result = self._runner.run(
                ["mpg123", "-q", str(path)],
                timeout=timeout_seconds,
            )
            if result.returncode != 0:
                self._logger.error(
                    "Audio playback failed: %s", result.stderr.strip()
                )
                return False
            return True
        except Exception as exc:
            # Never let playback errors bubble to scheduler threads.
            self._logger.error("Audio playback raised: %s", exc)
            return False
        finally:
            self._lock.release()
