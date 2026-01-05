from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
import logging
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from prayerhub.prayer_times import DayPlan


Handler = Callable[[DayPlan, str], None]


@dataclass
class JobScheduler:
    scheduler: BackgroundScheduler
    handler: Handler
    now_provider: Callable[[], datetime] = datetime.now
    misfire_grace_seconds: int = 60

    def __post_init__(self) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)

    def start(self) -> None:
        # Keep scheduler startup explicit so tests can inject paused schedulers.
        if not self.scheduler.running:
            self.scheduler.start()

    def schedule_day(self, plan: DayPlan, *, quran_times: Optional[Iterable[str]] = None) -> None:
        self._remove_jobs_for_date(plan.date)
        for name, hhmm in sorted(plan.times.items()):
            run_at = self._combine(plan.date, hhmm)
            if run_at <= self.now_provider():
                # Skip past events so we never fire on stale data.
                continue
            job_id = self._job_id(name, plan.date)
            self.scheduler.add_job(
                self.handler,
                trigger=DateTrigger(run_date=run_at),
                id=job_id,
                args=[plan, name],
                replace_existing=True,
                misfire_grace_time=self.misfire_grace_seconds,
                coalesce=True,
                max_instances=1,
            )
            self._logger.info("Scheduled %s at %s", job_id, run_at)

        for hhmm in sorted(quran_times or []):
            run_at = self._combine(plan.date, hhmm)
            if run_at <= self.now_provider():
                continue
            job_id = self._quran_job_id(plan.date, hhmm)
            self.scheduler.add_job(
                self.handler,
                trigger=DateTrigger(run_date=run_at),
                id=job_id,
                args=[plan, f"quran@{hhmm}"],
                replace_existing=True,
                misfire_grace_time=self.misfire_grace_seconds,
                coalesce=True,
                max_instances=1,
            )
            self._logger.info("Scheduled %s at %s", job_id, run_at)

    def schedule_refresh_job(self, *, hour: int = 0, minute: int = 5) -> None:
        # Daily refresh keeps the rolling cache and schedule aligned.
        self.scheduler.add_job(
            self.refresh_and_reschedule,
            trigger=CronTrigger(hour=hour, minute=minute),
            id="refresh_daily",
            replace_existing=True,
            misfire_grace_time=self.misfire_grace_seconds,
            coalesce=True,
            max_instances=1,
        )

    def refresh_and_reschedule(self) -> None:
        # This method is intended to be injected or overridden by the app layer.
        self._logger.warning("refresh_and_reschedule is not configured")

    def _remove_jobs_for_date(self, day: date) -> None:
        suffix = day.strftime("%Y%m%d")
        for job in self.scheduler.get_jobs():
            if job.id.endswith(suffix):
                # Clearing by suffix avoids stale jobs accumulating over time.
                self._logger.info("Removing job %s", job.id)
                self.scheduler.remove_job(job.id)

    def _job_id(self, name: str, day: date) -> str:
        return f"event_{name}_{day.strftime('%Y%m%d')}"

    def _quran_job_id(self, day: date, hhmm: str) -> str:
        # Quran jobs keep the time in the ID for easier tracking in status views.
        compact = hhmm.replace(":", "")
        return f"quran_{day.strftime('%Y%m%d')}_{compact}"

    def _combine(self, day: date, hhmm: str) -> datetime:
        # We store times as local wall-clock HH:MM strings.
        hh, mm = hhmm.split(":")
        return datetime.combine(day, time(int(hh), int(mm)))
