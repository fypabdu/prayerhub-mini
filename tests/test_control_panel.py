from __future__ import annotations

from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from werkzeug.security import generate_password_hash

from prayerhub.control_panel import ControlPanelServer
from prayerhub.test_scheduler import TestScheduleService


class FixedNow:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _make_app() -> tuple[ControlPanelServer, TestScheduleService]:
    scheduler = BackgroundScheduler()
    scheduler.start(paused=True)
    test_scheduler = TestScheduleService(
        scheduler=scheduler,
        now_provider=FixedNow(datetime(2025, 1, 1, 10, 0)).now,
        handler=lambda: None,
        max_pending_tests=5,
        max_minutes_ahead=1440,
    )
    server = ControlPanelServer(
        username="admin",
        password_hash=generate_password_hash("secret"),
        test_scheduler=test_scheduler,
        secret_key="test-secret",
    )
    return server, test_scheduler


def test_login_required_redirects() -> None:
    server, _ = _make_app()
    client = server.app.test_client()

    resp = client.get("/")

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_valid_login_creates_session() -> None:
    server, _ = _make_app()
    client = server.app.test_client()

    resp = client.post(
        "/login",
        data={"username": "admin", "password": "secret"},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")


def test_schedule_test_creates_job() -> None:
    server, test_scheduler = _make_app()
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
