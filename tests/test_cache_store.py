from __future__ import annotations

import json
from pathlib import Path

from prayerhub.cache_store import CacheStore


def test_write_then_read_returns_same_payload(tmp_path: Path) -> None:
    store = CacheStore(tmp_path)
    payload = {"date": "2025-01-01", "times": {"fajr": "05:00"}}

    store.write("day_2025-01-01", payload)
    loaded = store.read("day_2025-01-01")

    assert loaded == payload


def test_corrupt_json_returns_none(tmp_path: Path) -> None:
    store = CacheStore(tmp_path)
    cache_file = tmp_path / "corrupt.json"
    cache_file.write_text("{not-json", encoding="utf-8")

    loaded = store.read("corrupt")

    assert loaded is None
    assert cache_file.exists()
    assert cache_file.read_text(encoding="utf-8") == "{not-json"
