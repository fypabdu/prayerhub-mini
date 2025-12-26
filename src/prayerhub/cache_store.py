from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional


class CacheStore:
    def __init__(self, root_dir: Path) -> None:
        # Use a dedicated folder so cache files stay isolated and easy to prune.
        self._root_dir = root_dir
        self._root_dir.mkdir(parents=True, exist_ok=True)
        self._logger = logging.getLogger(self.__class__.__name__)

    def read(self, key: str) -> Optional[Dict[str, Any]]:
        path = self._path_for_key(key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            # Corrupt cache should not crash the app; log and fall back to None.
            self._logger.warning("Cache read failed for %s: %s", path, exc)
            return None
        if not isinstance(data, dict):
            # We only store JSON objects; anything else is treated as invalid.
            self._logger.warning("Cache file %s is not a JSON object", path)
            return None
        return data

    def write(self, key: str, payload: Dict[str, Any]) -> None:
        path = self._path_for_key(key)
        tmp_path = path.with_suffix(".tmp")

        # Write to a temp file and rename for atomicity across crashes.
        data = json.dumps(payload, indent=2, sort_keys=True)
        try:
            tmp_path.write_text(data, encoding="utf-8")
            tmp_path.replace(path)
        except OSError as exc:
            self._logger.error("Cache write failed for %s: %s", path, exc)
            raise

    def _path_for_key(self, key: str) -> Path:
        # Keep filenames predictable for debugging and on-device inspection.
        safe_key = key.replace("/", "_")
        return self._root_dir / f"{safe_key}.json"
