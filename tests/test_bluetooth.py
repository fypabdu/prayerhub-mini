from __future__ import annotations

from dataclasses import dataclass

from prayerhub.bluetooth import BluetoothManager
from prayerhub.audio import AudioRouter


@dataclass
class FakeProcess:
    returncode: int
    stdout: str
    stderr: str = ""


class FakeRunner:
    def __init__(self, responses: dict[tuple[str, ...], list[FakeProcess]]) -> None:
        self._responses = {k: list(v) for k, v in responses.items()}
        self.run_calls: list[list[str]] = []

    def which(self, name: str) -> str | None:
        return None

    def run(self, args: list[str], *, timeout: int) -> FakeProcess:
        self.run_calls.append(args)
        key = tuple(args)
        if key not in self._responses or not self._responses[key]:
            raise AssertionError(f"No fake response configured for {args}")
        return self._responses[key].pop(0)


def test_already_connected_skips_connect() -> None:
    mac = "AA:BB:CC:DD:EE:FF"
    responses = {
        ("bluetoothctl", "info", mac): [
            FakeProcess(0, "Connected: yes\n"),
        ],
    }
    runner = FakeRunner(responses)
    router = AudioRouter(runner)
    manager = BluetoothManager(
        runner=runner,
        audio_router=router,
        device_mac=mac,
        ensure_default_sink=False,
    )

    assert manager.ensure_connected() is True
    assert runner.run_calls == [["bluetoothctl", "info", mac]]


def test_disconnected_attempts_connect() -> None:
    mac = "AA:BB:CC:DD:EE:FF"
    responses = {
        ("bluetoothctl", "info", mac): [
            FakeProcess(0, "Connected: no\n"),
            FakeProcess(0, "Connected: yes\n"),
        ],
        ("bluetoothctl", "connect", mac): [
            FakeProcess(0, "Connection successful\n"),
        ],
    }
    runner = FakeRunner(responses)
    router = AudioRouter(runner)
    manager = BluetoothManager(
        runner=runner,
        audio_router=router,
        device_mac=mac,
        ensure_default_sink=False,
    )

    assert manager.ensure_connected() is True
    assert runner.run_calls == [
        ["bluetoothctl", "info", mac],
        ["bluetoothctl", "connect", mac],
        ["bluetoothctl", "info", mac],
    ]


def test_backoff_list_is_used_on_failures() -> None:
    mac = "AA:BB:CC:DD:EE:FF"
    responses = {
        ("bluetoothctl", "info", mac): [
            FakeProcess(0, "Connected: no\n"),
            FakeProcess(0, "Connected: no\n"),
            FakeProcess(0, "Connected: no\n"),
        ],
        ("bluetoothctl", "connect", mac): [
            FakeProcess(1, "Failed\n"),
            FakeProcess(1, "Failed\n"),
            FakeProcess(1, "Failed\n"),
        ],
    }
    runner = FakeRunner(responses)
    router = AudioRouter(runner)
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    manager = BluetoothManager(
        runner=runner,
        audio_router=router,
        device_mac=mac,
        ensure_default_sink=False,
        backoff_seconds=[1, 2, 3],
        sleep=fake_sleep,
    )

    assert manager.ensure_connected() is False
    assert sleeps == [1, 2, 3]
