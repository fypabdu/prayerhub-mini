from __future__ import annotations

from datetime import date, datetime

from apscheduler.schedulers.background import BackgroundScheduler

from prayerhub.cache_store import CacheStore
from prayerhub.prayer_times import DayPlan, PrayerTimeService
from prayerhub.scheduler import JobScheduler
from prayerhub.startup import schedule_from_cache, schedule_refresh


class FixedNow:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class FakeApiClient:
    def __init__(self, payload) -> None:
        self.payload = payload
        self.calls = 0

    def get_range(self, *, madhab: str, city: str, start: date, end: date):
        self.calls += 1
        return self.payload


def test_schedule_from_cache_only_future_jobs(tmp_path) -> None:
    cache = CacheStore(tmp_path)
    today = date(2025, 1, 1)
    cache.write(
        "day_2025-01-01",
        {
            "date": "2025-01-01",
            "madhab": "shafi",
            "city": "colombo",
            "times": {"fajr": "05:00", "dhuhr": "12:00"},
        },
    )

    scheduler = BackgroundScheduler()
    scheduler.start(paused=True)
    job_scheduler = JobScheduler(
        scheduler=scheduler,
        handler=lambda *_: None,
        now_provider=FixedNow(datetime(2025, 1, 1, 10, 0)).now,
    )

    schedule_from_cache(cache, job_scheduler)

    jobs = scheduler.get_jobs()
    assert len(jobs) == 1
    assert jobs[0].id.endswith("20250101")


def test_refresh_reschedules_today_and_tomorrow(tmp_path) -> None:
    cache = CacheStore(tmp_path)
    scheduler = BackgroundScheduler()
    scheduler.start(paused=True)
    job_scheduler = JobScheduler(
        scheduler=scheduler,
        handler=lambda *_: None,
        now_provider=FixedNow(datetime(2025, 1, 1, 4, 0)).now,
    )

    payload = {
        "results": [
            {
                "date": "2025-01-01",
                "madhab": "shafi",
                "city": "colombo",
                "times": {"fajr": "05:00", "dhuhr": "12:00"},
            },
            {
                "date": "2025-01-02",
                "madhab": "shafi",
                "city": "colombo",
                "times": {"fajr": "05:01", "dhuhr": "12:01"},
            },
        ]
    }
    api = FakeApiClient(payload)
    service = PrayerTimeService(
        api_client=api,
        cache_store=cache,
        city="colombo",
        madhab="shafi",
        clock=FixedNow(datetime(2025, 1, 1, 4, 0)),
    )

    schedule_refresh(job_scheduler, service, prefetch_days=2)

    jobs = scheduler.get_jobs()
    assert len(jobs) == 5
    assert scheduler.get_job("refresh_daily") is not None
