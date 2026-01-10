from __future__ import annotations

import os
from pathlib import Path

from prayerhub.app import _config_summary, main
from prayerhub.config import ConfigLoader


def _write_yaml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _base_config(test_audio_path: str) -> str:
    return f"""
location:
  city: "colombo"
  madhab: "shafi"
  timezone: "Asia/Colombo"

api:
  base_url: "http://example.com"
  timeout_seconds: 8
  max_retries: 4
  prefetch_days: 7

audio:
  test_audio: "{test_audio_path}"
  connected_tone: "data/audio/connected.mp3"
  background_keepalive_enabled: false
  background_keepalive_path: "data/audio/keepalive_low_freq.mp3"
  background_keepalive_volume_percent: 1
  background_keepalive_loop: true
  background_keepalive_nice: 10
  playback_timeout_seconds: 300
  playback_timeout_strategy: "fixed"
  playback_timeout_buffer_seconds: 5
  adhan:
    fajr: "data/audio/adhan_fajr.mp3"
    dhuhr: "data/audio/adhan_dhuhr.mp3"
    asr: "data/audio/adhan_asr.mp3"
    maghrib: "data/audio/adhan_maghrib.mp3"
    isha: "data/audio/adhan_isha.mp3"
  quran_schedule:
    - time: "06:30"
      file: "data/audio/quran_morning.mp3"
  notifications:
    sunrise: "data/audio/sunrise.mp3"
    sunset: "data/audio/sunset.mp3"
    midnight: "data/audio/midnight.mp3"
    tahajjud: "data/audio/tahajjud.mp3"
  volumes:
    master_percent: 60
    adhan_percent: 85
    fajr_adhan_percent: 60
    quran_percent: 55
    notification_percent: 50
    test_percent: 70

bluetooth:
  device_mac: "AA:BB:CC:DD:EE:FF"
  ensure_default_sink: true

control_panel:
  enabled: false
  host: "0.0.0.0"
  port: 8080
  auth:
    username: "admin"
    password_hash: "pbkdf2:sha256:..."
  test_scheduler:
    max_pending_tests: 10
    max_minutes_ahead: 1440

logging:
  file_path: "logs/prayerhub.log"
"""


def _seed_audio_files(root: Path) -> None:
    audio_dir = root / "data" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    for name in [
        "connected.mp3",
        "keepalive_low_freq.mp3",
        "adhan_fajr.mp3",
        "adhan_dhuhr.mp3",
        "adhan_asr.mp3",
        "adhan_maghrib.mp3",
        "adhan_isha.mp3",
        "quran_morning.mp3",
        "sunrise.mp3",
        "sunset.mp3",
        "midnight.mp3",
        "tahajjud.mp3",
    ]:
        (audio_dir / name).write_bytes(b"beep")


def test_app_respects_prayerhub_config_dir(tmp_path: Path, monkeypatch) -> None:
    test_audio = tmp_path / "test_beep.mp3"
    test_audio.write_bytes(b"beep")
    _seed_audio_files(tmp_path)
    _write_yaml(tmp_path / "config.yml", _base_config("test_beep.mp3"))

    monkeypatch.setenv("PRAYERHUB_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("PRAYERHUB_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.chdir(tmp_path)

    exit_code = main(["--dry-run"])

    assert exit_code == 0


def test_app_uses_explicit_config_path(tmp_path: Path, monkeypatch) -> None:
    test_audio = tmp_path / "test_beep.mp3"
    test_audio.write_bytes(b"beep")
    _seed_audio_files(tmp_path)
    config_path = tmp_path / "custom.yml"
    _write_yaml(config_path, _base_config("test_beep.mp3"))

    monkeypatch.setenv("PRAYERHUB_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.chdir(tmp_path)

    exit_code = main(["--config", str(config_path), "--dry-run"])

    assert exit_code == 0


def test_scheduler_starts_with_control_panel_enabled(tmp_path: Path, monkeypatch) -> None:
    test_audio = tmp_path / "test_beep.mp3"
    test_audio.write_bytes(b"beep")
    _seed_audio_files(tmp_path)
    config_path = tmp_path / "config.yml"
    config_text = _base_config("test_beep.mp3").replace(
        "control_panel:\n  enabled: false",
        "control_panel:\n  enabled: true",
    )
    _write_yaml(config_path, config_text)

    monkeypatch.setenv("PRAYERHUB_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.chdir(tmp_path)

    started = {"value": False}

    class FakeScheduler:
        def __init__(self) -> None:
            self.running = False

        def start(self, paused: bool = False) -> None:
            self.running = True
            started["value"] = True

        def add_job(self, *args, **kwargs):
            return None

        def get_jobs(self):
            return []

    class FakeServer:
        def __init__(self) -> None:
            self.app = self
            self.host = "0.0.0.0"
            self.port = 8080

        def run(self, host: str, port: int) -> None:
            return None

    monkeypatch.setenv("PRAYERHUB_SECRET_KEY", "test")

    class FakeApiClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def get_range(self, *, madhab: str, city: str, start, end):
            return {
                "results": [
                    {
                        "date": start.isoformat(),
                        "madhab": madhab,
                        "city": city,
                        "times": {"fajr": "05:00", "dhuhr": "12:00"},
                    }
                ]
            }

    monkeypatch.setattr("prayerhub.app.PrayerApiClient", FakeApiClient)
    monkeypatch.setattr(
        "apscheduler.schedulers.background.BackgroundScheduler", FakeScheduler
    )
    monkeypatch.setattr("prayerhub.control_panel.ControlPanelServer", lambda **_: FakeServer())

    exit_code = main(["--config", str(config_path)])

    assert exit_code == 0
    assert started["value"] is True


def test_app_exits_cleanly_on_config_error(tmp_path: Path, monkeypatch) -> None:
    _write_yaml(tmp_path / "config.yml", _base_config("missing.mp3"))
    _seed_audio_files(tmp_path)

    monkeypatch.setenv("PRAYERHUB_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("PRAYERHUB_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.chdir(tmp_path)

    exit_code = main(["--dry-run"])

    assert exit_code != 0


def test_config_summary_redacts_password_hash(tmp_path: Path, monkeypatch) -> None:
    test_audio = tmp_path / "test_beep.mp3"
    test_audio.write_bytes(b"beep")
    _seed_audio_files(tmp_path)
    _write_yaml(tmp_path / "config.yml", _base_config("test_beep.mp3"))

    monkeypatch.setenv("PRAYERHUB_CONFIG_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    config = ConfigLoader().load()
    summary = _config_summary(config)

    assert summary["control_panel"]["auth"] == {"username": "admin"}
    assert "password_hash" not in str(summary)
