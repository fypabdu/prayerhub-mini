from __future__ import annotations

from dataclasses import dataclass

import pytest
import requests

from prayerhub.prayer_api import PrayerApiClient
from prayerhub.prayer_times import ApiError


@dataclass
class FakeResponse:
    status_code: int
    payload: object
    text: str = ""

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeSession:
    def __init__(self, results: list[object]) -> None:
        self._results = list(results)
        self.calls: list[tuple[str, dict[str, str], int]] = []

    def get(self, url: str, *, params: dict[str, str], timeout: int):
        self.calls.append((url, params, timeout))
        if not self._results:
            raise AssertionError("No fake result configured")
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_retries_on_request_exception() -> None:
    session = FakeSession(
        [
            requests.RequestException("network"),
            requests.RequestException("network"),
            FakeResponse(200, {"ok": True}),
        ]
    )
    sleeps: list[float] = []

    client = PrayerApiClient(
        base_url="http://example.com",
        timeout_seconds=1,
        max_retries=2,
        backoff_base_seconds=1.0,
        sleep=sleeps.append,
        session=session,
    )

    payload = client.get_date(madhab="shafi", city="colombo", day=_fake_day())

    assert payload == {"ok": True}
    assert len(session.calls) == 3
    assert sleeps == [1.0, 2.0]


def test_retries_on_server_error() -> None:
    session = FakeSession(
        [
            FakeResponse(500, {"error": "bad"}, text="bad"),
            FakeResponse(200, {"ok": True}),
        ]
    )
    sleeps: list[float] = []

    client = PrayerApiClient(
        base_url="http://example.com",
        timeout_seconds=1,
        max_retries=1,
        backoff_base_seconds=0.5,
        sleep=sleeps.append,
        session=session,
    )

    payload = client.get_date(madhab="shafi", city="colombo", day=_fake_day())

    assert payload == {"ok": True}
    assert sleeps == [0.5]


def test_no_retry_on_client_error() -> None:
    session = FakeSession([FakeResponse(400, {"error": "bad"}, text="bad")])
    sleeps: list[float] = []

    client = PrayerApiClient(
        base_url="http://example.com",
        timeout_seconds=1,
        max_retries=3,
        sleep=sleeps.append,
        session=session,
    )

    with pytest.raises(ApiError):
        client.get_date(madhab="shafi", city="colombo", day=_fake_day())

    assert len(session.calls) == 1
    assert sleeps == []


def _fake_day():
    from datetime import date

    return date(2025, 1, 1)
