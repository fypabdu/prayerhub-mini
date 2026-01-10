from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Optional

from prayerhub.command_runner import CommandRunner, ProcessHandle


@dataclass
class BackgroundKeepAliveService:
    runner: CommandRunner
    bluetooth: Optional[object]
    audio_file: str
    volume_percent: int
    loop: bool
    nice_level: Optional[int] = None

    def __post_init__(self) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)
        self._process: Optional[ProcessHandle] = None

    def on_foreground_start(self) -> None:
        self.pause_for_foreground()

    def on_foreground_end(self) -> None:
        self.resume_if_idle()

    def resume_if_idle(self) -> None:
        if self.is_running():
            return
        if self.bluetooth is not None and not self.bluetooth.ensure_connected_once():
            self._logger.warning("Background keepalive skipped; bluetooth not connected")
            return

        path = self._resolve(self.audio_file)
        if not path.exists():
            self._logger.warning("Background keepalive audio missing: %s", path)
            return

        command = self._build_command(path)
        if not command:
            self._logger.error("Background keepalive unavailable; no audio backend")
            return
        self._logger.info("Background keepalive start: %s", path)
        self._process = self.runner.spawn(command)

    def pause_for_foreground(self) -> None:
        if not self.is_running():
            return
        self._logger.info("Background keepalive stopping for foreground audio")
        self._stop_process()

    def is_running(self) -> bool:
        if self._process is None:
            return False
        return self._process.poll() is None

    def _stop_process(self) -> None:
        if self._process is None:
            return
        try:
            self._process.terminate()
            try:
                self._process.wait(timeout=0.2)
            except Exception:
                pass
        except Exception as exc:
            self._logger.warning("Background keepalive stop failed: %s", exc)
        finally:
            self._process = None

    def _build_command(self, path: Path) -> Optional[list[str]]:
        base: list[str]
        if self.runner.which("mpg123"):
            base = ["mpg123", "-q"]
            if self.loop:
                base += ["--loop", "-1"]
            base += ["-f", str(self._scale_for_mpg123())]
            base.append(str(path))
        elif self.runner.which("ffplay"):
            base = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error"]
            if self.loop:
                base += ["-stream_loop", "-1"]
            base += ["-volume", str(self._clamp_volume())]
            base.append(str(path))
        else:
            return None

        if self.nice_level is not None and self.runner.which("nice"):
            return ["nice", "-n", str(self.nice_level)] + base
        return base

    def _scale_for_mpg123(self) -> int:
        percent = self._clamp_volume()
        return int(32768 * (percent / 100))

    def _clamp_volume(self) -> int:
        return max(0, min(self.volume_percent, 100))

    def _resolve(self, path_str: str) -> Path:
        path = Path(path_str)
        if path.is_absolute():
            return path
        return Path.cwd() / path
