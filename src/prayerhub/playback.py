from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from prayerhub.config import AudioConfig
from prayerhub.playback_timeout import PlaybackTimeoutPolicy


class PlaybackHandler:
    def __init__(
        self,
        *,
        bluetooth,
        player,
        audio: AudioConfig,
        timeout_policy: Optional[PlaybackTimeoutPolicy] = None,
    ) -> None:
        self._bluetooth = bluetooth
        self._player = player
        self._audio = audio
        self._timeout_policy = timeout_policy
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle_event(self, event_name: str) -> bool:
        try:
            if not self._bluetooth.ensure_connected_once():
                # Spec requires a single reconnect attempt, then skip if still down.
                self._logger.warning("Bluetooth not connected; skipping %s", event_name)
                return False

            selection = self._select_audio(event_name)
            if not selection:
                self._logger.warning("No audio mapping found for %s", event_name)
                return False

            path, volume = selection
            timeout_seconds = self._resolve_timeout(path)
            self._logger.info(
                "Playback event=%s path=%s volume=%s timeout=%s",
                event_name,
                path,
                volume,
                timeout_seconds,
            )
            return self._player.play(
                path,
                volume_percent=volume,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            # Never let job handler exceptions crash the scheduler thread.
            self._logger.error("Playback handler failed: %s", exc)
            return False

    def _select_audio(self, event_name: str) -> Optional[tuple[Path, int]]:
        if event_name == "test_audio":
            return (
                self._resolve(self._audio.test_audio),
                self._audio.volumes.test_percent,
            )
        if event_name == "fajr":
            return (
                self._resolve(self._audio.adhan.fajr),
                self._audio.volumes.fajr_adhan_percent,
            )
        if event_name in {"dhuhr", "asr", "maghrib", "isha"}:
            return (
                self._resolve(getattr(self._audio.adhan, event_name)),
                self._audio.volumes.adhan_percent,
            )
        if event_name in {"sunrise", "sunset", "midnight", "tahajjud"}:
            return (
                self._resolve(getattr(self._audio.notifications, event_name)),
                self._audio.volumes.notification_percent,
            )
        if event_name.startswith("quran@"):
            time_label = event_name.split("@", 1)[1]
            for item in self._audio.quran_schedule:
                if item.time == time_label:
                    return (
                        self._resolve(item.file),
                        self._audio.volumes.quran_percent,
                    )
        return None

    def _resolve_timeout(self, path: Path) -> Optional[int]:
        if self._timeout_policy is not None:
            return self._timeout_policy.resolve(path)
        timeout_seconds = self._audio.playback_timeout_seconds
        if timeout_seconds == 0:
            return None
        return timeout_seconds

    def _resolve(self, path_str: str) -> Path:
        path = Path(path_str)
        if path.is_absolute():
            return path
        # Use app working directory for relative paths to match config validation.
        return Path.cwd() / path
