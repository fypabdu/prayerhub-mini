from __future__ import annotations

from datetime import date, datetime

import pytest

from prayerhub.cache_store import CacheStore
from prayerhub.prayer_times import (
    ApiError,
    DayPlan,
    PrayerTimeService,
    day_plan_from_api,
    day_plans_from_range,
)


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class FakeApiClient:
    def __init__(self, *, range_payload=None, date_payloads=None, fail_range=False, fail_date=False) -> None:
        self._range_payload = range_payload
        self._date_payloads = date_payloads or {}
        self._fail_range = fail_range
        self._fail_date = fail_date
        self.range_calls = 0
        self.date_calls = []

    def get_range(self, *, madhab: str, city: str, start: date, end: date):
        self.range_calls += 1
        if self._fail_range:
            raise ApiError("range failed")
        return self._range_payload

    def get_date(self, *, madhab: str, city: str, day: date):
        self.date_calls.append(day)
        if self._fail_date:
            raise ApiError("date failed")
        return self._date_payloads[day.isoformat()]


def test_parse_date_endpoint_into_day_plan() -> None:
    payload = {
        "date": "2025-01-01",
        "madhab": "shafi",
        "city": "colombo",
        "times": {"fajr": "05:00", "maghrib": "18:00"},
    }

    plan = day_plan_from_api(payload)

    assert isinstance(plan, DayPlan)
    assert plan.date == date(2025, 1, 1)
    assert plan.times["fajr"] == "05:00"


def test_parse_range_endpoint_results() -> None:
    payload = {
        "results": [
            {
                "date": "2025-01-01",
                "madhab": "shafi",
                "city": "colombo",
                "times": {"fajr": "05:00", "maghrib": "18:00"},
            },
            {
                "date": "2025-01-02",
                "madhab": "shafi",
                "city": "colombo",
                "times": {"fajr": "05:01", "maghrib": "18:01"},
            },
        ]
    }

    plans = day_plans_from_range(payload)

    assert [plan.date for plan in plans] == [date(2025, 1, 1), date(2025, 1, 2)]


def test_range_failure_falls_back_to_per_date(tmp_path) -> None:
    base_date = date(2025, 1, 1)
    date_payloads = {
        "2025-01-01": {
            "date": "2025-01-01",
            "madhab": "shafi",
            "city": "colombo",
            "times": {"fajr": "05:00", "maghrib": "18:00"},
        },
        "2025-01-02": {
            "date": "2025-01-02",
            "madhab": "shafi",
            "city": "colombo",
            "times": {"fajr": "05:01", "maghrib": "18:01"},
        },
    }
    api = FakeApiClient(fail_range=True, date_payloads=date_payloads)
    service = PrayerTimeService(
        api_client=api,
        cache_store=CacheStore(tmp_path),
        city="colombo",
        madhab="shafi",
        clock=FixedClock(datetime(2025, 1, 1, 8, 0)),
    )

    service.prefetch(days=2)

    assert api.range_calls == 1
    assert api.date_calls == [base_date, base_date.replace(day=2)]
    assert service.get_day(base_date) is not None
    assert service.get_day(base_date.replace(day=2)) is not None


def test_network_failure_falls_back_to_cache(tmp_path) -> None:
    cached = {
        "date": "2025-01-01",
        "madhab": "shafi",
        "city": "colombo",
        "times": {"fajr": "05:00", "maghrib": "18:00"},
    }
    store = CacheStore(tmp_path)
    store.write("day_2025-01-01", cached)

    api = FakeApiClient(fail_range=True, fail_date=True)
    service = PrayerTimeService(
        api_client=api,
        cache_store=store,
        city="colombo",
        madhab="shafi",
        clock=FixedClock(datetime(2025, 1, 1, 8, 0)),
    )

    service.prefetch(days=1)
    plan = service.get_day(date(2025, 1, 1))

    assert plan is not None
    assert plan.times["fajr"] == "05:00"


def test_missing_extras_are_derived_from_next_day(tmp_path) -> None:
    payload = {
        "results": [
            {
                "date": "2025-01-01",
                "madhab": "shafi",
                "city": "colombo",
                "times": {"fajr": "05:00", "maghrib": "18:00"},
            },
            {
                "date": "2025-01-02",
                "madhab": "shafi",
                "city": "colombo",
                "times": {"fajr": "06:00", "maghrib": "18:01"},
            },
        ]
    }
    api = FakeApiClient(range_payload=payload)
    service = PrayerTimeService(
        api_client=api,
        cache_store=CacheStore(tmp_path),
        city="colombo",
        madhab="shafi",
        clock=FixedClock(datetime(2025, 1, 1, 8, 0)),
    )

    service.prefetch(days=2)

    plan = service.get_day(date(2025, 1, 1))
    assert plan is not None
    assert plan.times["midnight"] == "00:00"
    assert plan.times["tahajjud"] == "02:00"
