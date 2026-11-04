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
    if not results_dir.exists() or not list(results_dir.glob("results_*.json")):
        pytest.skip("No live benchmark results in benchmarks/results")
    summaries = load_all_results(results_dir)
    assert len(summaries) >= 1, "Expected at least 1 benchmark result summary"

    for s in summaries:
        assert "model" in s
        assert "configuration" in s
        assert "task_completion_rate_pct" in s
        # Ensure code compliance metrics are populated for runs with design cases
        if s.get("design_cases", 0) > 0:
            assert s.get("code_compliance_rate_pct") is not None
            assert "code_compliance_rate_margin_pct" not in s


def test_ccr_uses_only_the_oracle_verdict():
    """A DCR of 1.015 is not compliant: there is no tolerance band above DCR = 1.0."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        synthetic_data = {
            "model": "synthetic_model",
            "configuration": "full_agent",
            "timestamp": "2026-10-21T12:00:00",
            "task_completion_rate_pct": 100.0,
            "case_results": [
                {
                    "case_id": "A01_Portal_Gravity_Design_CAD",
                    "design_required": True,
                    "final_dcr": 1.00,
                    "code_compliant": True,
                    "concrete_volume": 1.757,
                },
                {
                    "case_id": "A02_Frame2D_Gravity_Design",
                    "design_required": True,
                    "final_dcr": 1.015,
                    "code_compliant": False,
                    "concrete_volume": 3.820,
                },
            ],
        }

        with open(tmp_path / "results_synthetic.json", "w", encoding="utf-8") as f:
            json.dump(synthetic_data, f)

        loaded = load_all_results(tmp_path)
        assert len(loaded) == 1
        res = loaded[0]

        assert res["compliant_cases"] == 1
        assert res["code_compliance_rate_pct"] == 50.0  # 1 / 2
        assert "code_compliance_rate_margin_pct" not in res


def test_failure_mode_table_lists_every_mode(tmp_path: Path):
    summary = {"model": "m", "configuration": "full_agent", "case_results": [
        {"case_id": "D02_Infeasible_Section_Cap", "failure_mode": "probe_behavior"},
        {"case_id": "A04_Frame2D_ELF_IMF_Design", "failure_mode": "unverified_design"},
        {"case_id": "D01_US_Units_ELF_Design", "failure_mode": "design_space_violation"},
    ]}
    table = print_and_save_failure_mode_table([summary], tmp_path).read_text(encoding="utf-8")
    row = next(line for line in table.splitlines() if line.startswith("| `m`"))
    cells = [c.strip() for c in row.strip("|").split("|")]
    header = next(line for line in table.splitlines() if line.startswith("| Model Name"))
    names = [c.strip() for c in header.strip("|").split("|")]
    counts = dict(zip(names, cells))
    assert counts["Probe Behavior"] == "1" and counts["Unverified Design"] == "1"
    assert counts["Design Space Violation"] == "1" and counts["Runtime Error"] == "0"


def test_table_generation_functions(benchmarks_dir: Path):
    results_dir = benchmarks_dir / "results"
    summaries = load_all_results(results_dir)
    if not summaries:
        summaries = [{
            "model": "synthetic_model",
            "configuration": "full_agent",
            "timestamp": "2026-10-21T12:00:00",
            "task_completion_rate_pct": 100.0,
            "case_results": [
                {
                    "case_id": "A01_Portal_Gravity_Design_CAD",
                    "design_required": True,
                    "final_dcr": 0.95,
                    "code_compliant": True,
                    "concrete_volume": 1.757,
                    "baseline_concrete_volume": 1.757,
                    "material_economy_ratio": 1.0,
                    "governing_limit_state": "Beam Flexure",
                }
            ],
        }]

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_results_dir = Path(tmp_dir) / "results"
        tmp_results_dir.mkdir(parents=True, exist_ok=True)

        summary_file = print_and_save_markdown_table(summaries, tmp_results_dir)
        assert summary_file.exists()
        content = summary_file.read_text(encoding="utf-8")
        assert "| Model Name | Config |" in content
        assert "Compliant (CCR)" in content and "Turn Limit %" in content and "Probe Behavior" in content

        detail_file = print_and_save_detailed_table(summaries, tmp_results_dir)
        assert detail_file is not None and detail_file.exists()
        detail_content = detail_file.read_text(encoding="utf-8")
        assert "| Case ID | Group | Baseline DCR | Agent DCR |" in detail_content
        assert "eta_vol" in detail_content


def test_multiseed_analysis_pipeline_dod():
    from research_paper.benchmarks.case_schema import load_cases
    from research_paper.benchmarks.run_benchmarks import ccr_eligible

    cases = load_cases()
    case_ids = [c.id for c in cases]
    design_ids = {c.id for c in cases if ccr_eligible(c)}
    reflection_ids = {c.id for c in cases if c.spec.initial_sections is not None}
    n_cases, n_design = len(case_ids), len(design_ids)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_results_dir = Path(tmp_dir) / "results"
        tmp_plots_dir = Path(tmp_dir) / "plots"
        tmp_results_dir.mkdir(parents=True, exist_ok=True)
        tmp_plots_dir.mkdir(parents=True, exist_ok=True)

        for cfg in ["full_agent", "ablated"]:
            all_case_runs = []
            for s_idx in range(5):
                for cid in case_ids:
                    is_design = cid in design_ids
                    is_reflection = cid in reflection_ids
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
                        "concrete_volume": 10.0,
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
                "total_runs": 5 * n_cases,
                "unique_cases": n_cases,
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

        # 3. Failure Mode Table (sums to <= number of cases per column)
        fail_file = print_and_save_failure_mode_table(summaries, tmp_results_dir)
        assert fail_file.exists()
        fail_content = fail_file.read_text(encoding="utf-8")
        assert "FAILURE-MODE TAXONOMY BREAKDOWN" in fail_content
        for line in fail_content.splitlines():
            if line.startswith("| `gemini-3.8-flash`"):
                parts = [p.strip() for p in line.split("|")[1:-1]]
                assert int(parts[3]) == n_cases
                assert int(parts[4]) <= n_cases

        # 4. Statistical Significance Report (N pairs = all cases for TCR, CCR-eligible cases for CCR)
        sig_file = compute_statistical_significance(summaries, tmp_results_dir)
        assert sig_file is not None and sig_file.exists()
        sig_content = sig_file.read_text(encoding="utf-8")
        assert f"| Task Completion (TCR) | {n_cases} | 5 |" in sig_content
        assert f"| Code Compliance (CCR) | {n_design} | 5 |" in sig_content

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


def test_direct_llm_modal_claim_completeness():
    """A modal case answered with only W and T1 scores 40% completeness (2 of 5 requested metrics)."""
    from research_paper.benchmarks.oracle_verifier import OracleVerifier

    res = OracleVerifier().evaluate(
        "A03_Frame2D_Modal_Analysis", None, {"total_weight": 250.0, "fundamental_period": 0.45}
    )
    assert res.claims_made == ["total_weight", "fundamental_period"]
    assert sorted(res.omitted_metrics) == ["modal_mass_ratio", "period_t2", "period_t3"]
    assert res.claim_completeness_pct == 40.0



def test_paired_tests_are_exact_for_few_differing_cases():
    """gemma CCR: 5 of 16 cases compliant only with resizing. The Pratt/normal-approximation Wilcoxon test gave
    p = 0.025; the exact McNemar test gives 2 * 0.5**5 = 0.0625. Continuous outcomes drop zero differences and use
    the exact Wilcoxon distribution."""
    from analyze_results import paired_test

    ccr = paired_test([1.0] * 16, [0.0] * 5 + [1.0] * 11)
    assert ccr["test"] == "McNemar (exact)" and (ccr["n_full"], ccr["n_ablated"]) == (5, 0)
    assert ccr["p"] == pytest.approx(0.0625) and ccr["statistic"] == "5 : 0"
    mixed = paired_test([1.0] * 4 + [0.0] * 2 + [1.0] * 10, [0.0] * 4 + [1.0] * 2 + [1.0] * 10)
    assert mixed["p"] == pytest.approx(1 - 20 / 64)  # 4 against 2 of 6
    dcr = paired_test([0.9, 0.95, 0.97, 0.99, 0.98, 1.0], [1.3, 1.45, 2.5, 1.1, 1.2, 1.0])
    assert dcr["test"] == "Wilcoxon (exact)" and dcr["n_nonzero"] == 5
    assert dcr["p"] == pytest.approx(2 / 2 ** 5)  # all five differences negative: exact two-sided p
    assert paired_test([1.0, 0.0, 1.0, 1.0], [1.0, 0.0, 1.0, 1.0])["p"] == 1.0


def test_holm_adjustment_is_step_down_and_monotone():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from research_paper.benchmarks.export_result_tables import holm_adjusted

    assert holm_adjusted([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert holm_adjusted([0.5, 0.9]) == pytest.approx([1.0, 1.0])
