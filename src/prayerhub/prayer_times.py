from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import logging
from typing import Any, Dict, Iterable, List, Optional

from prayerhub.cache_store import CacheStore


class ApiError(RuntimeError):
    """Raised when the prayer API request fails or returns unusable data."""


@dataclass(frozen=True)
class DayPlan:
    date: date
    madhab: str
    city: str
    times: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "madhab": self.madhab,
            "city": self.city,
            "times": dict(self.times),
        }


def day_plan_from_api(payload: Dict[str, Any]) -> DayPlan:
    # We keep parsing strict so we surface upstream schema issues early.
    try:
        raw_date = payload["date"]
        madhab = payload["madhab"]
        city = payload["city"]
        times = payload["times"]
    except KeyError as exc:
        raise ApiError(f"Missing field in API payload: {exc.args[0]}") from exc
    if not isinstance(times, dict):
        raise ApiError("API payload 'times' must be a mapping")
    return DayPlan(
        date=datetime.strptime(raw_date, "%Y-%m-%d").date(),
        madhab=madhab,
        city=city,
        times=dict(times),
    )


def day_plans_from_range(payload: Dict[str, Any]) -> List[DayPlan]:
    results = payload.get("results", [])
    if not isinstance(results, list):
        raise ApiError("Range payload 'results' must be a list")
    plans: List[DayPlan] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        times = item.get("times", {})
        if isinstance(times, dict) and "error" in times:
            # Skip out-of-range days without aborting the entire range.
            continue
        plans.append(day_plan_from_api(item))
    return plans


class Clock:
    def now(self) -> datetime:  # pragma: no cover - interface only
        raise NotImplementedError


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now()


class PrayerTimeService:
    def __init__(
        self,
        *,
        api_client: Any,
        cache_store: CacheStore,
        city: str,
        madhab: str,
        clock: Optional[Clock] = None,
    ) -> None:
        self._api_client = api_client
        self._cache = cache_store
        self._city = city
        self._madhab = madhab
        self._clock = clock or SystemClock()
        self._logger = logging.getLogger(self.__class__.__name__)

    def prefetch(self, days: int) -> None:
        start = self._clock.now().date()
        end = start + timedelta(days=days - 1)
        plans: List[DayPlan] = []

        try:
            range_payload = self._api_client.get_range(
                madhab=self._madhab, city=self._city, start=start, end=end
            )
            plans = day_plans_from_range(range_payload)
        except ApiError as exc:
            # Range queries are a performance optimization; fall back to per-day.
            self._logger.warning("Range prefetch failed: %s", exc)

        if not plans:
            plans = self._fetch_per_date(start, days)

        if not plans:
            # No fresh data; keep whatever is already cached.
            self._logger.warning("No prayer times fetched; using cache only")
            return

        enriched = self._derive_missing_extras(plans)
        for plan in enriched:
            self._cache.write(self._cache_key(plan.date), plan.to_dict())

    def get_day(self, day: date) -> Optional[DayPlan]:
        cached = self._cache.read(self._cache_key(day))
        if not cached:
            return None
        return day_plan_from_api(cached)

    def _fetch_per_date(self, start: date, days: int) -> List[DayPlan]:
        plans: List[DayPlan] = []
        for offset in range(days):
            current = start + timedelta(days=offset)
            try:
                payload = self._api_client.get_date(
                    madhab=self._madhab, city=self._city, day=current
                )
                plans.append(day_plan_from_api(payload))
            except ApiError as exc:
                # Continue so a single missing date does not stop the loop.
                self._logger.warning("Date fetch failed for %s: %s", current, exc)
        return plans

    def _derive_missing_extras(self, plans: Iterable[DayPlan]) -> List[DayPlan]:
        plans_list = list(plans)
        enriched: List[DayPlan] = []
        for idx, plan in enumerate(plans_list):
            next_plan = plans_list[idx + 1] if idx + 1 < len(plans_list) else None
            enriched.append(_derive_extras(plan, next_plan))
        return enriched

    def _cache_key(self, day: date) -> str:
        # Keep keys predictable so cache inspection is straightforward.
        return f"day_{day.isoformat()}"


def _derive_extras(plan: DayPlan, next_plan: Optional[DayPlan]) -> DayPlan:
    times = dict(plan.times)

    if "sunset" not in times:
        maghrib = times.get("maghrib")
        if maghrib:
            sunset_dt = _combine(plan.date, maghrib) - timedelta(minutes=20)
            times["sunset"] = sunset_dt.strftime("%H:%M")

    if not next_plan:
        if times == plan.times:
            return plan
        return DayPlan(
            date=plan.date,
            madhab=plan.madhab,
            city=plan.city,
            times=times,
        )

    if "midnight" in times and "tahajjud" in times:
        return DayPlan(
            date=plan.date,
            madhab=plan.madhab,
            city=plan.city,
            times=times,
        )

    maghrib = times.get("maghrib")
    next_fajr = next_plan.times.get("fajr")
    if not maghrib or not next_fajr:
        return DayPlan(
            date=plan.date,
            madhab=plan.madhab,
            city=plan.city,
            times=times,
        )

    maghrib_dt = _combine(plan.date, maghrib)
    fajr_dt = _combine(next_plan.date, next_fajr)
    night = fajr_dt - maghrib_dt
    if night <= timedelta(0):
        return DayPlan(
            date=plan.date,
            madhab=plan.madhab,
            city=plan.city,
            times=times,
        )

    if "midnight" not in times:
        midnight_dt = maghrib_dt + night / 2
        times["midnight"] = midnight_dt.strftime("%H:%M")

    if "tahajjud" not in times:
        tahajjud_dt = fajr_dt - night / 3
        times["tahajjud"] = tahajjud_dt.strftime("%H:%M")

    return DayPlan(
        date=plan.date,
        madhab=plan.madhab,
        city=plan.city,
        times=times,
    )


def _combine(day: date, hhmm: str) -> datetime:
    # We treat API times as local wall-clock times without a timezone offset.
    return datetime.strptime(f"{day.isoformat()} {hhmm}", "%Y-%m-%d %H:%M")
