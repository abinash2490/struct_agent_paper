"""
Reference solutions and minimum-volume baselines for the benchmark suite
========================================================================

For every case in ``benchmark_cases.json`` this script computes, with the deterministic oracle:

1. ``reference_solution`` — frozen ground-truth metrics:
   * analysis cases: metrics of the prescribed sections;
   * CAE fixture cases: the CSI SAP2000/ETABS results verified in ``struct_link/examples``
     (the oracle is cross-checked against them);
   * resizing (reflection) cases: the governing DCR of the trial sections;
   * design cases: the metrics of the minimum-volume baseline design.
2. ``baseline_design`` — the minimum-concrete-volume design over the agents' own design space
   (one square column section, one rectangular beam section with b <= h, dimensions on a fixed
   grid, plus any section limits stated in the prompt). Candidates are evaluated in ascending
   order of analytic volume, so the first feasible candidate is the exact optimum on the grid.

Usage
-----
    python research_paper/benchmarks/generate_reference_solutions.py                # dry run, all cases
    python research_paper/benchmarks/generate_reference_solutions.py --write        # update the JSON
    python research_paper/benchmarks/generate_reference_solutions.py --cases A02_Frame2D_Gravity_Design --workers 8
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research_paper.benchmarks.case_schema import (  # noqa: E402
    BaselineDesign,
    BenchmarkCase,
    DesignSummary,
    ReferenceSolution,
    SectionPair,
    load_cases,
    save_cases,
)
from research_paper.benchmarks.oracle_verifier import OracleSolution, OracleVerifier  # noqa: E402

# CSI SAP2000 / ETABS results for fixtures/exported_seismic_frame.{s2k,e2k}
# (struct_link/examples/export_{sap2000,etabs}_seismic_frame.py, verified manually in both programs).
CAE_REFERENCE = {
    "total_weight": 988.96,  # DEAD 288.96 + SuperDead 700.00 kN
    "base_shear": 132.37,    # EQx joint loads, kN
    "fundamental_period": 0.4577,
    "period_t2": 0.4167,
    "period_t3": 0.3874,
}
CAE_SOURCE = "CSI SAP2000 / ETABS (struct_link/examples, manually verified)"

_ORACLE: Optional[OracleVerifier] = None


def _worker_init() -> None:
    global _ORACLE
    _ORACLE = OracleVerifier()


def _evaluate(task: Tuple[str, Tuple[float, ...]]) -> Tuple[Tuple[float, ...], Optional[float], Optional[str]]:
    case_id, dims = task
    sol = _ORACLE.solve(case_id, SectionPair(column=dims[:2], beam=dims[2:]))
    return dims, sol.governing_dcr, sol.error


def _frange(lo: float, hi: float, step: float) -> List[float]:
    n = int(round((hi - lo) / step))
    return [round(lo + i * step, 4) for i in range(n + 1)]


def _member_lengths(oracle: OracleVerifier, case: BenchmarkCase) -> Tuple[float, float]:
    """Total column length and total beam length of the canonical model."""
    proj = oracle.build_project(case, SectionPair(column=(1.0, 1.0), beam=(1.0, 1.0)))
    nodes = {n.id: n for n in proj.model.nodes}
    is_3d = case.spec.geometry.dimension == "3d"
    col_len = beam_len = 0.0
    for e in proj.model.elements:
        a, b = nodes[e.start_node], nodes[e.end_node]
        length = math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))
        vertical = (abs(a.x - b.x) < 1e-6 and abs(a.y - b.y) < 1e-6) if is_3d else abs(a.x - b.x) < 1e-6
        if vertical:
            col_len += length
        else:
            beam_len += length
    return col_len, beam_len


def candidates(oracle: OracleVerifier, case: BenchmarkCase) -> List[Tuple[float, Tuple[float, ...]]]:
    """(volume, (col_b, col_h, beam_b, beam_h)) over the agents' design space, ascending by volume."""
    g = case.design_grid
    col_len, beam_len = _member_lengths(oracle, case)
    out = []
    for c in _frange(g.column_min, g.column_max, g.step):
        for bb in _frange(g.beam_width_min, g.beam_width_max, g.step):
            for bh in _frange(bb, g.beam_depth_max, g.step):
                if case.design_space_violations(SectionPair(column=(c, c), beam=(bb, bh))):
                    continue
                out.append((col_len * c * c + beam_len * bb * bh, (c, c, bb, bh)))
    out.sort()
    return out


def min_volume_search(oracle: OracleVerifier, case: BenchmarkCase, workers: int) -> BaselineDesign:
    cands = candidates(oracle, case)
    batch = max(1, 2 * workers)
    evaluated = 0
    with ProcessPoolExecutor(max_workers=workers, initializer=_worker_init) as pool:
        for start in range(0, len(cands), batch):
            chunk = cands[start:start + batch]
            results = {dims: (dcr, err) for dims, dcr, err in pool.map(_evaluate, [(case.id, d) for _, d in chunk])}
            evaluated += len(chunk)
            for _, dims in chunk:  # ascending volume: first feasible is the grid optimum
                dcr, err = results[dims]
                if err is None and dcr is not None and dcr <= case.deliverables.max_dcr:
                    sections = SectionPair(column=dims[:2], beam=dims[2:])
                    sol = oracle.solve(case.id, sections)
                    return BaselineDesign(
                        feasible=True, sections=sections, concrete_volume=sol.concrete_volume,
                        design=_design_summary(sol), evaluations=evaluated, candidates=len(cands),
                    )
    return BaselineDesign(feasible=False, evaluations=evaluated, candidates=len(cands))


def _design_summary(sol: OracleSolution) -> Optional[DesignSummary]:
    if sol.design is None:
        return None
    d = sol.design
    return DesignSummary(
        governing_dcr=round(d["governing_dcr"], 4),
        governing_member_id=d["governing_member_id"],
        governing_member_type=d["governing_member_type"],
        governing_limit_state=d["governing_limit_state"],
    )


def _rounded(metrics: Dict[str, float]) -> Dict[str, float]:
    return {k: round(float(v), 4) for k, v in metrics.items()}


def reference_for(oracle: OracleVerifier, case: BenchmarkCase) -> Optional[ReferenceSolution]:
    stamp = f"oracle_verifier.py ({date.today().isoformat()})"
    if case.evaluation.withheld:
        return None  # the prompt does not determine a unique structure
    if case.spec.cae is not None:
        sol = oracle.solve(case.id)
        metrics = {k: CAE_REFERENCE[k] for k in case.evaluation.required_metrics if k in CAE_REFERENCE}
        if "governing_dcr" in case.evaluation.required_metrics:
            metrics["governing_dcr"] = round(sol.governing_dcr, 4)
        return ReferenceSolution(
            source=CAE_SOURCE + ("" if "governing_dcr" not in metrics else f"; DCR from {stamp}"),
            metrics=metrics, design=_design_summary(sol),
        )
    if case.spec.sections is not None:
        sol = oracle.solve(case.id)
        _raise_on_error(sol)
        return ReferenceSolution(source=stamp, sections=case.spec.sections, metrics=_rounded(sol.metrics),
                                 concrete_volume=sol.concrete_volume)
    baseline = case.baseline_design
    initial = None
    if case.spec.initial_sections is not None:
        trial = oracle.solve(case.id, case.spec.initial_sections)
        _raise_on_error(trial)
        initial = round(trial.governing_dcr, 4)
    if baseline is None or not baseline.feasible:
        return ReferenceSolution(source=stamp, initial_dcr=initial) if initial is not None else None
    sol = oracle.solve(case.id, baseline.sections)
    return ReferenceSolution(source=stamp, sections=baseline.sections, metrics=_rounded(sol.metrics),
                             design=_design_summary(sol), initial_dcr=initial, concrete_volume=sol.concrete_volume)


def _raise_on_error(sol: OracleSolution) -> None:
    if sol.error:
        raise RuntimeError(f"{sol.case_id}: {sol.error}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cases", nargs="*", help="Case IDs (default: all)")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--skip-search", action="store_true", help="Reuse baseline_design already in the JSON")
    parser.add_argument("--write", action="store_true", help="Write results into benchmark_cases.json")
    args = parser.parse_args()

    oracle = OracleVerifier()
    cases = load_cases()
    selected = set(args.cases or [c.id for c in cases])
    for case in cases:
        if case.id not in selected:
            continue
        t0 = time.perf_counter()
        if case.deliverables.design == "design" and not args.skip_search:
            case.baseline_design = min_volume_search(oracle, case, args.workers)
        case.reference_solution = reference_for(oracle, case)
        b, r = case.baseline_design, case.reference_solution
        base = "—" if b is None else (
            f"INFEASIBLE after {b.evaluations}/{b.candidates}" if not b.feasible else
            f"col {b.sections.column} beam {b.sections.beam} V={b.concrete_volume} DCR={b.design.governing_dcr} "
            f"({b.design.governing_limit_state}, {b.evaluations}/{b.candidates} evals)"
        )
        print(f"{case.id:40s} {time.perf_counter() - t0:7.1f}s | baseline: {base}", flush=True)
        if r is not None:
            print(f"    reference: {r.metrics} initial_dcr={r.initial_dcr}", flush=True)

    if args.write:
        save_cases(cases)
        print("benchmark_cases.json updated.")


if __name__ == "__main__":
    main()
