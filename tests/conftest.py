import sys
from pathlib import Path


def pytest_sessionstart(session):
    """Ensure src/ is on sys.path for local test runs."""
    repo_root = Path(__file__).resolve().parents[1]
    src_path = repo_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
