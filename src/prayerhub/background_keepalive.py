from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from threading import Event, Thread
from typing import Callable, Optional
import time

from prayerhub.command_runner import CommandRunner, ProcessHandle


@dataclass
class BackgroundKeepAliveService:
    runner: CommandRunner
    bluetooth: Optional[object]
    audio_file: str
    volume_percent: int
    loop: bool
    nice_level: Optional[int] = None
    volume_cycle_enabled: bool = False
    volume_cycle_min_percent: int = 1
    volume_cycle_max_percent: int = 10
    volume_cycle_step_seconds: float = 1.0
    sleep: Callable[[float], None] = time.sleep

    def __post_init__(self) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)
        self._process: Optional[ProcessHandle] = None
        self._modulator_thread: Optional[Thread] = None
        self._modulator_stop = Event()

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

        command = self._build_command(path, self._initial_volume())
        if not command:
            self._logger.error("Background keepalive unavailable; no audio backend")
            return
        self._logger.info("Background keepalive start: %s", path)
        self._process = self.runner.spawn(command)
        if self.volume_cycle_enabled:
            self._start_modulator()

    def pause_for_foreground(self) -> None:
        if not self.is_running():
            return
        self._logger.info("Background keepalive stopping for foreground audio")
        self._stop_modulator()
        self._stop_process()

    def is_running(self) -> bool:
        if self._process is None:
            return False
        return self._process.poll() is None

    def is_modulating(self) -> bool:
        return bool(self._modulator_thread and self._modulator_thread.is_alive())

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

    def _start_modulator(self) -> None:
        if self._modulator_thread and self._modulator_thread.is_alive():
            return
        self._modulator_stop.clear()
        self._modulator_thread = Thread(target=self._modulate_loop, daemon=True)
        self._modulator_thread.start()

    def _stop_modulator(self) -> None:
        if not self._modulator_thread:
            return
        self._modulator_stop.set()
        self._modulator_thread.join(timeout=0.2)
        self._modulator_thread = None

    def _modulate_loop(self) -> None:
        volume = self._initial_volume()
        direction = 1
        while not self._modulator_stop.is_set():
            self.sleep(self.volume_cycle_step_seconds)
            if self._modulator_stop.is_set():
                break
            volume += direction
            if volume >= self.volume_cycle_max_percent:
                volume = self.volume_cycle_max_percent
                direction = -1
            elif volume <= self.volume_cycle_min_percent:
                volume = self.volume_cycle_min_percent
                direction = 1
            if not self.is_running():
                break
            self._restart_with_volume(volume)

    def _restart_with_volume(self, volume_percent: int) -> None:
        path = self._resolve(self.audio_file)
        command = self._build_command(path, volume_percent)
        if not command:
            return
        self._stop_process()
        self._process = self.runner.spawn(command)

    def _build_command(self, path: Path, volume_percent: int) -> Optional[list[str]]:
        base: list[str]
        if self.runner.which("mpg123"):
            base = ["mpg123", "-q"]
            if self.loop:
                base += ["--loop", "-1"]
            base += ["-f", str(self._scale_for_mpg123(volume_percent))]
            base.append(str(path))
        elif self.runner.which("ffplay"):
            base = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error"]
            if self.loop:
                base += ["-stream_loop", "-1"]
            base += ["-volume", str(self._clamp_volume(volume_percent))]
            base.append(str(path))
        else:
            return None

        if self.nice_level is not None and self.runner.which("nice"):
            return ["nice", "-n", str(self.nice_level)] + base
        return base

    def _scale_for_mpg123(self, volume_percent: int) -> int:
        percent = self._clamp_volume(volume_percent)
        return int(32768 * (percent / 100))

    def _clamp_volume(self, volume_percent: int) -> int:
        return max(0, min(volume_percent, 100))

    def _initial_volume(self) -> int:
        if self.volume_cycle_enabled:
            return self.volume_cycle_min_percent
        return self.volume_percent

    def _resolve(self, path_str: str) -> Path:
        path = Path(path_str)
        if path.is_absolute():
            return path
        return Path.cwd() / path
