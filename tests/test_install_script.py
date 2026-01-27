from __future__ import annotations

from pathlib import Path


def test_install_script_allows_reboot() -> None:
    script_path = Path(__file__).resolve().parents[1] / "deploy" / "install.sh"
    content = script_path.read_text(encoding="utf-8")
    assert "systemctl reboot" in content
