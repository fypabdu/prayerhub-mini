from __future__ import annotations

from pathlib import Path

import pytest

from prayerhub.config import ConfigError, ConfigLoader


def _write_yaml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed_audio_files(root: Path) -> None:
    audio_dir = root / "data" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    for name in [
        "connected.mp3",
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
  playback_timeout_seconds: 300
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

keepalive:
  enabled: false
  interval_minutes: 5
  audio_file: "data/audio/test_beep.mp3"
  volume_percent: 1

control_panel:
  enabled: true
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


def test_loads_base_and_overlays_config_d_in_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    test_audio = tmp_path / "test_beep.mp3"
    test_audio.write_bytes(b"beep")
    _seed_audio_files(tmp_path)

    _write_yaml(tmp_path / "config.yml", _base_config(str(test_audio)))
    _write_yaml(
        tmp_path / "config.d" / "10-location.yml",
        """
location:
  city: "galle"
""",
    )
    _write_yaml(
        tmp_path / "config.d" / "20-location.yml",
        """
location:
  city: "kandy"
""",
    )

    monkeypatch.setenv("PRAYERHUB_CONFIG_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    config = ConfigLoader().load()

    assert config.location.city == "kandy"
    assert config.logging.file_path == "logs/prayerhub.log"


def test_missing_test_audio_path_fails_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    missing_audio = "missing.mp3"
    _write_yaml(tmp_path / "config.yml", _base_config(missing_audio))

    monkeypatch.setenv("PRAYERHUB_CONFIG_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    _seed_audio_files(tmp_path)

    with pytest.raises(ConfigError):
        ConfigLoader().load()


def test_missing_adhan_audio_path_fails_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_audio = tmp_path / "test_beep.mp3"
    test_audio.write_bytes(b"beep")
    _seed_audio_files(tmp_path)

    config_text = _base_config("test_beep.mp3").replace(
        'fajr: "data/audio/adhan_fajr.mp3"', 'fajr: "adhan_fajr.mp3"'
    ).replace(
        'dhuhr: "data/audio/adhan_dhuhr.mp3"', 'dhuhr: "missing.mp3"'
    )
    _write_yaml(tmp_path / "config.yml", config_text)

    monkeypatch.setenv("PRAYERHUB_CONFIG_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ConfigError):
        ConfigLoader().load()


def test_missing_quran_audio_path_fails_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_audio = tmp_path / "test_beep.mp3"
    test_audio.write_bytes(b"beep")
    _seed_audio_files(tmp_path)

    config_text = _base_config("test_beep.mp3").replace(
        'file: "data/audio/quran_morning.mp3"', 'file: "missing_quran.mp3"'
    ).replace(
        'fajr: "data/audio/adhan_fajr.mp3"', 'fajr: "adhan_fajr.mp3"'
    )
    _write_yaml(tmp_path / "config.yml", config_text)

    monkeypatch.setenv("PRAYERHUB_CONFIG_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ConfigError):
        ConfigLoader().load()


def test_missing_notification_audio_path_fails_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_audio = tmp_path / "test_beep.mp3"
    test_audio.write_bytes(b"beep")
    _seed_audio_files(tmp_path)

    config_text = _base_config("test_beep.mp3").replace(
        'sunrise: "data/audio/sunrise.mp3"', 'sunrise: "missing_sunrise.mp3"'
    ).replace(
        'fajr: "data/audio/adhan_fajr.mp3"', 'fajr: "adhan_fajr.mp3"'
    )
    _write_yaml(tmp_path / "config.yml", config_text)

    monkeypatch.setenv("PRAYERHUB_CONFIG_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ConfigError):
        ConfigLoader().load()


def test_relative_audio_path_resolves_from_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_audio = tmp_path / "test_beep.mp3"
    test_audio.write_bytes(b"beep")
    _seed_audio_files(tmp_path)

    _write_yaml(tmp_path / "config.yml", _base_config("test_beep.mp3"))

    monkeypatch.setenv("PRAYERHUB_CONFIG_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    config = ConfigLoader().load()
    assert config.audio.test_audio == "test_beep.mp3"


def test_missing_control_panel_password_hash_fails_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_audio = tmp_path / "test_beep.mp3"
    test_audio.write_bytes(b"beep")
    _seed_audio_files(tmp_path)

    config_text = _base_config(str(test_audio)).replace(
        'password_hash: "pbkdf2:sha256:..."', ""
    )
    _write_yaml(tmp_path / "config.yml", config_text)

    monkeypatch.setenv("PRAYERHUB_CONFIG_DIR", str(tmp_path))

    with pytest.raises(ConfigError):
        ConfigLoader().load()


def test_volume_percent_out_of_range_fails_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_audio = tmp_path / "test_beep.mp3"
    test_audio.write_bytes(b"beep")
    _seed_audio_files(tmp_path)

    config_text = _base_config(str(test_audio)).replace("master_percent: 60", "master_percent: 101")
    _write_yaml(tmp_path / "config.yml", config_text)

    monkeypatch.setenv("PRAYERHUB_CONFIG_DIR", str(tmp_path))

    with pytest.raises(ConfigError):
        ConfigLoader().load()
