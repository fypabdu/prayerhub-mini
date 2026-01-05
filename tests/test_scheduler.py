from __future__ import annotations

from datetime import date, datetime, time

from apscheduler.schedulers.background import BackgroundScheduler

from prayerhub.prayer_times import DayPlan
from prayerhub.scheduler import JobScheduler


class FixedNow:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def test_reschedule_logs_removed_jobs(tmp_path, caplog) -> None:
    scheduler = BackgroundScheduler()
    scheduler.start(paused=True)
    job_scheduler = JobScheduler(
        scheduler=scheduler,
        handler=lambda *_: None,
        now_provider=FixedNow(datetime(2025, 1, 1, 4, 0)).now,
    )

    scheduler.add_job(
        lambda: None,
        trigger="date",
        id="event_fajr_20250101",
        run_date=datetime(2025, 1, 1, 5, 0),
    )
    scheduler.add_job(
        lambda: None,
        trigger="date",
        id="event_other_20250102",
        run_date=datetime(2025, 1, 2, 5, 0),
    )

    plan = DayPlan(
        date=date(2025, 1, 1),
        madhab="shafi",
        city="colombo",
        times={"fajr": "05:00"},
    )

    with caplog.at_level("INFO"):
        job_scheduler.schedule_day(plan)

    assert "Removing job event_fajr_20250101" in caplog.text

def _plan_for(day: date, times: dict[str, str]) -> DayPlan:
    return DayPlan(date=day, madhab="shafi", city="colombo", times=times)


def test_schedule_day_only_future_jobs() -> None:
    today = date(2025, 1, 1)
    now = datetime(2025, 1, 1, 10, 0)
    scheduler = BackgroundScheduler()
    scheduler.start(paused=True)

    job_scheduler = JobScheduler(
        scheduler=scheduler,
        now_provider=FixedNow(now).now,
        handler=lambda *_: None,
    )

    plan = _plan_for(today, {"fajr": "05:00", "dhuhr": "12:00"})
    job_scheduler.schedule_day(plan)

    jobs = scheduler.get_jobs()
    assert len(jobs) == 1
    assert jobs[0].id.endswith("20250101")


def test_schedule_day_adds_quran_jobs() -> None:
    today = date(2025, 1, 1)
    now = datetime(2025, 1, 1, 6, 0)
    scheduler = BackgroundScheduler()
    scheduler.start(paused=True)

    job_scheduler = JobScheduler(
        scheduler=scheduler,
        now_provider=FixedNow(now).now,
        handler=lambda *_: None,
    )

    plan = _plan_for(today, {"dhuhr": "12:00"})
    quran_schedule = ["06:30", "18:15"]
    job_scheduler.schedule_day(plan, quran_times=quran_schedule)

    ids = sorted(job.id for job in scheduler.get_jobs())
    assert "quran_20250101_0630" in ids
    assert "quran_20250101_1815" in ids


def test_reschedule_does_not_duplicate_jobs() -> None:
    today = date(2025, 1, 1)
    now = datetime(2025, 1, 1, 10, 0)
    scheduler = BackgroundScheduler()
    scheduler.start(paused=True)

    job_scheduler = JobScheduler(
        scheduler=scheduler,
        now_provider=FixedNow(now).now,
        handler=lambda *_: None,
    )

    plan = _plan_for(today, {"dhuhr": "12:00"})
    job_scheduler.schedule_day(plan)
    job_scheduler.schedule_day(plan)

    jobs = scheduler.get_jobs()
    assert len(jobs) == 1


def test_schedule_day_removes_old_jobs_for_date() -> None:
    today = date(2025, 1, 1)
    now = datetime(2025, 1, 1, 6, 0)
    scheduler = BackgroundScheduler()
    scheduler.start(paused=True)

    job_scheduler = JobScheduler(
        scheduler=scheduler,
        now_provider=FixedNow(now).now,
        handler=lambda *_: None,
    )

    stale_id = f"event_maghrib_{today.strftime('%Y%m%d')}"
    scheduler.add_job(
        lambda: None,
        trigger="date",
        id=stale_id,
        run_date=datetime.combine(today, time(18, 0)),
        replace_existing=True,
    )

    plan = _plan_for(today, {"fajr": "05:00", "dhuhr": "12:00"})
    job_scheduler.schedule_day(plan)

    jobs = scheduler.get_jobs()
    assert len(jobs) == 1
    assert jobs[0].id.endswith("20250101")
