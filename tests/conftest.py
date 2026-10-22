"""
Pytest configuration and shared fixtures for research_paper benchmarks and validation.
"""

from __future__ import annotations

import json
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


@pytest.fixture(scope="session")
def benchmark_cases_path(benchmarks_dir: Path) -> Path:
    return benchmarks_dir / "benchmark_cases.json"


@pytest.fixture(scope="session")
def benchmark_cases(benchmark_cases_path: Path) -> list[dict]:
    with open(benchmark_cases_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def fixtures_dir(benchmarks_dir: Path) -> Path:
    return benchmarks_dir / "fixtures"
