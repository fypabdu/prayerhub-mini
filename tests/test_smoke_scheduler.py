from __future__ import annotations

from datetime import date, datetime

import pytest
from apscheduler.schedulers.background import BackgroundScheduler

from prayerhub.prayer_times import DayPlan
from prayerhub.scheduler import JobScheduler


class FixedNow:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


@pytest.mark.smoke
def test_scheduler_creates_jobs_for_day_plan() -> None:
    scheduler = BackgroundScheduler()
    scheduler.start(paused=True)

    plan = DayPlan(
        date=date(2025, 1, 1),
        madhab="shafi",
        city="colombo",
        times={"fajr": "05:00", "dhuhr": "12:00"},
    )

    job_scheduler = JobScheduler(
        scheduler=scheduler,
        handler=lambda *_: None,
        now_provider=FixedNow(datetime(2025, 1, 1, 4, 0)).now,
    )

    job_scheduler.schedule_day(plan)

    # Smoke check: two future jobs should be scheduled.
    assert len(scheduler.get_jobs()) == 2
