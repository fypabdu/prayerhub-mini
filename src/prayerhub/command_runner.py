from __future__ import annotations

from dataclasses import dataclass
import subprocess
from typing import Protocol, Sequence
import shutil


class ProcessHandle(Protocol):
    def terminate(self) -> None:
        ...

    def poll(self) -> int | None:
        ...

    def wait(self, timeout: int | None = None) -> int:
        ...


class CommandRunner(Protocol):
    def run(
        self, args: Sequence[str], *, timeout: int | None
    ) -> subprocess.CompletedProcess[str]:
        ...

    def which(self, name: str) -> str | None:
        ...

    def spawn(self, args: Sequence[str]) -> ProcessHandle:
        ...


@dataclass
class SubprocessCommandRunner:
    def run(
        self, args: Sequence[str], *, timeout: int | None
    ) -> subprocess.CompletedProcess[str]:
        # Capture output so callers can log details without re-running commands.
        return subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def which(self, name: str) -> str | None:
        # Delegate to shutil.which so we can stub this in tests.
        return shutil.which(name)

    def spawn(self, args: Sequence[str]) -> subprocess.Popen[str]:
        return subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
