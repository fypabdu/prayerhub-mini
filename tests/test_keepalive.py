from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from apscheduler.triggers.interval import IntervalTrigger

from prayerhub.keepalive import KeepAliveService


class FakePlayer:
    def __init__(self, playing: bool) -> None:
        self._playing = playing
        self.calls: list[Path] = []

    def is_playing(self) -> bool:
        return self._playing

    def play(self, path: Path, *, volume_percent: int) -> bool:
        self.calls.append(path)
        return True


class FakeBluetooth:
    def __init__(self, connected: bool) -> None:
        self.connected = connected
        self.calls = 0

    def ensure_connected_once(self) -> bool:
        self.calls += 1
        return self.connected


@dataclass
class FakeScheduler:
    calls: list[dict]

    def add_job(self, func, *, trigger, id, replace_existing, coalesce, max_instances):
        self.calls.append(
            {
                "func": func,
                "trigger": trigger,
                "id": id,
                "replace_existing": replace_existing,
                "coalesce": coalesce,
                "max_instances": max_instances,
            }
        )


def test_keepalive_skips_when_playing(tmp_path: Path) -> None:
    audio_file = tmp_path / "keepalive.mp3"
    audio_file.write_bytes(b"beep")
    player = FakePlayer(playing=True)
    bluetooth = FakeBluetooth(connected=True)
    service = KeepAliveService(
        scheduler=FakeScheduler([]),
        player=player,
        bluetooth=bluetooth,
        audio_file=str(audio_file),
        volume_percent=1,
        interval_minutes=5,
    )

    service.run_once()

    assert player.calls == []


def test_keepalive_plays_when_idle(tmp_path: Path) -> None:
    audio_file = tmp_path / "keepalive.mp3"
    audio_file.write_bytes(b"beep")
    player = FakePlayer(playing=False)
    bluetooth = FakeBluetooth(connected=True)
    service = KeepAliveService(
        scheduler=FakeScheduler([]),
        player=player,
        bluetooth=bluetooth,
        audio_file=str(audio_file),
        volume_percent=1,
        interval_minutes=5,
    )

    service.run_once()

    assert player.calls == [audio_file]


def test_keepalive_schedule_adds_interval_job() -> None:
    scheduler = FakeScheduler([])
    service = KeepAliveService(
        scheduler=scheduler,
        player=FakePlayer(playing=False),
        bluetooth=None,
        audio_file="keepalive.mp3",
        volume_percent=1,
        interval_minutes=5,
    )

    service.schedule()

    assert len(scheduler.calls) == 1
    call = scheduler.calls[0]
    assert call["id"] == "keepalive_audio"
    assert isinstance(call["trigger"], IntervalTrigger)
