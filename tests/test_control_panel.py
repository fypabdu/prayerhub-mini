from __future__ import annotations

from datetime import datetime
from pathlib import Path

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


def _make_app() -> tuple[ControlPanelServer, TestScheduleService, FakeRouter, FakePlayer]:
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
    )
    return server, test_scheduler, router, player


def test_login_required_redirects() -> None:
    server, _, _, _ = _make_app()
    client = server.app.test_client()

    resp = client.get("/")

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

    log_path = Path("logs/test.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("line1\nline2\n", encoding="utf-8")

    resp = client.get("/")
    body = resp.get_data(as_text=True)

    assert "event_fajr_20250101" in body
    assert "test_audio" in body
    assert "line2" in body


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
