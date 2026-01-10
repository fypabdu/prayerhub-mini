from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from prayerhub.background_keepalive import BackgroundKeepAliveService


@dataclass
class FakeProcess:
    terminated: bool = False

    def terminate(self) -> None:
        self.terminated = True

    def poll(self) -> int | None:
        return 0 if self.terminated else None

    def wait(self, timeout: int | None = None) -> int:
        self.terminated = True
        return 0


class FakeRunner:
    def __init__(self, available: set[str]) -> None:
        self.available = available
        self.spawn_calls: list[list[str]] = []

    def which(self, name: str) -> str | None:
        return name if name in self.available else None

    def spawn(self, args: list[str]) -> FakeProcess:
        self.spawn_calls.append(args)
        return FakeProcess()


class FakeBluetooth:
    def __init__(self, connected: bool) -> None:
        self.connected = connected
        self.calls = 0

    def ensure_connected_once(self) -> bool:
        self.calls += 1
        return self.connected


def test_background_keepalive_starts_when_idle(tmp_path: Path) -> None:
    audio_file = tmp_path / "keepalive.mp3"
    audio_file.write_bytes(b"beep")
    runner = FakeRunner({"mpg123"})
    bluetooth = FakeBluetooth(connected=True)
    service = BackgroundKeepAliveService(
        runner=runner,
        bluetooth=bluetooth,
        audio_file=str(audio_file),
        volume_percent=1,
        loop=True,
        nice_level=10,
    )

    service.resume_if_idle()

    assert runner.spawn_calls
    assert service.is_running() is True
    assert bluetooth.calls == 1


def test_background_keepalive_skips_when_bluetooth_down(tmp_path: Path) -> None:
    audio_file = tmp_path / "keepalive.mp3"
    audio_file.write_bytes(b"beep")
    runner = FakeRunner({"mpg123"})
    bluetooth = FakeBluetooth(connected=False)
    service = BackgroundKeepAliveService(
        runner=runner,
        bluetooth=bluetooth,
        audio_file=str(audio_file),
        volume_percent=1,
        loop=True,
        nice_level=None,
    )

    service.resume_if_idle()

    assert runner.spawn_calls == []
    assert service.is_running() is False


def test_background_keepalive_pause_stops_process(tmp_path: Path) -> None:
    audio_file = tmp_path / "keepalive.mp3"
    audio_file.write_bytes(b"beep")
    runner = FakeRunner({"mpg123"})
    bluetooth = FakeBluetooth(connected=True)
    service = BackgroundKeepAliveService(
        runner=runner,
        bluetooth=bluetooth,
        audio_file=str(audio_file),
        volume_percent=1,
        loop=True,
        nice_level=None,
    )

    service.resume_if_idle()
    service.pause_for_foreground()

    assert service.is_running() is False


def test_background_keepalive_resume_skips_when_running(tmp_path: Path) -> None:
    audio_file = tmp_path / "keepalive.mp3"
    audio_file.write_bytes(b"beep")
    runner = FakeRunner({"mpg123"})
    bluetooth = FakeBluetooth(connected=True)
    service = BackgroundKeepAliveService(
        runner=runner,
        bluetooth=bluetooth,
        audio_file=str(audio_file),
        volume_percent=1,
        loop=True,
        nice_level=None,
    )

    service.resume_if_idle()
    service.resume_if_idle()

    assert len(runner.spawn_calls) == 1
