from __future__ import annotations

from pathlib import Path

from dataclasses import dataclass

from prayerhub.audio import AudioPlayer, AudioRouter


@dataclass
class FakeResult:
    returncode: int = 0
    stderr: str = ""


class FakeRunner:
    def __init__(self, available: set[str]) -> None:
        self.available = available
        self.run_calls: list[list[str]] = []

    def which(self, name: str) -> str | None:
        return name if name in self.available else None

    def run(self, args: list[str], *, timeout: int | None) -> FakeResult:
        self.run_calls.append(args)
        return FakeResult()


@dataclass
class FakeMonitor:
    started: int = 0
    ended: int = 0

    def on_foreground_start(self) -> None:
        self.started += 1

    def on_foreground_end(self) -> None:
        self.ended += 1


def test_audio_router_selects_wpctl_then_pactl() -> None:
    runner = FakeRunner({"wpctl", "pactl"})
    router = AudioRouter(runner)
    assert router.backend == "pipewire"

    runner = FakeRunner({"pactl"})
    router = AudioRouter(runner)
    assert router.backend == "pulseaudio"


def test_audio_player_refuses_missing_file(tmp_path: Path) -> None:
    runner = FakeRunner({"mpg123"})
    router = AudioRouter(runner)
    player = AudioPlayer(runner, router)

    assert not player.play(tmp_path / "missing.mp3", volume_percent=50, timeout_seconds=1)
    assert runner.run_calls == []


def test_audio_player_enforces_single_playback(tmp_path: Path) -> None:
    audio_file = tmp_path / "test.mp3"
    audio_file.write_bytes(b"beep")

    runner = FakeRunner({"mpg123"})
    router = AudioRouter(runner)
    player = AudioPlayer(runner, router)

    player._lock.acquire()
    try:
        assert not player.play(audio_file, volume_percent=50, timeout_seconds=1)
    finally:
        player._lock.release()


def test_audio_player_falls_back_to_ffplay(tmp_path: Path) -> None:
    audio_file = tmp_path / "test.mp3"
    audio_file.write_bytes(b"beep")

    runner = FakeRunner({"ffplay"})
    router = AudioRouter(runner)
    player = AudioPlayer(runner, router)

    assert player.play(audio_file, volume_percent=50, timeout_seconds=1)
    assert runner.run_calls
    assert runner.run_calls[0][0] == "ffplay"


def test_audio_player_errors_when_no_backend(tmp_path: Path, caplog) -> None:
    audio_file = tmp_path / "test.mp3"
    audio_file.write_bytes(b"beep")

    runner = FakeRunner(set())
    router = AudioRouter(runner)
    player = AudioPlayer(runner, router)

    with caplog.at_level("ERROR"):
        assert not player.play(audio_file, volume_percent=50, timeout_seconds=1)
    assert "mpg123" in caplog.text and "ffplay" in caplog.text


def test_audio_player_notifies_monitor(tmp_path: Path) -> None:
    audio_file = tmp_path / "test.mp3"
    audio_file.write_bytes(b"beep")

    runner = FakeRunner({"mpg123"})
    router = AudioRouter(runner)
    monitor = FakeMonitor()
    player = AudioPlayer(runner, router, monitor=monitor)

    assert player.play(audio_file, volume_percent=50, timeout_seconds=1)
    assert monitor.started == 1
    assert monitor.ended == 1
