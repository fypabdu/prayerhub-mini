from __future__ import annotations

from pathlib import Path

from prayerhub.audio import AudioPlayer, AudioRouter


class FakeRunner:
    def __init__(self, available: set[str]) -> None:
        self.available = available
        self.run_calls: list[list[str]] = []

    def which(self, name: str) -> str | None:
        return name if name in self.available else None

    def run(self, args: list[str], *, timeout: int) -> None:
        self.run_calls.append(args)


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
