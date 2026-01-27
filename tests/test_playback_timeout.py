from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from prayerhub.playback_timeout import PlaybackTimeoutPolicy
from prayerhub.playback_timeout import FfprobeDurationProbe


class FakeProbe:
    def __init__(self, duration) -> None:
        self.duration = duration
        self.calls: list[Path] = []

    def duration_seconds(self, path: Path):
        self.calls.append(path)
        return self.duration


class TimeoutRunner:
    def which(self, _name: str) -> str | None:
        return "/usr/bin/ffprobe"

    def run(self, _args, *, timeout):
        raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=timeout)


class CountingRunner:
    def __init__(self, stdout: str = "12.5\n") -> None:
        self.calls = 0
        self.stdout = stdout

    def which(self, _name: str) -> str | None:
        return "/usr/bin/ffprobe"

    def run(self, args, *, timeout):
        self.calls += 1
        return subprocess.CompletedProcess(args, 0, self.stdout, "")


def test_auto_timeout_uses_duration_with_buffer() -> None:
    probe = FakeProbe(12.2)
    policy = PlaybackTimeoutPolicy(
        strategy="auto",
        fallback_seconds=300,
        buffer_seconds=5,
        duration_probe=probe,
    )

    timeout = policy.resolve(Path("adhan.mp3"))

    assert timeout == 18
    assert probe.calls == [Path("adhan.mp3")]


def test_auto_timeout_falls_back_when_duration_missing() -> None:
    probe = FakeProbe(None)
    policy = PlaybackTimeoutPolicy(
        strategy="auto",
        fallback_seconds=120,
        buffer_seconds=5,
        duration_probe=probe,
    )

    timeout = policy.resolve(Path("adhan.mp3"))

    assert timeout == 120


def test_auto_timeout_can_disable_when_fallback_is_zero() -> None:
    probe = FakeProbe(None)
    policy = PlaybackTimeoutPolicy(
        strategy="auto",
        fallback_seconds=0,
        buffer_seconds=5,
        duration_probe=probe,
    )

    timeout = policy.resolve(Path("adhan.mp3"))

    assert timeout is None


def test_fixed_timeout_uses_fallback() -> None:
    probe = FakeProbe(12.2)
    policy = PlaybackTimeoutPolicy(
        strategy="fixed",
        fallback_seconds=90,
        buffer_seconds=5,
        duration_probe=probe,
    )

    timeout = policy.resolve(Path("adhan.mp3"))

    assert timeout == 90


def test_ffprobe_timeout_returns_none(tmp_path: Path) -> None:
    probe = FfprobeDurationProbe(runner=TimeoutRunner())

    duration = probe.duration_seconds(tmp_path / "audio.mp3")

    assert duration is None


def test_ffprobe_duration_cached_until_file_changes(tmp_path: Path) -> None:
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"beep")
    runner = CountingRunner(stdout="10.0\n")
    probe = FfprobeDurationProbe(runner=runner)

    first = probe.duration_seconds(audio_path)
    second = probe.duration_seconds(audio_path)

    assert first == 10.0
    assert second == 10.0
    assert runner.calls == 1

    audio_path.write_bytes(b"beep-beep")
    third = probe.duration_seconds(audio_path)

    assert third == 10.0
    assert runner.calls == 2


def test_ffprobe_logs_cache_activity(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"beep")
    runner = CountingRunner(stdout="10.0\n")
    probe = FfprobeDurationProbe(runner=runner)

    with caplog.at_level("INFO"):
        probe.duration_seconds(audio_path)
        probe.duration_seconds(audio_path)

    assert "ffprobe cache miss" in caplog.text
    assert "ffprobe cache hit" in caplog.text


def test_timeout_policy_logs_resolution(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"beep")
    probe = FakeProbe(12.2)
    policy = PlaybackTimeoutPolicy(
        strategy="auto",
        fallback_seconds=120,
        buffer_seconds=5,
        duration_probe=probe,
    )

    with caplog.at_level("INFO"):
        timeout = policy.resolve(audio_path)

    assert timeout == 18
    assert "Playback timeout resolved" in caplog.text
