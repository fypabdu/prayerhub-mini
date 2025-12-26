from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, Optional

import requests

from prayerhub.prayer_times import ApiError


class PrayerApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: int = 8,
        session: Optional[requests.Session] = None,
    ) -> None:
        # We share a session for connection pooling and keep timeouts centralized.
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
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
        try:
            resp = self._session.get(url, params=params, timeout=self._timeout_seconds)
        except requests.RequestException as exc:
            # Network errors should not crash scheduling; surface as ApiError.
            raise ApiError(f"Request failed for {url}: {exc}") from exc

        if resp.status_code != 200:
            self._logger.warning("API call failed: %s %s", resp.status_code, resp.text)
            raise ApiError(f"API request failed with status {resp.status_code}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise ApiError("API returned invalid JSON") from exc

        if not isinstance(data, dict):
            raise ApiError("API response must be a JSON object")

        return data
