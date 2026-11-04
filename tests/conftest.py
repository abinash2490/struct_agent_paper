"""
Pytest configuration and shared fixtures for research_paper benchmarks and validation.
"""

from __future__ import annotations

from pathlib import Path
import sys
import pytest

# Ensure research_paper/benchmarks is in sys.path
THIS_DIR = Path(__file__).resolve().parent
BENCHMARKS_DIR = (THIS_DIR.parent / "benchmarks").resolve()
REPO_ROOT = THIS_DIR.parent.parent.resolve()

if str(BENCHMARKS_DIR) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS_DIR))


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def benchmarks_dir() -> Path:
    return BENCHMARKS_DIR


