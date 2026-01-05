from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from werkzeug.security import generate_password_hash

from prayerhub.control_panel import ControlPanelServer
from prayerhub.test_scheduler import TestScheduleService


class FixedNow:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class FakeRouter:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def set_master_volume(self, percent: int, *, timeout_seconds: int = 3) -> None:
        self.calls.append(percent)


class FakePlayer:
    def __init__(self) -> None:
        self.events: list[str] = []

    def __call__(self, event: str) -> bool:
        self.events.append(event)
        return True


def _make_app(
    *,
    config_path: Path | None = None,
    device_status_provider: Callable[[], dict] | None = None,
) -> tuple[ControlPanelServer, TestScheduleService, FakeRouter, FakePlayer]:
    scheduler = BackgroundScheduler()
    scheduler.start(paused=True)
    test_scheduler = TestScheduleService(
        scheduler=scheduler,
        now_provider=FixedNow(datetime(2025, 1, 1, 10, 0)).now,
        handler=lambda: None,
        max_pending_tests=5,
        max_minutes_ahead=1440,
    )
    router = FakeRouter()
    player = FakePlayer()
    server = ControlPanelServer(
        username="admin",
        password_hash=generate_password_hash("secret"),
        test_scheduler=test_scheduler,
        secret_key="test-secret",
        scheduler=scheduler,
        audio_router=router,
        play_handler=player,
        log_path="logs/test.log",
        quran_times=("06:30",),
        config_path=str(config_path) if config_path else None,
        device_status_provider=device_status_provider,
    )
    return server, test_scheduler, router, player


def test_login_required_redirects() -> None:
    server, _, _, _ = _make_app()
    client = server.app.test_client()

    resp = client.get("/")

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

    resp = client.get("/status")

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

def test_valid_login_creates_session() -> None:
    server, _, _, _ = _make_app()
    client = server.app.test_client()

    resp = client.post(
        "/login",
        data={"username": "admin", "password": "secret"},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")


def test_schedule_test_creates_job() -> None:
    server, test_scheduler, _, _ = _make_app()
    client = server.app.test_client()

    client.post(
        "/login",
        data={"username": "admin", "password": "secret"},
        follow_redirects=True,
    )

    resp = client.post(
        "/test/schedule",
        data={"minutes": "5"},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert test_scheduler.list_test_jobs()


def test_dashboard_shows_next_jobs_and_test_jobs() -> None:
    status_provider = lambda: {"bluetooth": "connected", "wifi": "ssid", "ip": "1.2.3.4"}
    server, test_scheduler, _, _ = _make_app(device_status_provider=status_provider)
    client = server.app.test_client()

    client.post(
        "/login",
        data={"username": "admin", "password": "secret"},
        follow_redirects=True,
    )
    test_scheduler.schedule_test_in_minutes(5)
    server.scheduler.add_job(
        lambda: None,
        trigger="date",
        id="event_fajr_20250101",
        run_date=datetime(2025, 1, 1, 10, 5),
        replace_existing=True,
    )

    log_path = Path("logs/test.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("line1\nline2\n", encoding="utf-8")

    resp = client.get("/")
    body = resp.get_data(as_text=True)

    assert "event_fajr_20250101" in body
    assert "test_audio" in body
    assert "line2" in body
    assert "connected" in body
    assert "ssid" in body
    assert "1.2.3.4" in body


def test_controls_volume_buttons_call_router() -> None:
    server, _, router, _ = _make_app()
    client = server.app.test_client()

    client.post(
        "/login",
        data={"username": "admin", "password": "secret"},
        follow_redirects=True,
    )

    client.post("/controls/volume", data={"direction": "up"})
    client.post("/controls/volume", data={"direction": "down"})

    assert router.calls == [55, 50]


def test_controls_play_now_triggers_handler() -> None:
    server, _, _, player = _make_app()
    client = server.app.test_client()

    client.post(
        "/login",
        data={"username": "admin", "password": "secret"},
        follow_redirects=True,
    )

    resp = client.post("/controls/play-now", data={"event": "fajr"})

    assert resp.status_code == 302
    assert player.events == ["fajr"]


def test_controls_play_now_triggers_test_and_quran() -> None:
    server, _, _, player = _make_app()
    client = server.app.test_client()

    client.post(
        "/login",
        data={"username": "admin", "password": "secret"},
        follow_redirects=True,
    )

    resp = client.post("/controls/play-now", data={"event": "test_audio"})
    assert resp.status_code == 302

    resp = client.post("/controls/play-now", data={"event": "quran@06:30"})
    assert resp.status_code == 302

    assert player.events == ["test_audio", "quran@06:30"]


def test_status_shows_next_jobs_and_test_jobs() -> None:
    server, test_scheduler, _, _ = _make_app()
    client = server.app.test_client()

    client.post(
        "/login",
        data={"username": "admin", "password": "secret"},
        follow_redirects=True,
    )
    test_scheduler.schedule_test_in_minutes(5)
    server.scheduler.add_job(
        lambda: None,
        trigger="date",
        id="event_fajr_20250101",
        run_date=datetime(2025, 1, 1, 10, 5),
        replace_existing=True,
    )

    resp = client.get("/status")
    body = resp.get_data(as_text=True)

    assert "event_fajr_20250101" in body
    assert "test_audio" in body


def _write_config(path: Path, audio_dir: Path) -> None:
    content = f"""
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
  test_audio: "{audio_dir / 'test.mp3'}"
  connected_tone: "{audio_dir / 'connected.mp3'}"
  playback_timeout_seconds: 300
  adhan:
    fajr: "{audio_dir / 'adhan_fajr.mp3'}"
    dhuhr: "{audio_dir / 'adhan_dhuhr.mp3'}"
    asr: "{audio_dir / 'adhan_asr.mp3'}"
    maghrib: "{audio_dir / 'adhan_maghrib.mp3'}"
    isha: "{audio_dir / 'adhan_isha.mp3'}"
  quran_schedule:
    - time: "06:30"
      file: "{audio_dir / 'quran.mp3'}"
  notifications:
    sunrise: "{audio_dir / 'sunrise.mp3'}"
    sunset: "{audio_dir / 'sunset.mp3'}"
    midnight: "{audio_dir / 'midnight.mp3'}"
    tahajjud: "{audio_dir / 'tahajjud.mp3'}"
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
  audio_file: "{audio_dir / 'test.mp3'}"
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
    path.write_text(content, encoding="utf-8")


def test_config_page_loads_values(tmp_path: Path) -> None:
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    for name in [
        "test.mp3",
        "connected.mp3",
        "adhan_fajr.mp3",
        "adhan_dhuhr.mp3",
        "adhan_asr.mp3",
        "adhan_maghrib.mp3",
        "adhan_isha.mp3",
        "quran.mp3",
        "sunrise.mp3",
        "sunset.mp3",
        "midnight.mp3",
        "tahajjud.mp3",
    ]:
        (audio_dir / name).write_bytes(b"beep")

    config_path = tmp_path / "config.yml"
    _write_config(config_path, audio_dir)

    server, _, _, _ = _make_app(config_path=config_path)
    client = server.app.test_client()
    client.post(
        "/login",
        data={"username": "admin", "password": "secret"},
        follow_redirects=True,
    )

    resp = client.get("/config")
    body = resp.get_data(as_text=True)

    assert "location_city" in body
    assert "colombo" in body
    assert "api_base_url" in body
    assert "http://example.com" in body


def test_config_save_updates_file(tmp_path: Path) -> None:
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    for name in [
        "test.mp3",
        "connected.mp3",
        "adhan_fajr.mp3",
        "adhan_dhuhr.mp3",
        "adhan_asr.mp3",
        "adhan_maghrib.mp3",
        "adhan_isha.mp3",
        "quran.mp3",
        "sunrise.mp3",
        "sunset.mp3",
        "midnight.mp3",
        "tahajjud.mp3",
    ]:
        (audio_dir / name).write_bytes(b"beep")

    config_path = tmp_path / "config.yml"
    _write_config(config_path, audio_dir)

    server, _, _, _ = _make_app(config_path=config_path)
    client = server.app.test_client()
    client.post(
        "/login",
        data={"username": "admin", "password": "secret"},
        follow_redirects=True,
    )

    resp = client.post(
        "/config",
        data={
            "location_city": "kandy",
            "api_timeout": "12",
            "audio_timeout": "0",
            "quran_time_0": "07:00",
            "quran_file_0": str(audio_dir / "quran.mp3"),
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    updated = config_path.read_text(encoding="utf-8")
    assert "city: kandy" in updated
    assert "timeout_seconds: 12" in updated
    assert "playback_timeout_seconds: 0" in updated
