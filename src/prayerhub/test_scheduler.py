from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Callable, List

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger


Handler = Callable[[], None]


@dataclass
class TestScheduleService:
    __test__ = False  # Prevent pytest from treating this runtime class as a test case.
    scheduler: BackgroundScheduler
    now_provider: Callable[[], datetime]
    handler: Handler
    max_pending_tests: int
    max_minutes_ahead: int
    job_prefix: str = "test_audio"

    def __post_init__(self) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)

    def schedule_test_at_time(self, hhmm: str) -> str:
        now = self.now_provider()
        hour, minute = self._parse_hhmm(hhmm)
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            # If the time has passed today, schedule for tomorrow.
            candidate = candidate + timedelta(days=1)
        self._ensure_within_limits(candidate, now)
        return self._schedule(candidate)

    def schedule_test_in_minutes(self, minutes: int) -> str:
        if minutes <= 0:
            raise ValueError("Minutes must be positive")
        if minutes > self.max_minutes_ahead:
            raise ValueError("Minutes exceed max_minutes_ahead")
        now = self.now_provider()
        run_at = now + timedelta(minutes=minutes)
        return self._schedule(run_at)

    def list_test_jobs(self) -> List[dict]:
        jobs = []
        for job in self.scheduler.get_jobs():
            if job.id.startswith(self.job_prefix):
                jobs.append({"id": job.id, "run_date": job.next_run_time})
        return sorted(jobs, key=lambda item: item["run_date"])

    def cancel_test_job(self, job_id: str) -> bool:
        job = self.scheduler.get_job(job_id)
        if not job:
            return False
        self.scheduler.remove_job(job_id)
        return True

    def _schedule(self, run_at: datetime) -> str:
        self._ensure_capacity()
        job_id = self._job_id(run_at)
        self.scheduler.add_job(
            self.handler,
            trigger=DateTrigger(run_date=run_at),
            id=job_id,
            replace_existing=True,
            misfire_grace_time=30,
            coalesce=True,
            max_instances=1,
        )
        self._logger.info("Scheduled test job %s at %s", job_id, run_at)
        return job_id

    def _ensure_capacity(self) -> None:
        pending = len(
            [job for job in self.scheduler.get_jobs() if job.id.startswith(self.job_prefix)]
        )
        if pending >= self.max_pending_tests:
            raise ValueError("Too many pending test jobs")

    def _ensure_within_limits(self, run_at: datetime, now: datetime) -> None:
        delta = run_at - now
        if delta.total_seconds() <= 0:
            raise ValueError("Cannot schedule test job in the past")
        if delta > timedelta(minutes=self.max_minutes_ahead):
            raise ValueError("Scheduled time exceeds max_minutes_ahead")

    def _parse_hhmm(self, hhmm: str) -> tuple[int, int]:
        try:
            hour_str, minute_str = hhmm.split(":")
            return int(hour_str), int(minute_str)
        except ValueError as exc:
            raise ValueError("Time must be in HH:MM format") from exc

    def _job_id(self, run_at: datetime) -> str:
        # Job IDs are derived from time so they remain stable in status views.
        return f"{self.job_prefix}_{run_at.strftime('%Y%m%d%H%M')}"
