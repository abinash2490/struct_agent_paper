"""
Unit tests for research_paper/benchmarks/verify_cae_parity.py.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import pytest
from verify_cae_parity import (
    calculate_parity_metrics,
    generate_tables,
    SAP2000_VERSION,
    ETABS_VERSION,
)


def test_cae_parity_metrics_precision():
    metrics = calculate_parity_metrics()
    assert len(metrics) == 14, f"Expected 14 parity comparison metrics, got {len(metrics)}"

    max_diff = 0.0
    for row in metrics:
        rel_diff = row["diff_pct"]
        if rel_diff > max_diff:
            max_diff = rel_diff
        assert (
            rel_diff < 0.50
        ), f"Parameter '{row['parameter']}' in model '{row['model']}' exceeded 0.5% threshold: {rel_diff:.4f}%"
        assert row.get("source"), f"Metric row missing CAE source provenance: {row}"

    assert max_diff < 0.50, f"Max relative difference {max_diff:.4f}% must be < 0.50%"


def test_commercial_version_metadata():
    assert "SAP2000" in SAP2000_VERSION
    assert "ETABS" in ETABS_VERSION
    assert ("v27" in SAP2000_VERSION or "v24" in SAP2000_VERSION or "Build" in SAP2000_VERSION)
    assert ("v23" in ETABS_VERSION or "v21" in ETABS_VERSION or "Build" in ETABS_VERSION)


def test_generate_tables_file_output():
    metrics = calculate_parity_metrics()
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_table = Path(tmp_dir) / "test_table.md"
        generate_tables(metrics, out_table)
        assert out_table.exists()
        md_content = out_table.read_text(encoding="utf-8")
        assert "| **Benchmark Structure** | Parameter / Metric |" in md_content or "SAP2000" in md_content
        assert "ETABS" in md_content
        assert "PASSED (< 0.5%)" in md_content
