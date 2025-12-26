from __future__ import annotations

from datetime import date, timedelta
import logging
from typing import Iterable, Optional

from prayerhub.cache_store import CacheStore
from prayerhub.prayer_times import DayPlan, PrayerTimeService
from prayerhub.scheduler import JobScheduler


def schedule_from_cache(cache: CacheStore, scheduler: JobScheduler) -> None:
    logger = logging.getLogger("Startup")
    # We schedule from cache immediately to keep the device offline-capable.
    for plan in _read_cached_days(cache):
        scheduler.schedule_day(plan)
    logger.info("Scheduled jobs from cache")


def schedule_refresh(
    scheduler: JobScheduler, prayer_service: PrayerTimeService, prefetch_days: int
) -> None:
    logger = logging.getLogger("Startup")

    def refresh() -> None:
        prayer_service.prefetch(days=prefetch_days)
        today = scheduler.now_provider().date()
        for day in [today, today + timedelta(days=1)]:
            plan = prayer_service.get_day(day)
            if plan:
                scheduler.schedule_day(plan)
        logger.info("Refreshed schedule for %s", today.isoformat())

    scheduler.refresh_and_reschedule = refresh
    scheduler.schedule_refresh_job()
    refresh()


def _read_cached_days(cache: CacheStore) -> Iterable[DayPlan]:
    # CacheStore doesn't index keys, so we scan known prefixes in the folder.
    root = cache._root_dir  # Intentional: internal read for cache bootstrap.
    for path in sorted(root.glob("day_*.json")):
        day_key = path.stem
        payload = cache.read(day_key)
        if payload:
            yield DayPlan(
                date=date.fromisoformat(payload["date"]),
                madhab=payload["madhab"],
                city=payload["city"],
                times=payload["times"],
            )
