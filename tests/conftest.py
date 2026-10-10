"""Test runner setup."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from testing.windows_loader import cleanup, install


def pytest_configure():
    install()


def pytest_sessionfinish():
    cleanup()
