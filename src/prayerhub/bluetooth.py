from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from typing import Callable, Iterable
import time

from prayerhub.audio import AudioRouter
from prayerhub.command_runner import CommandRunner


MAC_PATTERN = re.compile(r"^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$")


@dataclass
class BluetoothManager:
    runner: CommandRunner
    audio_router: AudioRouter
    device_mac: str
    ensure_default_sink: bool
    backoff_seconds: Iterable[int] = field(default_factory=lambda: [1, 2, 5])
    connect_timeout_seconds: int = 10
    info_timeout_seconds: int = 5
    sleep: Callable[[float], None] = time.sleep

    def __post_init__(self) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)
        if not MAC_PATTERN.match(self.device_mac):
            raise ValueError(f"Invalid Bluetooth MAC address: {self.device_mac}")

    def ensure_connected(self) -> bool:
        if self._is_connected():
            return True

        # We retry with a small backoff because bluetoothctl can be flaky on boot.
        for delay in self.backoff_seconds:
            if self._connect_once():
                if self.ensure_default_sink:
                    self.audio_router.ensure_default_sink()
                return True
            self.sleep(delay)

        return False

    def _connect_once(self) -> bool:
        result = self.runner.run(
            ["bluetoothctl", "connect", self.device_mac],
            timeout=self.connect_timeout_seconds,
        )
        if result.returncode != 0:
            self._logger.warning(
                "Bluetooth connect failed for %s: %s",
                self.device_mac,
                result.stderr.strip(),
            )
            return False
        return self._is_connected()

    def _is_connected(self) -> bool:
        result = self.runner.run(
            ["bluetoothctl", "info", self.device_mac],
            timeout=self.info_timeout_seconds,
        )
        if result.returncode != 0:
            return False
        for line in result.stdout.splitlines():
            if line.strip().lower().startswith("connected:"):
                return "yes" in line.lower()
        return False
