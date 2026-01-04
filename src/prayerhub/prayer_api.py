from __future__ import annotations

import logging
from datetime import date
import time
from typing import Any, Callable, Dict, Optional

import requests

from prayerhub.prayer_times import ApiError


class PrayerApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: int = 8,
        max_retries: int = 0,
        backoff_base_seconds: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        session: Optional[requests.Session] = None,
    ) -> None:
        # We share a session for connection pooling and keep timeouts centralized.
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_retries = max(0, int(max_retries))
        self._backoff_base_seconds = max(0.0, float(backoff_base_seconds))
        self._sleep = sleep
        self._session = session or requests.Session()
        self._logger = logging.getLogger(self.__class__.__name__)

    def get_date(self, *, madhab: str, city: str, day: date) -> Dict[str, Any]:
        return self._get(
            "/api/v1/times/date/",
            {"madhab": madhab, "city": city, "date": day.isoformat()},
        )

    def get_range(
        self, *, madhab: str, city: str, start: date, end: date
    ) -> Dict[str, Any]:
        return self._get(
            "/api/v1/times/range/",
            {
                "madhab": madhab,
                "city": city,
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
        )

    def _get(self, path: str, params: Dict[str, str]) -> Dict[str, Any]:
        url = f"{self._base_url}{path}"
        last_error: Optional[ApiError] = None
        attempts = self._max_retries + 1

        for attempt in range(attempts):
            should_retry = False
            try:
                resp = self._session.get(
                    url, params=params, timeout=self._timeout_seconds
                )
            except requests.RequestException as exc:
                # Network errors should not crash scheduling; surface as ApiError.
                last_error = ApiError(f"Request failed for {url}: {exc}")
                should_retry = True
            else:
                if resp.status_code != 200:
                    self._logger.warning(
                        "API call failed: %s %s", resp.status_code, resp.text
                    )
                    last_error = ApiError(
                        f"API request failed with status {resp.status_code}"
                    )
                    if resp.status_code >= 500:
                        should_retry = True
                else:
                    try:
                        data = resp.json()
                    except ValueError as exc:
                        raise ApiError("API returned invalid JSON") from exc

                    if not isinstance(data, dict):
                        raise ApiError("API response must be a JSON object")

                    return data

            if should_retry and attempt < self._max_retries:
                delay = self._backoff_base_seconds * (2 ** attempt)
                if delay > 0:
                    self._sleep(delay)
                continue

            if last_error is not None:
                raise last_error

        raise ApiError("API request failed after retries")
