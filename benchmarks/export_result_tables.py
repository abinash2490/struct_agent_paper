"""
Export the result tables of manuscript Section 5 (Tables 5.3-5.8) from the final results files.

Every value comes from the latest results file of each model and configuration in ``benchmarks/results``, loaded
as ``analyze_results.py`` loads them (setup failures left out, CCR over the compliance-scored design runs).

Usage
-----
    python research_paper/benchmarks/export_result_tables.py
writes research_paper/manuscript/tables/table_5_*.md and copies each table into 05_results_and_discussion.md
between its '<!-- table: <file> -->' and '<!-- /table -->' markers.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research_paper.benchmarks.analyze_results import load_all_results, wilcoxon_tests  # noqa: E402

RESULTS = REPO_ROOT / "research_paper" / "benchmarks" / "results"
TABLES = REPO_ROOT / "research_paper" / "manuscript" / "tables"
SECTION = REPO_ROOT / "research_paper" / "manuscript" / "05_results_and_discussion.md"
MODELS = ["qwen3.5:9b", "minimax-m3.1-flash:cloud", "gemma4:31b-cloud", "deepseek-v4.1-flash:cloud"]
CONFIGS = ["full_agent", "ablated", "direct_llm", "code_gen"]
AGENTS = ("full_agent", "ablated")
PROBES = ("D02", "D03", "D04")
MODES = {
    "runaway_generation": "Runaway generation", "model_construction": "Model construction",
    "missing_tool": "Missing tool", "artifact_missing": "Missing artifact", "schema_fidelity": "Schema fidelity",
    "probe_behavior": "Probe behavior", "design_space_violation": "Design-space violation",
    "unverified_design": "Unverified design", "dcr_non_convergence": "DCR > 1.0", "runtime_error": "Runtime error",
}
CHECKS = {
    "grid_x_match": "Grid, X", "grid_y_match": "Grid, Y", "column_count_match": "Column count",
    "story_heights_match": "Story heights", "sections_match": "Prescribed sections",
    "supports_match": "Support fixity", "materials_match": "Materials",
    "gravity_load_magnitudes_match": "Gravity load totals", "partition_weight_present": "Partition weight",
    "no_unspecified_lateral_loads": "Lateral loads not in the prompt",
    "no_unspecified_load_cases": "Load cases not in the prompt",
    "seismic_parameters_match": "Seismic or record parameters",
    "seismic_load_magnitudes_match": "Seismic force totals", "bearing_pressure_match": "Bearing pressure",
    "design_on_static_envelope": "Design on the static envelope",
    "design_on_spectrum_envelope": "Design on the spectrum envelope",
}


def _cid(record: Dict[str, Any]) -> str:
    return record["case_id"][:3]


def _pct(value: Optional[float]) -> str:
    return "–" if value is None else f"{value:.1f}"


def _row(cells: List[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _summaries() -> Dict[tuple, Dict[str, Any]]:
    return {(s["model"], s["configuration"]): s for s in load_all_results(RESULTS)}


def global_performance(runs: Dict[tuple, Dict[str, Any]]) -> List[str]:
    lines = [_row(["Model", "Configuration", "Runs", "TCR (%)", "CCR", "CHR (%)", "Claims (%)", "PSFR (%)",
                   "Probes", "N_iter", "η_vol", "Turn limit (%)", "Repeats / run", "Runtime (s)"]),
             _row(["---", "---"] + [":---:"] * 12)]
    keys = [(m, c) for m in MODELS for c in CONFIGS] + [("deterministic_heuristic", "heuristic")]
    for key in keys:
        s = runs.get(key)
        if s is None:
            continue
        model, cfg = key
        records = s["case_results"]
        agent = cfg in AGENTS
        claims = sum(r.get("claims_made_count", 0) for r in records)
        probes = [r for r in records if _cid(r) in PROBES]
        n_iter = s.get("avg_convergence_iterations") if cfg == "full_agent" else None
        eta = s.get("avg_material_economy_ratio")
        lines.append(_row([
            f"`{model}`" if cfg == "full_agent" or cfg == "heuristic" else "", f"`{cfg}`", str(len(records)),
            _pct(s.get("task_completion_rate_pct")),
            f"{s['compliant_cases']}/{s['design_cases']} ({s['code_compliance_rate_pct']:.1f})",
            "–" if cfg == "heuristic" or claims == 0 else _pct(s.get("calculation_hallucination_rate_pct")),
            "–" if cfg == "heuristic" else _pct(s.get("claim_completeness_rate_pct")),
            _pct(s.get("prompt_to_schema_fidelity_rate_pct")) if agent else "–",
            "–" if cfg == "heuristic" else f"{sum(1 for r in probes if r.get('behavior_passed'))}/{len(probes)}",
            "–" if n_iter is None else f"{n_iter:.1f}",
            "–" if eta is None else f"{eta:.3f}",
            f"{100.0 * sum(1 for r in records if r.get('turn_limit_reached')) / len(records):.1f}" if agent else "–",
            f"{sum(r.get('repeated_calls', 0) for r in records) / len(records):.2f}" if agent else "–",
            f"{s.get('avg_runtime_sec', 0.0):.0f}",
        ]))
    return lines


def failure_modes(runs: Dict[tuple, Dict[str, Any]]) -> List[str]:
    counts = {key: Counter(r.get("failure_mode") for r in s["case_results"] if r.get("failure_mode"))
              for key, s in runs.items()}
    used = [m for m in MODES if any(c[m] for c in counts.values())]
    lines = [_row(["Model", "Configuration", "Failed / runs"] + [MODES[m] for m in used]),
             _row(["---", "---"] + [":---:"] * (1 + len(used)))]
    keys = [(m, c) for m in MODELS for c in CONFIGS] + [("deterministic_heuristic", "heuristic")]
    for key in keys:
        if key not in runs:
            continue
        model, cfg = key
        records = runs[key]["case_results"]
        c = counts[key]
        lines.append(_row([f"`{model}`" if cfg in ("full_agent", "heuristic") else "", f"`{cfg}`",
                           f"{sum(c.values())}/{len(records)}"] + [str(c[m]) if c[m] else "·" for m in used]))
    return lines


def fidelity_checks(runs: Dict[tuple, Dict[str, Any]]) -> List[str]:
    """Failures of each PSFR check, per model and agent configuration (full / ablated), over the runs scored."""
    fails: Dict[tuple, Counter] = {}
    scored: Dict[tuple, int] = {}
    for model in MODELS:
        for cfg in AGENTS:
            records = runs.get((model, cfg), {}).get("case_results", [])
            details = [r["prompt_to_schema_fidelity_details"] for r in records
                       if r.get("prompt_to_schema_fidelity_passed") is not None
                       and r.get("prompt_to_schema_fidelity_details")]
            scored[(model, cfg)] = len(details)
            fails[(model, cfg)] = Counter(k for d in details for k, v in d.items() if v is False)
    used = [k for k in CHECKS if any(f[k] for f in fails.values())]
    used.sort(key=lambda k: -sum(f[k] for f in fails.values()))
    lines = [_row(["PSFR check"] + [f"`{m}`" for m in MODELS] + ["All"]),
             _row(["---"] + [":---:"] * (len(MODELS) + 1))]
    for k in used:
        cells = [f"{fails[(m, 'full_agent')][k]} / {fails[(m, 'ablated')][k]}" for m in MODELS]
        lines.append(_row([CHECKS[k]] + cells + [str(sum(f[k] for f in fails.values()))]))
    lines.append(_row(["Runs failing PSFR / scored"] + [
        f"{sum(1 for r in runs[(m, 'full_agent')]['case_results'] if r.get('prompt_to_schema_fidelity_passed') is False)}"
        f"/{scored[(m, 'full_agent')]} · "
        f"{sum(1 for r in runs[(m, 'ablated')]['case_results'] if r.get('prompt_to_schema_fidelity_passed') is False)}"
        f"/{scored[(m, 'ablated')]}" for m in MODELS] + [""]))
    return lines


def ablation_tests(runs: Dict[tuple, Dict[str, Any]]) -> List[str]:
    """Paired tests of full_agent against ablated per model on CCR and the governing DCR, with p adjusted by the
    Holm method over all the tests of the table."""
    lines = [_row(["Model", "Metric", "Test", "Pairs", "Pairs that differ", "Full agent", "Ablated", "Δ",
                   "Statistic", "p", "p (Holm)"]),
             _row(["---", "---", "---"] + [":---:"] * 8)]
    names = {"Code Compliance (CCR)": "CCR", "Governing DCR": "Governing DCR"}
    rows = []
    for model in MODELS:
        if (model, "full_agent") not in runs or (model, "ablated") not in runs:
            continue
        rows += [(model, t) for t in wilcoxon_tests(runs[(model, "full_agent")], runs[(model, "ablated")])
                 if t["metric"] in names]
    holm = holm_adjusted([t["p"] for _, t in rows])
    previous = None
    for (model, t), p_holm in zip(rows, holm):
        lines.append(_row([f"`{model}`" if model != previous else "", names[t["metric"]], t["test"], str(t["n"]),
                           str(t["n_nonzero"]), f"{t['full_mean']:.3f}", f"{t['ablated_mean']:.3f}",
                           f"{t['diff']:+.3f}", t["statistic"], _p(t["p"]), _p(p_holm)]))
        previous = model
    return lines


def holm_adjusted(p_values: List[float]) -> List[float]:
    """Holm-Bonferroni adjusted p-values, in the input order."""
    order = sorted(range(len(p_values)), key=lambda i: p_values[i])
    adjusted, running = [0.0] * len(p_values), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(p_values) - rank) * p_values[i]))
        adjusted[i] = running
    return adjusted


def _p(p: float) -> str:
    return "< 0.001" if p < 0.001 else f"{p:.3f}"


def _mark(ok: Optional[bool]) -> str:
    return "–" if ok is None else ("✓" if ok else "✗")


def plan_perception(runs: Dict[tuple, Dict[str, Any]]) -> List[str]:
    """Plan cases: grid lines (X and Y), column count, PSFR, and the oracle's verdict on the delivered design."""
    lines = [_row(["Model", "Configuration", "C03 school (grid · columns · PSFR)",
                   "C04 hostel (grid · columns · PSFR · oracle DCR)",
                   "C05 mall, ft-in (grid · columns · PSFR · oracle DCR)"]),
             _row(["---", "---", ":---:", ":---:", ":---:"])]
    for model in MODELS:
        for cfg in AGENTS:
            records = {_cid(r): r for r in runs.get((model, cfg), {}).get("case_results", [])}
            cells = []
            for case in ("C03", "C04", "C05"):
                r = records.get(case)
                if r is None or not r.get("nodes_count"):
                    reason = (r or {}).get("failure_mode") or "no model"
                    cells.append(f"no model ({MODES.get(reason, reason).lower()})")
                    continue
                d = r.get("prompt_to_schema_fidelity_details") or {}
                grid = None if "grid_x_match" not in d else bool(d.get("grid_x_match") and d.get("grid_y_match"))
                cell = f"{_mark(grid)} · {_mark(d.get('column_count_match'))} · " \
                       f"{_mark(r.get('prompt_to_schema_fidelity_passed'))}"
                if case != "C03":
                    dcr = r.get("final_dcr")
                    cell += " · " + ("–" if dcr is None else f"{dcr:.3f} {_mark(r.get('code_compliant'))}")
                cells.append(cell)
            lines.append(_row([f"`{model}`" if cfg == "full_agent" else "", f"`{cfg}`"] + cells))
    return lines


def probes(runs: Dict[tuple, Dict[str, Any]]) -> List[str]:
    """D01 compliance (oracle DCR) and the probe behavior of D02-D04, per model and configuration."""
    why = {"runaway_generation": "runaway", "runtime_error": "no answer", "model_construction": "no model"}
    lines = [_row(["Model", "Configuration", "D01 US units (DCR)", "D02 infeasible", "D03 missing height",
                   "D04 contradiction"]),
             _row(["---", "---", ":---:", ":---:", ":---:", ":---:"])]
    for model in MODELS:
        for cfg in CONFIGS:
            records = {_cid(r): r for r in runs.get((model, cfg), {}).get("case_results", [])}
            if not records:
                continue
            d01 = records.get("D01")
            if d01 is None:
                cells = ["–"]
            elif d01.get("final_dcr") is None:
                # sections the oracle cannot build (gemma code_gen: 24 × 24 in a model in feet; deepseek: zeros)
                given = bool(d01.get("final_sections"))
                cells = ["✗ (no valid sections)" if given else f"✗ ({why.get(d01.get('failure_mode'), 'no design')})"]
            else:
                cells = [f"{_mark(d01.get('code_compliant'))} ({d01['final_dcr']:.3f})"]
            for case in PROBES:
                r = records.get(case)
                if r is None:
                    cells.append("–")
                elif r.get("behavior_passed"):
                    cells.append("✓")
                else:
                    reason = why.get(r.get("failure_mode"))
                    if case == "D02" and r.get("design_space_violations"):
                        reason = "outside the cap"
                    cells.append("✗" + (f" ({reason})" if reason else ""))
            lines.append(_row([f"`{model}`" if cfg == "full_agent" else "", f"`{cfg}`"] + cells))
    return lines


def sync_section(tables: Dict[str, List[str]]) -> None:
    """Copy each table into Section 5 between '<!-- table: name -->' and '<!-- /table -->'."""
    if not SECTION.exists():  # the manuscript is not part of the public repository
        return
    text = SECTION.read_text(encoding="utf-8")
    for name, lines in tables.items():
        start, end = f"<!-- table: {name} -->", "<!-- /table -->"
        i = text.find(start)
        if i == -1:
            continue
        j = text.find(end, i)
        text = text[:i + len(start)] + "\n" + "\n".join(lines) + "\n" + text[j:]
    SECTION.write_text(text, encoding="utf-8")
    print(f"synced {SECTION}")


def main() -> None:
    runs = _summaries()
    TABLES.mkdir(parents=True, exist_ok=True)
    tables = {
        "table_5_3_global_performance.md": global_performance(runs),
        "table_5_4_failure_modes.md": failure_modes(runs),
        "table_5_5_fidelity_checks.md": fidelity_checks(runs),
        "table_5_6_plan_perception.md": plan_perception(runs),
        "table_5_7_ablation_tests.md": ablation_tests(runs),
        "table_5_8_probes.md": probes(runs),
    }
    for name, lines in tables.items():
        (TABLES / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"wrote {TABLES / name}")
    sync_section(tables)


if __name__ == "__main__":
    main()
