"""
Unit tests for research_paper/benchmarks/analyze_results.py.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import json
import pytest
from analyze_results import (
    load_all_results,
    print_and_save_markdown_table,
    print_and_save_detailed_table,
    print_and_save_failure_mode_table,
    compute_statistical_significance,
    generate_plots,
)


def test_load_all_results_live(benchmarks_dir: Path):
    results_dir = benchmarks_dir / "results"
    summaries = load_all_results(results_dir)
    assert len(summaries) >= 1, "Expected at least 1 benchmark result summary"

    for s in summaries:
        assert "model" in s
        assert "configuration" in s
        assert "task_completion_rate_pct" in s
        # Ensure code compliance metrics are populated for runs with design cases
        if s.get("design_cases", 0) > 0:
            assert s.get("code_compliance_rate_pct") is not None
            assert s.get("code_compliance_rate_margin_pct") is not None
            assert s["code_compliance_rate_margin_pct"] >= s["code_compliance_rate_pct"]


def test_margin_ccr_computation_synthetic():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Create synthetic result with one case at 1.00 (strict compliant)
        # and one case at 1.01 (margin compliant only)
        synthetic_data = {
            "model": "synthetic_model",
            "configuration": "full_agent",
            "timestamp": "2026-10-21T12:00:00",
            "task_completion_rate_pct": 100.0,
            "case_results": [
                {
                    "case_id": "A01_Portal_Frame_Office",
                    "design_required": True,
                    "final_dcr": 1.00,
                    "code_compliant": True,
                    "concrete_volume_m3": 1.757,
                },
                {
                    "case_id": "A02_Portal_Frame_Storage",
                    "design_required": True,
                    "final_dcr": 1.015,
                    "code_compliant": False,
                    "concrete_volume_m3": 3.820,
                },
            ],
        }

        with open(tmp_path / "results_synthetic.json", "w", encoding="utf-8") as f:
            json.dump(synthetic_data, f)

        loaded = load_all_results(tmp_path)
        assert len(loaded) == 1
        res = loaded[0]

        assert res["compliant_cases"] == 1  # only A01 is strict
        assert res["code_compliance_rate_pct"] == 50.0  # 1 / 2 = 50.0%
        assert res["code_compliance_rate_margin_pct"] == 100.0  # both <= 1.02: 2 / 2 = 100.0%


def test_table_generation_functions(benchmarks_dir: Path):
    results_dir = benchmarks_dir / "results"
    summaries = load_all_results(results_dir)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_results_dir = Path(tmp_dir) / "results"
        tmp_results_dir.mkdir(parents=True, exist_ok=True)

        summary_file = print_and_save_markdown_table(summaries, tmp_results_dir)
        assert summary_file.exists()
        content = summary_file.read_text(encoding="utf-8")
        assert "| Model Name | Config |" in content
        assert "Compliant (CCR Strict / Margin)" in content

        # Detailed table expects benchmark_cases.json in parent directory
        cases_file = tmp_results_dir.parent / "benchmark_cases.json"
        import shutil
        shutil.copyfile(benchmarks_dir / "benchmark_cases.json", cases_file)

        detail_file = print_and_save_detailed_table(summaries, tmp_results_dir)
        assert detail_file is not None and detail_file.exists()
        detail_content = detail_file.read_text(encoding="utf-8")
        assert "| Case ID | Group | Baseline DCR | Agent DCR |" in detail_content
        assert "eta_vol" in detail_content


def test_multiseed_analysis_pipeline_dod(benchmarks_dir: Path):
    cases_file = benchmarks_dir / "benchmark_cases.json"
    with open(cases_file, "r", encoding="utf-8") as fp:
        raw_cases = json.load(fp)
    case_ids = [c["id"] for c in raw_cases]
    assert len(case_ids) == 24

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_results_dir = Path(tmp_dir) / "results"
        tmp_plots_dir = Path(tmp_dir) / "plots"
        tmp_results_dir.mkdir(parents=True, exist_ok=True)
        tmp_plots_dir.mkdir(parents=True, exist_ok=True)

        for cfg in ["full_agent", "ablated"]:
            all_case_runs = []
            for s_idx in range(5):
                for cid in case_ids:
                    is_design = (
                        "A05" not in cid and "B01" not in cid and "B04" not in cid and
                        "C01" not in cid and "C02" not in cid and "C03" not in cid and
                        "C04" not in cid and "C05" not in cid
                    )
                    is_reflection = ("A08" in cid or "B07" in cid or "C07" in cid)
                    dcr_hist = [2.5, 1.4, 0.85 + 0.01 * s_idx] if is_reflection else ([0.85] if is_design else [])
                    all_case_runs.append({
                        "case_id": cid,
                        "seed_index": s_idx,
                        "design_required": is_design,
                        "success": True if cfg == "full_agent" else (s_idx % 2 == 0),
                        "code_compliant": True if is_design else None,
                        "final_dcr": 0.85 if is_design else None,
                        "initial_dcr": 2.5 if is_reflection else (0.85 if is_design else None),
                        "dcr_history": dcr_hist,
                        "iterations_to_converge": 2 if is_reflection else (0 if is_design else None),
                        "concrete_volume_m3": 10.0,
                        "material_economy_ratio": 1.02,
                        "claims_made_count": 3,
                        "hallucinated_claims_count": 0,
                        "claim_completeness_pct": 100.0,
                        "calculation_hallucination_rate_pct": 0.0,
                        "prompt_to_schema_fidelity_passed": True,
                        "wall_clock_time_sec": 5.0 + s_idx,
                        "failure_mode": None if (cfg == "full_agent" or s_idx % 2 == 0) else "dcr_non_convergence",
                    })

            summary_data = {
                "model": "gemini-3.8-flash",
                "configuration": cfg,
                "timestamp": f"20261021_12000{1 if cfg == 'full_agent' else 0}",
                "seeds": 5,
                "total_cases": 120,
                "total_runs": 120,
                "unique_cases": 24,
                "task_completion_rate_pct": 100.0 if cfg == "full_agent" else 60.0,
                "code_compliance_rate_pct": 100.0 if cfg == "full_agent" else 60.0,
                "calculation_hallucination_rate_pct": 0.0,
                "claim_completeness_rate_pct": 100.0,
                "prompt_to_schema_fidelity_rate_pct": 100.0,
                "case_results": all_case_runs,
            }
            with open(tmp_results_dir / f"results_gemini-3.8-flash_{cfg}_20261021.json", "w", encoding="utf-8") as fp:
                json.dump(summary_data, fp)

        # 1. Load results
        summaries = load_all_results(tmp_results_dir)
        assert len(summaries) == 2

        # 2. Summary Markdown table (Criterion 4a: both CHR % and Claim Completeness %)
        summary_file = print_and_save_markdown_table(summaries, tmp_results_dir)
        assert summary_file.exists()
        summary_content = summary_file.read_text(encoding="utf-8")
        assert "CHR %" in summary_content
        assert "Claim Completeness %" in summary_content
        assert "Runs (TCR) / Cases" in summary_content

        # 3. Failure Mode Table (Criterion 4e: sums to <= 24 per column)
        fail_file = print_and_save_failure_mode_table(summaries, tmp_results_dir)
        assert fail_file.exists()
        fail_content = fail_file.read_text(encoding="utf-8")
        assert "FAILURE-MODE TAXONOMY BREAKDOWN" in fail_content
        for line in fail_content.splitlines():
            if line.startswith("| `gemini-3.8-flash`"):
                parts = [p.strip() for p in line.split("|")[1:-1]]
                assert int(parts[3]) == 24
                assert int(parts[4]) <= 24

        # 4. Statistical Significance Report (Criterion 4c: N Pairs = 24 or 16)
        sig_file = compute_statistical_significance(summaries, tmp_results_dir)
        assert sig_file is not None and sig_file.exists()
        sig_content = sig_file.read_text(encoding="utf-8")
        assert "| Task Completion (TCR) | 24 | 5 |" in sig_content
        assert "| Code Compliance (CCR) | 16 | 5 |" in sig_content

        # 5. Publication Plots (Criterion 4b & 4d: fig_chr_vs_completeness and fig_dcr_convergence)
        saved_plots = generate_plots(summaries, tmp_plots_dir)
        plot_names = [p.name for p in saved_plots]
        assert any(name.startswith("fig_chr_vs_completeness") for name in plot_names)
        assert any(name.startswith("fig_dcr_convergence") for name in plot_names)


def test_heuristic_summary_table_display_na():
    """Verify that heuristic baseline shows N/A for CHR % and Claim Completeness % with footnote."""
    summaries = [{
        "model": "deterministic_heuristic",
        "configuration": "heuristic",
        "timestamp": "20261021_120000",
        "total_cases": 24,
        "total_runs": 24,
        "unique_cases": 24,
        "successful_cases": 24,
        "compliant_cases": 24,
        "design_cases": 16,
        "task_completion_rate_pct": 100.0,
        "code_compliance_rate_pct": 100.0,
        "calculation_hallucination_rate_pct": 0.0,
        "claim_completeness_rate_pct": 0.0,
        "case_results": [],
    }]
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_results_dir = Path(tmp_dir)
        table_path = print_and_save_markdown_table(summaries, tmp_results_dir)
        content = table_path.read_text(encoding="utf-8")
        assert "| `deterministic_heuristic` | heuristic | 24 (**100.0%**) | 24/16 (**100.0%**) | N/A | N/A |" in content
        assert "*Note: CHR and CCR_claims are not applicable to the deterministic heuristic baseline" in content


def test_code_gen_mixed_failed_runs_chr_bounds():
    """Verify that pooled CHR stays in [0.0, 100.0] even when code_gen has failed executions."""
    cases = []
    # 21 successful cases with 4 claims each, 1 hallucination each
    for i in range(21):
        cases.append({
            "case_id": f"Case_{i:02d}",
            "success": True,
            "claims_made": ["weight", "period", "base_shear", "dcr"],
            "claims_made_count": 4,
            "hallucinated_claims_count": 1,
            "expected_oracle_metrics": ["weight", "period", "base_shear", "dcr"],
            "claim_completeness_pct": 100.0,
        })
    # 3 failed cases (script crashed), all 4 expected metrics attempted and failed
    for i in range(21, 24):
        cases.append({
            "case_id": f"Case_{i:02d}",
            "success": False,
            "claims_made": ["weight", "period", "base_shear", "dcr"],
            "claims_made_count": 4,
            "hallucinated_claims_count": 4,
            "expected_oracle_metrics": ["weight", "period", "base_shear", "dcr"],
            "claim_completeness_pct": 0.0,
        })

    total_claims = sum(c["claims_made_count"] for c in cases)
    total_hallucinations = sum(c["hallucinated_claims_count"] for c in cases)
    pooled_chr = round((total_hallucinations / max(total_claims, 1)) * 100.0, 1)

    assert total_claims == 24 * 4
    assert total_hallucinations == 21 * 1 + 3 * 4
    assert 0.0 <= pooled_chr <= 100.0


def test_direct_llm_a05_claim_completeness():
    """Verify that A05 under direct_llm with weight+T1 scores 40.0% completeness (2/5)."""
    from research_paper.benchmarks.oracle_verifier import OracleVerifier
    verifier = OracleVerifier()
    res = verifier.evaluate(
        "A05_2D_Modal_Dynamics",
        col_b=0.40,
        col_h=0.40,
        beam_b=0.30,
        beam_h=0.50,
        claims={"claimed_total_weight_kN": 250.0, "claimed_fundamental_period_s": 0.45},
    )
    expected = res.expected_metrics
    assert len(expected) == 5  # total_weight, T1, T2, T3, MMR
    assert len(res.claims_made) == 2  # total_weight, T1
    completeness = round(len(set(res.claims_made) & set(expected)) / len(expected) * 100.0, 1)
    assert completeness == 40.0

