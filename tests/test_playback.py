from __future__ import annotations

from pathlib import Path

import pytest

from prayerhub.config import AdhanAudio, AudioConfig, AudioVolumes, NotificationAudio, QuranScheduleItem
from prayerhub.playback import PlaybackHandler


class FakeBluetooth:
    def __init__(self, connected: bool) -> None:
        self.connected = connected
        self.calls = 0

    def ensure_connected_once(self) -> bool:
        self.calls += 1
        return self.connected


class FakePlayer:
    def __init__(self, should_raise: bool = False) -> None:
        self.should_raise = should_raise
        self.calls: list[tuple[Path, int, int | None]] = []

    def play(self, path: Path, *, volume_percent: int, timeout_seconds: int | None = 30) -> bool:
        if self.should_raise:
            raise RuntimeError("boom")
        self.calls.append((path, volume_percent, timeout_seconds))
        return True


class FakeTimeoutPolicy:
    def __init__(self, timeout_seconds: int | None) -> None:
        self.timeout_seconds = timeout_seconds
        self.calls: list[Path] = []

    def resolve(self, path: Path) -> int | None:
        self.calls.append(path)
        return self.timeout_seconds


def _audio_config() -> AudioConfig:
    return AudioConfig(
        test_audio="data/audio/test_beep.mp3",
        connected_tone="data/audio/connected.mp3",
        background_keepalive_enabled=False,
        background_keepalive_path="data/audio/keepalive_low_freq.mp3",
        background_keepalive_volume_percent=1,
        background_keepalive_loop=True,
        background_keepalive_nice=10,
        background_keepalive_volume_cycle_enabled=False,
        background_keepalive_volume_cycle_min_percent=1,
        background_keepalive_volume_cycle_max_percent=10,
        background_keepalive_volume_cycle_step_seconds=1.0,
        adhan=AdhanAudio(
            fajr="data/audio/adhan_fajr.mp3",
            dhuhr="data/audio/adhan_dhuhr.mp3",
            asr="data/audio/adhan_asr.mp3",
            maghrib="data/audio/adhan_maghrib.mp3",
            isha="data/audio/adhan_isha.mp3",
        ),
        quran_schedule=(QuranScheduleItem(time="06:30", file="data/audio/quran_morning.mp3"),),
        notifications=NotificationAudio(
            sunrise="data/audio/sunrise.mp3",
            sunset="data/audio/sunset.mp3",
            midnight="data/audio/midnight.mp3",
            tahajjud="data/audio/tahajjud.mp3",
        ),
        volumes=AudioVolumes(
            master_percent=60,
            adhan_percent=85,
            fajr_adhan_percent=60,
            quran_percent=55,
            notification_percent=50,
            test_percent=70,
        ),
        playback_timeout_seconds=300,
        playback_timeout_strategy="fixed",
        playback_timeout_buffer_seconds=5,
    )


def test_handler_skips_when_bluetooth_unavailable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    bluetooth = FakeBluetooth(connected=False)
    player = FakePlayer()

    handler = PlaybackHandler(
        bluetooth=bluetooth,
        player=player,
        audio=_audio_config(),
    )

    assert handler.handle_event("fajr") is False
    assert bluetooth.calls == 1
    assert player.calls == []


def test_handler_plays_fajr_with_fajr_volume(tmp_path: Path, monkeypatch) -> None:
    audio_dir = tmp_path / "data" / "audio"
    audio_dir.mkdir(parents=True)
    (audio_dir / "adhan_fajr.mp3").write_bytes(b"beep")
    monkeypatch.chdir(tmp_path)

    bluetooth = FakeBluetooth(connected=True)
    player = FakePlayer()
    handler = PlaybackHandler(
        bluetooth=bluetooth,
        player=player,
        audio=_audio_config(),
    )

    assert handler.handle_event("fajr") is True
    assert player.calls == [(audio_dir / "adhan_fajr.mp3", 60, 300)]


def test_handler_plays_notification_with_notification_volume(tmp_path: Path, monkeypatch) -> None:
    audio_dir = tmp_path / "data" / "audio"
    audio_dir.mkdir(parents=True)
    (audio_dir / "sunrise.mp3").write_bytes(b"beep")
    monkeypatch.chdir(tmp_path)

    bluetooth = FakeBluetooth(connected=True)
    player = FakePlayer()
    handler = PlaybackHandler(
        bluetooth=bluetooth,
        player=player,
        audio=_audio_config(),
    )

    assert handler.handle_event("sunrise") is True
    assert player.calls == [(audio_dir / "sunrise.mp3", 50, 300)]


def test_handler_plays_quran_when_matching_time(tmp_path: Path, monkeypatch) -> None:
    audio_dir = tmp_path / "data" / "audio"
    audio_dir.mkdir(parents=True)
    (audio_dir / "quran_morning.mp3").write_bytes(b"beep")
    monkeypatch.chdir(tmp_path)

    bluetooth = FakeBluetooth(connected=True)
    player = FakePlayer()
    handler = PlaybackHandler(
        bluetooth=bluetooth,
        player=player,
        audio=_audio_config(),
    )

    assert handler.handle_event("quran@06:30") is True
    assert player.calls == [(audio_dir / "quran_morning.mp3", 55, 300)]


def test_handler_plays_test_audio_with_test_volume(tmp_path: Path, monkeypatch) -> None:
    audio_dir = tmp_path / "data" / "audio"
    audio_dir.mkdir(parents=True)
    (audio_dir / "test_beep.mp3").write_bytes(b"beep")
    monkeypatch.chdir(tmp_path)

    bluetooth = FakeBluetooth(connected=True)
    player = FakePlayer()
    handler = PlaybackHandler(
        bluetooth=bluetooth,
        player=player,
        audio=_audio_config(),
    )

    assert handler.handle_event("test_audio") is True
    assert player.calls == [(audio_dir / "test_beep.mp3", 70, 300)]


def test_handler_catches_player_errors(tmp_path: Path, monkeypatch) -> None:
    audio_dir = tmp_path / "data" / "audio"
    audio_dir.mkdir(parents=True)
    (audio_dir / "adhan_fajr.mp3").write_bytes(b"beep")
    monkeypatch.chdir(tmp_path)

    bluetooth = FakeBluetooth(connected=True)
    player = FakePlayer(should_raise=True)
    handler = PlaybackHandler(
        bluetooth=bluetooth,
        player=player,
        audio=_audio_config(),
    )

    assert handler.handle_event("fajr") is False


def test_handler_disables_timeout_when_configured(tmp_path: Path, monkeypatch) -> None:
    audio_dir = tmp_path / "data" / "audio"
    audio_dir.mkdir(parents=True)
    (audio_dir / "adhan_fajr.mp3").write_bytes(b"beep")
    monkeypatch.chdir(tmp_path)

    bluetooth = FakeBluetooth(connected=True)
    player = FakePlayer()
    audio = _audio_config()
    audio = audio.__class__(**{**audio.__dict__, "playback_timeout_seconds": 0})
    handler = PlaybackHandler(
        bluetooth=bluetooth,
        player=player,
        audio=audio,
    )

    assert handler.handle_event("fajr") is True
    assert player.calls == [(audio_dir / "adhan_fajr.mp3", 60, None)]


def test_handler_uses_timeout_policy_when_provided(tmp_path: Path, monkeypatch) -> None:
    audio_dir = tmp_path / "data" / "audio"
    audio_dir.mkdir(parents=True)
    (audio_dir / "adhan_fajr.mp3").write_bytes(b"beep")
    monkeypatch.chdir(tmp_path)

    bluetooth = FakeBluetooth(connected=True)
    player = FakePlayer()
    policy = FakeTimeoutPolicy(42)
    audio = _audio_config()
    audio = audio.__class__(**{**audio.__dict__, "playback_timeout_strategy": "auto"})
    handler = PlaybackHandler(
        bluetooth=bluetooth,
        player=player,
        audio=audio,
        timeout_policy=policy,
    )

    assert handler.handle_event("fajr") is True
    assert policy.calls == [audio_dir / "adhan_fajr.mp3"]
    assert player.calls == [(audio_dir / "adhan_fajr.mp3", 60, 42)]


def test_handler_logs_playback_details(tmp_path: Path, monkeypatch, caplog) -> None:
    audio_dir = tmp_path / "data" / "audio"
    audio_dir.mkdir(parents=True)
    (audio_dir / "adhan_fajr.mp3").write_bytes(b"beep")
    monkeypatch.chdir(tmp_path)

    bluetooth = FakeBluetooth(connected=True)
    player = FakePlayer()
    handler = PlaybackHandler(
        bluetooth=bluetooth,
        player=player,
        audio=_audio_config(),
    )

    with caplog.at_level("INFO"):
        assert handler.handle_event("fajr") is True

    assert "Playback event=fajr" in caplog.text
    assert "adhan_fajr.mp3" in caplog.text
