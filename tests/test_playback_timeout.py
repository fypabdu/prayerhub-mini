from __future__ import annotations

from pathlib import Path

from prayerhub.playback_timeout import PlaybackTimeoutPolicy


class FakeProbe:
    def __init__(self, duration) -> None:
        self.duration = duration
        self.calls: list[Path] = []

    def duration_seconds(self, path: Path):
        self.calls.append(path)
        return self.duration


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
