from __future__ import annotations

from dataclasses import dataclass
import subprocess
from typing import Protocol, Sequence
import shutil


class CommandRunner(Protocol):
    def run(
        self, args: Sequence[str], *, timeout: int | None
    ) -> subprocess.CompletedProcess[str]:
        ...

    def which(self, name: str) -> str | None:
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
