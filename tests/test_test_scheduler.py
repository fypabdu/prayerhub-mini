from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from apscheduler.schedulers.background import BackgroundScheduler

from prayerhub.test_scheduler import TestScheduleService


class FixedNow:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def test_schedule_at_time_uses_today_or_tomorrow() -> None:
    now = datetime(2025, 1, 1, 10, 0)
    scheduler = BackgroundScheduler()
    scheduler.start(paused=True)

    service = TestScheduleService(
        scheduler=scheduler,
        now_provider=FixedNow(now).now,
        handler=lambda: None,
        max_pending_tests=5,
        max_minutes_ahead=1440,
    )

    job_id = service.schedule_test_at_time("11:00")
    job = scheduler.get_job(job_id)
    assert job is not None
    assert job.next_run_time.replace(tzinfo=None) == datetime(2025, 1, 1, 11, 0)

    job_id = service.schedule_test_at_time("09:00")
    job = scheduler.get_job(job_id)
    assert job is not None
    assert job.next_run_time.replace(tzinfo=None) == datetime(2025, 1, 2, 9, 0)


def test_schedule_in_minutes_creates_future_job() -> None:
    now = datetime(2025, 1, 1, 10, 0)
    scheduler = BackgroundScheduler()
    scheduler.start(paused=True)

    service = TestScheduleService(
        scheduler=scheduler,
        now_provider=FixedNow(now).now,
        handler=lambda: None,
        max_pending_tests=5,
        max_minutes_ahead=1440,
    )

    job_id = service.schedule_test_in_minutes(15)
    job = scheduler.get_job(job_id)
    assert job is not None
    assert job.next_run_time.replace(tzinfo=None) == datetime(2025, 1, 1, 10, 15)


def test_schedule_rejects_past_or_too_far() -> None:
    now = datetime(2025, 1, 1, 10, 0)
    scheduler = BackgroundScheduler()
    scheduler.start(paused=True)

    service = TestScheduleService(
        scheduler=scheduler,
        now_provider=FixedNow(now).now,
        handler=lambda: None,
        max_pending_tests=5,
        max_minutes_ahead=60,
    )

    with pytest.raises(ValueError):
        service.schedule_test_in_minutes(0)

    with pytest.raises(ValueError):
        service.schedule_test_in_minutes(61)


def test_cancel_removes_job() -> None:
    now = datetime(2025, 1, 1, 10, 0)
    scheduler = BackgroundScheduler()
    scheduler.start(paused=True)

    service = TestScheduleService(
        scheduler=scheduler,
        now_provider=FixedNow(now).now,
        handler=lambda: None,
        max_pending_tests=5,
        max_minutes_ahead=1440,
    )

    job_id = service.schedule_test_in_minutes(10)
    assert service.cancel_test_job(job_id) is True
    assert scheduler.get_job(job_id) is None


def test_max_pending_tests_enforced() -> None:
    now = datetime(2025, 1, 1, 10, 0)
    scheduler = BackgroundScheduler()
    scheduler.start(paused=True)

    service = TestScheduleService(
        scheduler=scheduler,
        now_provider=FixedNow(now).now,
        handler=lambda: None,
        max_pending_tests=1,
        max_minutes_ahead=1440,
    )

    service.schedule_test_in_minutes(5)
    with pytest.raises(ValueError):
        service.schedule_test_in_minutes(10)
