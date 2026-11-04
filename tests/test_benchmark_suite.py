"""
Consistency tests for the benchmark suite (benchmark_cases.json).

Run from the repository root:
    pytest research_paper/tests -q
    BENCHMARK_SLOW=1 pytest research_paper/tests -q   # also re-solves time-history references
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research_paper.benchmarks.benchmark_utils import (  # noqa: E402
    evaluate_prompt_to_schema_fidelity,
    parse_numerical_claims_from_text,
)
from research_paper.benchmarks.case_schema import (  # noqa: E402
    SectionPair,
    difficulty_label,
    difficulty_score,
    load_cases,
)
from research_paper.benchmarks.generate_reference_solutions import CAE_REFERENCE, candidates  # noqa: E402
from research_paper.benchmarks.oracle_verifier import OracleVerifier  # noqa: E402

CASES = load_cases()
BY_ID = {c.id: c for c in CASES}
SLOW = os.environ.get("BENCHMARK_SLOW") == "1"


@pytest.fixture(scope="module")
def oracle() -> OracleVerifier:
    return OracleVerifier()


def _mentions(prompt: str, value: float) -> bool:
    """True when the prompt states ``value`` (any trailing-zero formatting, thousands separators allowed)."""
    text = prompt.replace(",", "")
    for m in re.finditer(r"\d+(?:\.\d+)?", text):
        if abs(float(m.group(0)) - value) <= 1e-9 * max(1.0, abs(value)):
            return True
    return False


# -----------------------------------------------------------------------------
# Structure of the suite
# -----------------------------------------------------------------------------
def test_suite_composition():
    assert len(CASES) == 27
    assert len(BY_ID) == len(CASES), "case IDs must be unique"
    groups = [c.group for c in CASES]
    assert {g: groups.count(g) for g in set(groups)} == {"A_2D": 8, "B_3D": 9, "C_Multimodal": 6, "D_Robustness": 4}


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_difficulty_follows_rubric(case):
    assert case.difficulty.score == difficulty_score(case)
    assert case.difficulty.label == difficulty_label(case.difficulty.score)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_referenced_files_exist(case):
    paths = [case.spec.plan_image, case.spec.cae.file if case.spec.cae else None]
    if case.spec.seismic is not None and case.spec.seismic.ground_motion is not None:
        paths.append(case.spec.seismic.ground_motion.file)
    for p in filter(None, paths):
        assert (REPO_ROOT / p).exists(), p
        assert p in case.prompt or case.spec.plan_image == p, f"{p} is not named in the prompt"


def test_expected_tools_are_agent_tools():
    from struct_agent.llm.schemas import get_tool_schemas

    names = {t["function"]["name"] for t in get_tool_schemas()}
    for case in CASES:
        unknown = set(case.evaluation.expected_tools) - names
        assert not unknown, f"{case.id}: unknown tools {unknown}"


# -----------------------------------------------------------------------------
# Prompt <-> spec consistency
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("case", [c for c in CASES if c.spec.geometry is not None], ids=lambda c: c.id)
def test_prompt_states_the_spec(case):
    spec, prompt = case.spec, case.prompt
    numbers = []
    if spec.plan_image is None:  # plan geometry comes from the drawing
        if "bay_widths_x" not in case.evaluation.withheld:
            numbers += spec.geometry.bay_widths_x + (spec.geometry.bay_widths_y or [])
    if "story_heights" not in case.evaluation.withheld:
        numbers += spec.geometry.story_heights
    for s in (spec.sections, spec.initial_sections):
        if s is not None:
            numbers += [*s.column, *s.beam]
    us = spec.units.startswith("kip")
    loads = spec.loads
    numbers += [loads.superimposed_dead * (1000 if us else 1), loads.live * (1000 if us else 1)]
    if loads.partition_weight is not None:
        numbers.append(loads.partition_weight * (1000 if us else 1))
    if loads.tributary_width is not None:
        numbers.append(loads.tributary_width)
    if spec.section_limits is not None:
        numbers += [spec.section_limits.max_width, spec.section_limits.max_depth]
    seis = spec.seismic
    if seis is not None:
        numbers += [v for v in (seis.sds, seis.sd1, seis.s1, seis.r_factor) if v is not None]
        numbers.append(seis.importance_factor) if seis.procedure != "tha" else None
    missing = [v for v in numbers if not _mentions(prompt, v)]
    assert not missing, f"{case.id}: prompt does not state {missing}"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_report_clause_requests_every_required_metric(case):
    keywords = {
        "total_weight": r"total dead load W",
        "base_shear": r"base shear",
        "fundamental_period": r"\bT1\b",
        "period_t2": r"\bT2\b",
        "period_t3": r"\bT3\b",
        "modal_mass_ratio": r"mass participation",
        "peak_roof_displacement": r"roof displacement",
        "max_base_reaction": r"support reaction",
        "governing_dcr": r"governing DCR",
    }
    for metric in case.evaluation.required_metrics:
        assert re.search(keywords[metric], case.prompt), f"{case.id}: prompt does not ask for {metric}"


# -----------------------------------------------------------------------------
# Baselines and frozen references
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("case", [c for c in CASES if c.deliverables.design == "design"], ids=lambda c: c.id)
def test_baseline_design(case, oracle):
    base = case.baseline_design
    assert base is not None, "run generate_reference_solutions.py --write"
    if case.taxonomy.probe == "infeasible":
        assert not base.feasible and base.evaluations == base.candidates
        assert case.reference_solution is None, "no feasible sections, so no reference design"
        return
    assert base.feasible
    assert case.design_space_violations(base.sections) == []
    sol = oracle.solve(case.id, base.sections)
    assert sol.governing_dcr <= case.deliverables.max_dcr
    assert sol.concrete_volume == pytest.approx(base.concrete_volume, abs=1e-3)


@pytest.mark.parametrize("case_id", ["A01_Portal_Gravity_Design_CAD", "A04_Frame2D_ELF_IMF_Design"])
def test_baseline_is_the_grid_optimum(case_id, oracle):
    """Every candidate with less volume than the baseline violates the strength checks."""
    case = BY_ID[case_id]
    cands = candidates(oracle, case)
    best = case.baseline_design.sections
    index = next(i for i, (_, d) in enumerate(cands) if d == (*best.column, *best.beam))
    for _, dims in cands[:index]:
        sol = oracle.solve(case_id, SectionPair(column=dims[:2], beam=dims[2:]))
        assert sol.governing_dcr > case.deliverables.max_dcr


@pytest.mark.parametrize(
    "case",
    [c for c in CASES if not c.evaluation.withheld and c.taxonomy.probe != "infeasible"],
    ids=lambda c: c.id,
)
def test_reference_solution_reproduces(case, oracle):
    ref = case.reference_solution
    assert ref is not None, "run generate_reference_solutions.py --write"
    if case.spec.analysis == "tha" and not SLOW:
        pytest.skip("time-history reference (set BENCHMARK_SLOW=1)")
    sol = oracle.solve(case.id, ref.sections)
    assert sol.error is None
    tol = 5e-3 if case.spec.cae is not None else 1e-3  # CSI values vs. our solvers
    for metric, value in ref.metrics.items():
        assert sol.metrics[metric] == pytest.approx(value, rel=tol), metric
    if ref.initial_dcr is not None:
        trial = oracle.solve(case.id, case.spec.initial_sections)
        assert trial.governing_dcr == pytest.approx(ref.initial_dcr, rel=1e-3)
        assert ref.initial_dcr > 1.0, "trial sections must be overstressed"


def test_cae_reference_is_the_csi_result():
    for cid in ("C01_SAP2000_Import_Verify_Export", "C02_ETABS_Import_Design_Check_Export"):
        ref = BY_ID[cid].reference_solution
        for metric, value in ref.metrics.items():
            if metric in CAE_REFERENCE:
                assert value == CAE_REFERENCE[metric]


# -----------------------------------------------------------------------------
# Scoring machinery
# -----------------------------------------------------------------------------
def test_oracle_claim_scoring(oracle):
    case = BY_ID["A03_Frame2D_Modal_Analysis"]
    truth = case.reference_solution.metrics
    exact = oracle.evaluate(case.id, None, dict(truth))
    assert exact.calculation_hallucination_rate_pct == 0.0 and exact.claim_completeness_pct == 100.0

    wrong = dict(truth, fundamental_period=truth["fundamental_period"] * 1.5)
    wrong.pop("period_t3")
    res = oracle.evaluate(case.id, None, wrong)
    assert res.hallucinated_metrics == ["fundamental_period"]
    assert res.omitted_metrics == ["period_t3"]
    assert res.calculation_hallucination_rate_pct == pytest.approx(25.0)


def test_oracle_rejects_design_space_violations(oracle):
    case = BY_ID["A02_Frame2D_Gravity_Design"]
    base = case.baseline_design.sections
    rectangular = SectionPair(column=(base.column[0], base.column[1] + 0.05), beam=base.beam)
    res = oracle.evaluate(case.id, rectangular)
    assert res.code_compliant is False
    assert "column section is not square" in res.design_space_violations


def test_grid_values_given_to_two_decimals_are_on_the_grid():
    """D01 (feet, 2 in steps): 16 in written as 1.33 ft is on the grid; 15 in (1.25 ft) is not."""
    case = BY_ID["D01_US_Units_ELF_Design"]
    off_grid = "dimensions are not multiples of 0.166667"
    assert off_grid not in case.design_space_violations(SectionPair(column=(1.33, 1.33), beam=(1.0, 1.67)))
    assert off_grid in case.design_space_violations(SectionPair(column=(1.25, 1.25), beam=(1.0, 1.67)))
    # nemotron's 10 in beams (0.8333 ft) meet the 10 in minimum width they round to
    assert case.design_space_violations(SectionPair(column=(1.8333, 1.8333), beam=(0.8333, 1.5))) == []
    assert "beam narrower than the 0.833333 minimum" in case.design_space_violations(
        SectionPair(column=(1.8333, 1.8333), beam=(0.6667, 1.5)))


def test_claim_parser_converts_units():
    text = ("The total dead load W is 120.5 kips, the base shear Vb = 10.3 kip, T1 = 0.42 s, "
            "the peak roof displacement is 25 mm and the governing DCR is 0.97.")
    si = parse_numerical_claims_from_text(text, "kN, m")
    assert si["total_weight"] == pytest.approx(120.5 * 4.448222, rel=1e-5)
    assert si["peak_roof_displacement"] == pytest.approx(0.025)
    us = parse_numerical_claims_from_text(text, "kip, ft")
    assert us["base_shear"] == pytest.approx(10.3)
    assert us["fundamental_period"] == 0.42 and us["governing_dcr"] == 0.97


def test_claim_parser_skips_pressures_citations_and_markdown():
    """Agent summaries (pilot runs): a floor pressure is not W, and ACI 318-25 / §22.4 are not the DCR."""
    text = (
        "| **Gravity loads** | Floor dead load = 5.1 kPa, Office live load = 3.12 kPa over a 5.0 m width |\n"
        "- **Total dead load (W)** – includes floor dead load + member self‑weight: **1472.06 kN**\n"
        "| Governing demand‑capacity ratio, **DCR** (column axial‑flexure, ACI 318‑25 §22.4) | **1.138** | – |\n"
        "| X‑direction base shear, **Vb** (from RSA, ELF‑scaled, ASCE 7‑22 §12.9.1.4) | **193.536** | kN |\n"
        "| Fundamental period, **T₁** (first mode, X‑direction) | **1.020** | s |\n"
    )
    claims = parse_numerical_claims_from_text(text, "kN, m")
    assert claims["total_weight"] == pytest.approx(1472.06)
    assert claims["governing_dcr"] == pytest.approx(1.138)
    assert claims["base_shear"] == pytest.approx(193.536)
    assert claims["fundamental_period"] == pytest.approx(1.020)
    # A following ordinary word is not a unit; a line load is not a force
    assert parse_numerical_claims_from_text("the governing DCR is 0.97 and all members pass")["governing_dcr"] == 0.97
    assert "total_weight" not in parse_numerical_claims_from_text("total dead load W = 25.5 kN/m along the beam")
    # Identifiers are not values, and LaTeX units count (gemma A06 final message)
    roof = parse_numerical_claims_from_text(
        "### 4. Peak Roof Displacement\nThe peak relative displacement of the roof node (Node 13) with respect "
        "to the fixed base.\n- **Peak Roof Displacement:** $71.08\\text{ mm}$\n"
        "- **Fundamental Period ($T_1$):** $0.498\\text{ s}$", "kN, m")
    assert roof["peak_roof_displacement"] == pytest.approx(0.07108)
    assert roof["fundamental_period"] == pytest.approx(0.498)


@pytest.mark.parametrize("case", [c for c in CASES if c.spec.geometry is not None and c.spec.analysis != "tha"],
                         ids=lambda c: c.id)
def test_canonical_model_passes_schema_fidelity(case, oracle):
    sections = case.spec.sections or (case.baseline_design.sections if case.baseline_design and case.baseline_design.feasible
                                      else SectionPair(column=(0.4, 0.4), beam=(0.3, 0.5)))
    if case.spec.units.startswith("kip"):
        sections = SectionPair(column=(1.5, 1.5), beam=(1.0, 2.0))
    project = oracle.build_project(case, sections)
    seis = case.spec.seismic
    calls = []
    designs = case.deliverables.design != "none" or case.spec.initial_sections is not None
    design_basis = {"cracked_sections": True, "second_order": True} if designs else {}
    if seis is not None:
        tool = {"elf": "apply_lateral_loads", "rsa_code": "run_response_spectrum",
                "rsa_record": "run_response_spectrum"}[seis.procedure]
        args = {"sds": seis.sds, "sd1": seis.sd1, "s1": seis.s1, "r_factor": seis.r_factor,
                "importance_factor": seis.importance_factor, "system_type": seis.system}
        if seis.ground_motion is not None:
            args["ground_motion"] = seis.ground_motion.file
        if tool == "run_response_spectrum":
            args.update(design_basis, analysis_case_id="RSA",
                        direction="both" if len(seis.directions) > 1 else seis.directions[0])
        calls.append((tool, args))
        if seis.procedure == "elf":
            calls.append(("generate_load_combinations", {
                "sds": seis.sds if seis.vertical_effect else None,
                "orthogonal_seismic": bool(seis.orthogonal_combination)}))
    if designs and case.spec.analysis != "rsa":
        calls.append(("run_analysis", {"analysis_case_id": "Static", **design_basis}))
    if designs:
        calls.append(("run_design", {"allowable_bearing_pressure": case.spec.foundation.allowable_bearing_pressure}))
    from research_paper.benchmarks.benchmark_utils import gravity_load_totals

    reference = gravity_load_totals(project, case.spec.units)
    ok, details = evaluate_prompt_to_schema_fidelity(project, case, calls, reference)
    assert ok, details
    # Floor loads 1000x too small (gemma D01: 0.105 entered with pressure_unit='psf') fail the magnitude check
    wrong = {**reference, "dead": reference["dead"] * 1.5}
    assert evaluate_prompt_to_schema_fidelity(project, case, calls, wrong)[1]["gravity_load_magnitudes_match"] is False
    # Another concrete, or a bearing pressure the prompt does not state, fails
    assert details["materials_match"] is True
    if designs:
        other = [(n, {**a, "allowable_bearing_pressure": 200.0} if n == "run_design" else a)
                 for n, a in calls]
        assert evaluate_prompt_to_schema_fidelity(project, case, other, reference)[1]["bearing_pressure_match"] is False
    concrete = next(m for m in project.model.materials if m.type == "concrete")
    concrete.fc *= 1.2
    assert evaluate_prompt_to_schema_fidelity(project, case, calls, reference)[1]["materials_match"] is False
    if seis is not None and seis.procedure == "elf" and seis.vertical_effect:
        # Combinations without the vertical seismic effect do not reproduce the spec
        no_ev = [(n, {**a, "sds": None}) if n == "generate_load_combinations" else (n, a) for n, a in calls]
        assert evaluate_prompt_to_schema_fidelity(project, case, no_ev)[1]["load_combinations_match"] is False
    if designs:
        # A first-order, gross-section analysis does not satisfy the design analysis basis
        gross = [(name, {k: v for k, v in a.items() if k not in ("cracked_sections", "second_order")}) for name, a in calls]
        ok_gross, details_gross = evaluate_prompt_to_schema_fidelity(project, case, gross)
        assert not ok_gross and details_gross["design_analysis_basis_match"] is False
    if designs and case.spec.analysis == "rsa":
        # gemma B05 (ablated): the final design check used a static ELF envelope run after the spectra
        static = calls[:-1] + [("run_analysis", {"analysis_case_id": "Static_Env", **design_basis}),
                               ("run_design", {"analysis_case_id": "Static_Env"})]
        assert evaluate_prompt_to_schema_fidelity(project, case, static)[1]["design_on_spectrum_envelope"] is False
        assert evaluate_prompt_to_schema_fidelity(
            project, case, calls[:-1] + [("run_design", {"analysis_case_id": "RSA_design"})]
        )[1]["design_on_spectrum_envelope"] is True
        if len(seis.directions) > 1:
            one_way = [(n, {**a, "direction": "x"}) if n == "run_response_spectrum" else (n, a) for n, a in calls]
            assert evaluate_prompt_to_schema_fidelity(project, case, one_way)[1]["design_on_spectrum_envelope"] is False


def test_partition_weight_compared_only_where_it_enters_the_seismic_weight(oracle):
    from research_paper.benchmarks.benchmark_utils import gravity_load_totals

    # A02 (gravity only): the tool's default office PartitionWeight case (gemma A02) is in no combination
    gravity = BY_ID["A02_Frame2D_Gravity_Design"]
    project = oracle.build_project(gravity, gravity.baseline_design.sections)
    reference = gravity_load_totals(project, gravity.spec.units)
    assert reference["partition"] == 0.0
    details = evaluate_prompt_to_schema_fidelity(project, gravity, [], {**reference, "partition": 108.0})[1]
    assert details["gravity_load_magnitudes_match"] is True
    # A04 (ELF): the partition weight is part of the seismic weight and is compared
    seismic = BY_ID["A04_Frame2D_ELF_IMF_Design"]
    project = oracle.build_project(seismic, seismic.baseline_design.sections)
    reference = gravity_load_totals(project, seismic.spec.units)
    assert reference["partition"] > 0.0
    wrong = {**reference, "partition": 0.0}
    assert evaluate_prompt_to_schema_fidelity(project, seismic, [], wrong)[1]["gravity_load_magnitudes_match"] is False


def test_s1_is_compared_only_where_eq_12_8_7_applies(oracle):
    """nemotron omitted S1 = 0.11 / 0.5 g, which changes no result (Eq. 12.8-7 needs S1 >= 0.6 g)."""
    case = BY_ID["A04_Frame2D_ELF_IMF_Design"]
    project = oracle.build_project(case, case.baseline_design.sections)
    s = case.spec.seismic
    no_s1 = [("apply_lateral_loads", {"sds": s.sds, "sd1": s.sd1, "r_factor": s.r_factor,
                                      "importance_factor": s.importance_factor, "system_type": s.system})]
    assert evaluate_prompt_to_schema_fidelity(project, case, no_s1)[1]["seismic_parameters_match"] is True
    high = case.model_copy(deep=True)
    high.spec.seismic.s1 = 0.75
    assert evaluate_prompt_to_schema_fidelity(project, high, no_s1)[1]["seismic_parameters_match"] is False


def test_schema_fidelity_reads_the_final_models_loading(oracle):
    """nemotron (ablated) rebuilt models after its last generate_load_combinations / apply_lateral_loads calls:
    the final model must itself hold the combinations and the seismic load cases."""
    case = BY_ID["A04_Frame2D_ELF_IMF_Design"]
    complete = oracle.build_project(case, case.baseline_design.sections)
    details = evaluate_prompt_to_schema_fidelity(complete, case, [])[1]
    assert details["load_combinations_present"] is True and details["seismic_loads_present"] is True
    no_combinations = oracle.build_project(case, case.baseline_design.sections)
    no_combinations.model.load_combinations = []
    assert evaluate_prompt_to_schema_fidelity(no_combinations, case, [])[1]["load_combinations_present"] is False
    no_seismic = oracle.build_project(case, case.baseline_design.sections)
    no_seismic.model.load_cases = [lc for lc in no_seismic.model.load_cases if not lc.id.upper().startswith("EQ")]
    assert evaluate_prompt_to_schema_fidelity(no_seismic, case, [])[1]["seismic_loads_present"] is False


def test_schema_fidelity_detects_wrong_geometry(oracle):
    case = BY_ID["A02_Frame2D_Gravity_Design"]
    wrong = case.model_copy(deep=True)
    wrong.spec.geometry.bay_widths_x = [6.0, 5.0, 4.0]
    project = oracle.build_project(wrong, case.baseline_design.sections)
    ok, details = evaluate_prompt_to_schema_fidelity(project, case, [])
    assert not ok and details["grid_x_match"] is False


def test_schema_fidelity_detects_sections_other_than_prescribed(oracle):
    """gemma B01 left out the beam size: the tool's default 0.30 x 0.50 m beam replaced the prompt's 0.30 x 0.55 m."""
    case = BY_ID["B01_Frame3D_Gravity_Analysis"]
    assert evaluate_prompt_to_schema_fidelity(oracle.build_project(case, case.spec.sections), case, [])[1]["sections_match"]
    project = oracle.build_project(case, SectionPair(column=(0.45, 0.45), beam=(0.30, 0.50)))
    ok, details = evaluate_prompt_to_schema_fidelity(project, case, [])
    assert not ok and details["sections_match"] is False


def test_gravity_cases_reject_unspecified_lateral_loads(oracle):
    """qwen A01 (seed 4) added ELF loads with an invented SDS to a gravity-only case and designed for them."""
    from struct_agent.tools.loads import apply_lateral_loads

    case = BY_ID["A01_Portal_Gravity_Design_CAD"]
    project = oracle.build_project(case, case.baseline_design.sections)
    assert evaluate_prompt_to_schema_fidelity(project, case, [])[1]["no_unspecified_lateral_loads"] is True
    assert apply_lateral_loads(project, sds=0.4, sd1=0.2, r_factor=8.0, direction="x").ok
    assert evaluate_prompt_to_schema_fidelity(project, case, [])[1]["no_unspecified_lateral_loads"] is False


def test_static_designs_are_checked_on_a_static_envelope(oracle):
    """qwen C06 (seeds 0, 1): the ELF design was checked on a response spectrum envelope."""
    case = BY_ID["C06_Pinned_Base_ELF_Design_CAD"]
    project = oracle.build_project(case, case.baseline_design.sections)
    static = [("run_analysis", {"analysis_case_id": "S", "cracked_sections": True, "second_order": True})]
    rsa = static + [("run_response_spectrum", {"analysis_case_id": "R", "direction": "both"})]

    def basis(calls):
        return evaluate_prompt_to_schema_fidelity(project, case, calls)[1]["design_on_static_envelope"]

    assert basis(static + [("run_design", {})]) is True
    assert basis(rsa + [("run_design", {"analysis_case_id": "R_design"})]) is False
    assert basis(rsa + [("run_design", {"analysis_case_id": "S"})]) is True
    assert basis(rsa + [("run_design", {"analysis_case_id": "envelope"})]) is True  # the tool's alias of 'S'
    one_combination = [("run_analysis", {"analysis_case_id": "G", "load_case_id": "COMB_1.2D+1.6L"}), ("run_design", {})]
    assert basis(one_combination) is False


def test_checks_of_the_final_model_are_judged_not_only_the_last_one(oracle):
    """deepseek B08: after the last resize, the design was checked on the full envelope, then a one-combination
    footing diagnostic was run; deepseek B04 and minimax ablated B04 checked at the stated bearing pressure, then
    probed others. A check of the final model on the specified basis counts; a check of an earlier model does not."""
    case = BY_ID["C06_Pinned_Base_ELF_Design_CAD"]
    project = oracle.build_project(case, case.baseline_design.sections)
    q = case.spec.foundation.allowable_bearing_pressure
    envelope = [("run_analysis", {"analysis_case_id": "S", "cracked_sections": True, "second_order": True}),
                ("run_design", {"analysis_case_id": "S", "allowable_bearing_pressure": q})]
    diagnostic = [("run_analysis", {"analysis_case_id": "U", "load_case_id": "COMB_0.66D-1.0E"}),
                  ("run_design", {"analysis_case_id": "U", "allowable_bearing_pressure": q})]
    sensitivity = [("run_design", {"analysis_case_id": "S", "allowable_bearing_pressure": 1000.0})]
    resize = [("modify_project", {"sections": [{"id": "BEAM", "h": 0.6}]})]

    def details(calls):
        return evaluate_prompt_to_schema_fidelity(project, case, calls)[1]

    assert details(envelope + diagnostic)["design_on_static_envelope"] is True
    assert details(envelope + sensitivity)["bearing_pressure_match"] is True
    assert details(envelope + sensitivity)["bearing_pressure"] == q
    # Checks before the final model change are of an earlier model
    assert details(envelope + resize + diagnostic)["design_on_static_envelope"] is False
    assert details(envelope + resize + envelope[1:] + sensitivity)["bearing_pressure_match"] is True
    assert details(envelope + resize + sensitivity)["bearing_pressure_match"] is False
    # minimax B09: cracked, second-order analyses earlier, but the final model checked on a gross-section analysis
    gross = [("run_analysis", {"analysis_case_id": "G"}),
             ("run_design", {"analysis_case_id": "G", "allowable_bearing_pressure": q})]
    assert details(envelope)["design_analysis_basis_match"] is True
    assert details(envelope + resize + gross)["design_analysis_basis_match"] is False


def test_conventional_concrete_unit_weight_passes(oracle):
    """deepseek B01, B07, C03: 24 kN/m3 for the stated 2,400 kg/m3 (g taken as 10 m/s2, 1.97 % high) is the
    prompt's concrete; a unit weight 3 % off is not."""
    from research_paper.benchmarks.benchmark_utils import materials_match

    case = BY_ID["B01_Frame3D_Gravity_Analysis"]
    project = oracle.build_project(case, case.spec.sections)
    concrete = next(m for m in project.model.materials if m.type == "concrete")
    exact = case.spec.materials.density_kg_m3 * 9.80665 / 1000.0
    for unit_weight, ok in ((24.0, True), (exact * 1.03, False)):
        concrete.unit_weight = unit_weight
        assert materials_match(project, case)[0] is ok, unit_weight


def test_design_check_tracker_detects_checks_of_an_earlier_model():
    """run_design checks a stored analysis; after resizing without a new analysis it mixes new capacities with
    old demands (nemotron B04, seed 3). The current run_design refuses such a check; the tracker still judges a
    model changed after the final check."""
    from research_paper.benchmarks.audit_results import replay
    from research_paper.benchmarks.benchmark_utils import DesignCheckTracker

    frame = {"num_bays": 1, "num_stories": 1, "bay_width": 5.0, "story_height": 3.0, "fc": 27580.0, "col_b": 0.3, "col_h": 0.3, "beam_b": 0.25, "beam_h": 0.35}
    start = [{"tool": "create_frame_model", "args": frame},
             {"tool": "apply_gravity_loads", "args": {"occupancy": "office", "superimposed_dead": 5.1, "custom_live_load": 3.12,
                                                      "tributary_width": 4.0}},
             {"tool": "generate_load_combinations", "args": {}},
             {"tool": "run_analysis", "args": {"analysis_case_id": "S1"}},
             {"tool": "run_design", "args": {"analysis_case_id": "S1", "design_case_id": "D"}},
             {"tool": "modify_project", "args": {"sections": [{"id": "COL", "b": 0.5, "h": 0.5}]}}]
    reanalysis = {"tool": "run_analysis", "args": {"analysis_case_id": "S2"}}

    def current(log):
        checks = DesignCheckTracker()
        project, _ = replay({"configuration": "full_agent", "tool_log": log}, checks)
        return checks.checks_current, checks.design_current(project)

    assert current(start[:5]) == ([True], True)
    assert current(start) == ([True], False)  # resized after the check
    # run_design refuses the stale analysis, so the earlier check stays the last one
    assert current(start + [{"tool": "run_design", "args": {"analysis_case_id": "S1", "design_case_id": "D"}}]) == ([True], False)
    assert current(start + [reanalysis, {"tool": "run_design", "args": {"analysis_case_id": "S2", "design_case_id": "D"}}])[1] is True
    # 'envelope' is the latest static envelope
    assert current(start + [reanalysis, {"tool": "run_design", "args": {"analysis_case_id": "envelope", "design_case_id": "D"}}])[1] is True
    # An unchanged resize (same dimensions) leaves the check current
    same = {"tool": "modify_project", "args": {"sections": [{"id": "COL", "b": 0.3, "h": 0.3}]}}
    assert current(start[:5] + [same])[1] is True


def test_context_window_failures_are_not_model_failures():
    """A 16k Ollama window ended 103 of 135 qwen3.5:9b runs with an empty, length-truncated response."""
    from research_paper.benchmarks.run_benchmarks import classify_failure, context_limits

    calls = [{"prompt_tokens": 12306, "finish_reason": "tool_calls", "tool_calls": 1},
             {"prompt_tokens": 15800, "finish_reason": "length", "tool_calls": 0}]
    limits = context_limits(calls)
    assert limits["final_response_truncated"] and limits["truncated_responses"] == 1 and not limits["prompt_truncations"]
    assert context_limits([{"prompt_tokens": 19639}, {"prompt_tokens": 8194}])["prompt_truncations"] == 1
    # The tool-free report turn after an exhausted turn budget drops the tool schemas, not the conversation
    wrap_up = [{"prompt_tokens": 28492, "tools_offered": True}, {"prompt_tokens": 19110, "tools_offered": False}]
    assert context_limits(wrap_up)["prompt_truncations"] == 0
    record = {"configuration": "full_agent", "success": False, "design_task": "design", "code_compliant": False,
              "behavior_passed": None, "nodes_count": 0, **limits}
    assert classify_failure(record) == "context_limit"
    assert classify_failure({**record, "final_response_truncated": False}) == "model_construction"
    # An Ollama crash ended qwen C03 and refused C06: the server failed, not the model
    assert classify_failure({**record, "final_response_truncated": False, "provider_error": True}) == "provider_error"


def test_a_response_at_the_output_cap_is_the_models_failure():
    """qwen3.5:9b thought for 30 minutes without answering (code_gen B03, C03, C04): a response that reaches
    --max-output-tokens is a runaway, not a context window or server failure, and is not re-run."""
    from research_paper.benchmarks.run_benchmarks import classify_failure, context_limits

    capped = [{"prompt_tokens": 12306, "finish_reason": "tool_calls", "tool_calls": 1},
              {"prompt_tokens": 15800, "completion_tokens": 48000, "finish_reason": "length", "tool_calls": 0}]
    limits = context_limits(capped, 48000)
    assert limits["final_response_capped"] and not limits["final_response_truncated"] and limits["output_cap_hits"] == 1
    record = {"configuration": "full_agent", "success": False, "design_task": "design", "code_compliant": False,
              "behavior_passed": None, "nodes_count": 3, **limits}
    assert classify_failure(record) == "runaway_generation"
    # Cut off after a few thousand tokens: the context window ended it
    short = [{**capped[0]}, {**capped[1], "completion_tokens": 9000}]
    assert context_limits(short, 48000)["final_response_truncated"]
    assert classify_failure({**record, **context_limits(short, 48000)}) == "context_limit"
    # qwen3.5:9b's 64k window cuts a runaway before a 128k cap: still the model's runaway
    window = [{**capped[0]}, {**capped[1], "completion_tokens": 41000}]
    assert context_limits(window, 131072)["final_response_capped"]
    assert context_limits(window)["final_response_capped"]  # also without a cap


def test_agent_compliance_requires_a_check_of_the_delivered_sections(oracle):
    """A compliant oracle result counts only if the agent ran run_design after its last model change."""
    from research_paper.benchmarks.run_benchmarks import build_record, classify_failure

    case = BY_ID["A02_Frame2D_Gravity_Design"]
    res = oracle.evaluate(case.id, case.baseline_design.sections)
    assert res.code_compliant
    common = dict(config="full_agent", model="mock", temperature=0.0, seed=42, oracle=res, success=True, elapsed=1.0,
                  nodes_count=16, elements_count=21, psfr=(True, {}))
    checked = build_record(case, final_design_verified=True, **common)
    assert checked["code_compliant"] is True and classify_failure(checked) is None
    unchecked = build_record(case, final_design_verified=False, **common)
    assert unchecked["code_compliant"] is False and classify_failure(unchecked) == "unverified_design"
    # Configurations without tools are judged on the oracle alone
    single_shot = build_record(case, **{**common, "config": "direct_llm"})
    assert single_shot["code_compliant"] is True


def test_claim_parser_final_dcr_load_factors_and_long_sentences():
    """gemma pilot messages: the final DCR wins over the trial one, 1.2D is a load factor, values may sit far from labels."""
    a07 = ("| **Trial** | 0.40 m | 0.30 m x 0.60 m | **3.045** (Column P-M) | Fail |\n"
           "- **Governing DCR (Trial):** **3.045** (Column axial-flexure interaction).\n"
           "- **Governing DCR (Final):** **0.983** (Beam shear).")
    assert parse_numerical_claims_from_text(a07)["governing_dcr"] == pytest.approx(0.983)
    c03 = (r"- **Maximum Vertical Support Reaction:** Under the factored load combination $1.2\text{D} + 1.6\text{L}$, "
           r"the maximum vertical reaction occurs at the most heavily loaded interior column (Column C2 at the base), "
           r"with a value of **$1,080.98\text{ kN}$**.")
    assert parse_numerical_claims_from_text(c03)["max_base_reaction"] == pytest.approx(1080.98)
    c02 = ("- **Total Dead Load ($W$):** The total vertical reaction (representing the sum of DEAD and SuperDead loads) "
           "is **1,659.87 kN**.\n- **Governing DCR:** **1.062**")
    claims = parse_numerical_claims_from_text(c02)
    assert claims["total_weight"] == pytest.approx(1659.87) and claims["governing_dcr"] == pytest.approx(1.062)


def test_schema_fidelity_accepts_a_mirrored_plan():
    from research_paper.benchmarks.benchmark_utils import _grid_matches

    spacings = [3.6576, 3.9624, 3.9624, 3.3528]
    assert _grid_matches([0.0, 3.3528, 7.3152, 11.2776, 14.9352], spacings, 0.05)  # read right to left
    assert not _grid_matches([0.0, 3.35, 6.6, 10.0, 15.24], spacings, 0.05)  # gemma C05 reading


def test_claim_parser_prefers_the_final_design_section():
    """gemma A08: trial DCR first, final values in a table under a 'Final' heading, plus a drift DCR."""
    text = ("### 1. Trial Sections\n- **Governing DCR:** 1.96 (Column axial-flexure P-M interaction).\n\n"
            "### 3. Final Design Results\n| Parameter | Value |\n| :--- | :--- |\n"
            "| **Total Dead Load ($W$)** | $1,679.2\text{ kN}$ |\n| **Governing DCR** | **0.994** (Beam Flexure) |\n\n"
            "**Compliance Summary:**\n- Story drifts are satisfied (Governing Drift DCR = 0.473).")
    claims = parse_numerical_claims_from_text(text)
    assert claims["governing_dcr"] == pytest.approx(0.994) and claims["total_weight"] == pytest.approx(1679.2)
    assert parse_numerical_claims_from_text("Governing Drift DCR = 0.47; governing DCR = 0.91")["governing_dcr"] == 0.91


def test_claim_parser_same_line_and_limits():
    """gemma batch: sub-items are not the total, a total reaction is not the maximum, and 'exceeds 1.0' is a limit."""
    c01 = ("*   **Total Dead Load ($W$):**\n    *   $\text{DEAD} = 288.96 \text{ kN}$\n"
           "    *   $\text{SuperDead} = 700.00 \text{ kN}$")
    assert "total_weight" not in parse_numerical_claims_from_text(c01)
    b01 = ("- **Maximum Vertical Support Reaction:**\n  Under 1.2D + 1.6L the total vertical base reaction is 7,131.32 kN. "
           "The maximum vertical support reaction is 1,149.69 kN at column C2.")
    assert parse_numerical_claims_from_text(b01)["max_base_reaction"] == pytest.approx(1149.69)
    d02 = ("the governing Demand-Capacity Ratio (DCR) for the columns exceeds 1.0, so the limits are insufficient.\n"
           "- **Governing DCR:** $8.78$ (Column axial-flexure P-M interaction)")
    assert parse_numerical_claims_from_text(d02)["governing_dcr"] == pytest.approx(8.78)
    # A bare DCR of one check or an intermediate iteration does not beat the governing DCR
    a08 = ("### 2. Final Design Iterations\n- Iteration 1: This failed due to joint shear (DCR = 1.17).\n"
           "### 3. Final Design Summary\n| **Governing DCR** | **0.994** (Beam Flexure) |")
    assert parse_numerical_claims_from_text(a08)["governing_dcr"] == pytest.approx(0.994)
    d02b = "- second-order effects are within limits (DCR = 0.714).\n- **Governing DCR:** **$8.78$** (Column P-M)."
    assert parse_numerical_claims_from_text(d02b)["governing_dcr"] == pytest.approx(8.78)


def test_claim_parser_reads_nemotron_formatting():
    """nemotron batch: spaced and LaTeX thousands separators, HTML and LaTeX subscripts, qualifiers in
    parentheses after the label, listed periods, withheld values, and trial values next to final ones."""
    parse = parse_numerical_claims_from_text
    a02 = "- **Total dead load W** (member self‑weight + floor dead load) = **1 393.5 kN**"
    assert parse(a02)["total_weight"] == pytest.approx(1393.5)
    b02 = r"- **Total dead load:** **\( W = 4{,}772.5 \text{ kN} \)**"
    assert parse(b02)["total_weight"] == pytest.approx(4772.5)
    a04 = "| **X‑direction base shear, V<sub>b</sub>** (ASCE 7‑22 ELF, R = 5, I<sub>e</sub> = 1.0) | **165.3 kN** |"
    assert parse(a04)["base_shear"] == pytest.approx(165.3)
    a06 = r"| Fundamental period \(T_{1}\) | **0.432** | s |"
    assert parse(a06)["fundamental_period"] == pytest.approx(0.432)
    a03 = ("| **Cumulative X‑direction modal mass participation ratio** of the first three modes "
           "(from RSA with 3 modes, gross sections) | **0.99999** (≈ 1.00) |")
    assert parse(a03)["modal_mass_ratio"] == pytest.approx(0.99999)
    periods = parse("| **First three periods** T₁, T₂, T₃ | **0.5185 s**, **0.1629 s**, **0.0932 s** |")
    assert (periods["fundamental_period"], periods["period_t2"], periods["period_t3"]) == pytest.approx((0.5185, 0.1629, 0.0932))
    b03 = ("| **Cumulative X‑direction modal mass participation ratio of the first three modes** | "
           "*Not directly available from the current modal analysis output.* |\n"
           r"- The **modal mass participation ratio** requires \(\Gamma_i = \frac{\phi_i^T M 1}{\phi_i^T M \phi_i}\).")
    assert "modal_mass_ratio" not in parse(b03)
    a07 = ("**Initial Trial Sections (0.40 m × 0.40 m columns)**  \n- Governing DCR: **1.253** – **FAIL**.\n\n"
           "**Final Design (after iterative resizing)**  \n- Governing DCR: **0.994** – **PASS**.")
    assert parse(a07)["governing_dcr"] == pytest.approx(0.994)
    a08 = ("- Governing DCR from the first design check: **1.451** (beam flexure).\n"
           "- **Governing DCR** (beam shear, ACI 318‑25 §22.5): **0.9997** (≤ 1.00)")
    assert parse(a08)["governing_dcr"] == pytest.approx(0.9997)
    final_from_initial = "- Governing DCR of the final design (resized from the initial sections): **0.97**"
    assert parse(final_from_initial)["governing_dcr"] == pytest.approx(0.97)
    # B08: the trial DCR under its own heading; the final one on the line after its label
    b08 = ("### 1. Governing DCR of the **trial sections**\n**Governing DCR = 2.565** (joint shear).\n\n"
           "### 2. Final design\n- **Governing DCR of the final design:**\n**\\(DCR_{gov} = 0.999\\)** (beam flexure).")
    assert parse(b08)["governing_dcr"] == pytest.approx(0.999)
    # B08: 'of final design' beats a story-drift DCR that sits under a 'final' heading
    b08b = ("| **Governing DCR of final design** | **0.999** (beam flexure) |\n\n### Final checks\n"
            "* Story drift is satisfied; the maximum drift ratio occurs in Story 2, X-direction, with DCR = 0.831.")
    assert parse(b08b)["governing_dcr"] == pytest.approx(0.999)
    # C01: the sum, not its first term
    c01 = "1. **Total Dead Load (W = DEAD + SuperDead)**\n- DEAD load case vertical reaction: **288.96 kN**\n- **W = 288.96 + 700.00 = 988.96 kN**"
    assert parse(c01)["total_weight"] == pytest.approx(988.96)
    c01b = ("1. **Total Dead Load (W)**\n- DEAD load case vertical reaction: **288.96 kN**\n"
            "- SuperDead load case vertical reaction: **700.00 kN**\n- **W = DEAD + SuperDead = 988.96 kN**")
    assert parse(c01b)["total_weight"] == pytest.approx(988.96)
    # B08: a sub-heading inside the trial section stays in it, and a boxed LaTeX value is read
    b08c = ("### **1. Trial Sections (Initial Guess)**\n**Analysis & Design Results (first pass)**\n"
            "- **Governing DCR = 2.5649** (fail)\n\n### **3. Final Design Results**\n**Final Governing DCR**\n"
            "\\[\n\\text{Governing DCR} = \\boxed{0.9969}\n\\]\n**Design status:**\n- **Governing DCR:** 0.9969 (beam flexure)")
    assert parse(b08c)["governing_dcr"] == pytest.approx(0.9969)
    # D02: a section size is not a DCR
    d02 = "- **Governing DCR:** The last check on a 0.30 × 0.45 m column gave a beam-flexure DCR of 2.85."
    assert parse(d02).get("governing_dcr") != pytest.approx(0.30)


def test_unscorable_claims_are_not_hallucinations(oracle):
    """A probe whose structure is undetermined (D03) has no reference W, so a claimed W is not scored."""
    res = oracle.evaluate("D03_Underspecified_Story_Height", None, {"total_weight": 631.45})
    assert "total_weight" not in res.claims_made and not res.hallucinated_metrics


def test_infeasibility_wording_is_recognized():
    from research_paper.benchmarks.run_benchmarks import BEHAVIOR_PATTERNS

    for text in ("Status: FAILED (architectural constraints prevent further enlargement of members to achieve DCR <= 1.0).",
                 "the specified architectural limits are insufficient to support the heavy-storage live load",
                 # nemotron ablated D02
                 "Consequently, no column‑beam combination satisfying the given dimensional limits can achieve "
                 "ACI 318‑25 compliance under the stated loading.",
                 "The frame could not satisfy the drift limit within the section caps.",
                 # minimax direct_llm and gemma code_gen D02
                 "No reinforcement-detailed design satisfying DCR <= 1.0 exists within the stated dimensional and "
                 "loading constraints.",
                 "The demand exceeds capacity for the given architectural constraints. DCR > 1.0."):
        assert re.search(BEHAVIOR_PATTERNS["report_infeasible"], text, re.IGNORECASE)
    # a design statement is not an infeasibility report
    for text in ("No further resizing is needed; the sections satisfy all checks.",
                 "The 0.40 m column can achieve the required capacity.",
                 "The beam capacity exceeds the demand."):
        assert not re.search(BEHAVIOR_PATTERNS["report_infeasible"], text, re.IGNORECASE)


def test_asking_for_a_withheld_input_answers_the_probe(oracle):
    """nemotron D03: asking for the story height before modelling is the expected behaviour, so the run is
    complete, has no failure mode, and is not scored for fidelity."""
    from research_paper.benchmarks.run_benchmarks import build_record, classify_failure

    case = BY_ID["D03_Underspecified_Story_Height"]
    message = ("I need the story height to complete the model. Could you please specify the vertical story height "
               "(e.g., 3.0 m, 3.5 m) for the two-story frame?")
    record = build_record(case, config="full_agent", model="mock", temperature=0.2, seed=42,
                          oracle=oracle.evaluate(case.id, None, {}), success=False, elapsed=1.0,
                          final_message=message, nodes_count=0, psfr=(False, {"error": "no model"}))
    assert record["behavior_passed"] is True and record["success"] is True
    assert record["prompt_to_schema_fidelity_passed"] is None and classify_failure(record) is None


def test_contradiction_flag_wording_is_recognized():
    from research_paper.benchmarks.run_benchmarks import BEHAVIOR_PATTERNS

    flagged = ("*Note: The prompt requested a total length of 18.0 m, but specified three 5.0 m bays; the model was "
               "created based on the bay dimensions (15.0 m total).*")  # gemma D04, full_agent seed 1
    silent = ("*   **Geometry:** 5.0 m bays (15.0 m total length), 3.5 m story heights.\n"
              "Design a frame with three 5.0 m bays giving a total frame length of 18.0 m.")
    assert re.search(BEHAVIOR_PATTERNS["flag_contradiction"], flagged, re.IGNORECASE)
    assert not re.search(BEHAVIOR_PATTERNS["flag_contradiction"], silent, re.IGNORECASE)


def test_audit_skips_runs_with_truncated_arguments():
    from research_paper.benchmarks.audit_results import _truncated

    assert not _truncated({"sections": [{"id": "COL", "b": 0.5, "h": 0.5}], "title": "Frame"})
    assert _truncated({"columns": [{"grid_x": "A"}, "... 4 more"]})
    assert _truncated({"x_grids": "<list>"}) and _truncated({"note": "a" * 10 + "..."})


def test_replay_refuses_what_the_run_refused():
    """An ablated run's modify_project call was refused, so its replay must not resize the model."""
    from research_paper.benchmarks.audit_results import replay

    log = [{"tool": "create_frame_model", "args": {"num_bays": 1, "num_stories": 1, "bay_width": 5.0, "story_height": 3.0, "fc": 27580.0, "col_b": 0.4, "col_h": 0.4}},
           {"tool": "modify_project", "args": {"sections": [{"id": "COL", "b": 0.6, "h": 0.6}]}}]
    widths = {}
    for config in ("full_agent", "ablated"):
        project, _ = replay({"configuration": config, "tool_log": log})
        widths[config] = next(s.b for s in project.model.sections if s.id == "COL")
    assert widths == {"full_agent": pytest.approx(0.6), "ablated": pytest.approx(0.4)}


def test_replay_blocks_the_model_recreation_the_run_blocked(oracle):
    """gemma A08 (ablated, seed 3): a re-creation with larger columns after a design check was refused in the
    run, and must be refused in the replay (the guard reads the runner's tool log)."""
    from research_paper.benchmarks.audit_results import replay

    frame = {"num_bays": 1, "num_stories": 1, "bay_width": 5.0, "story_height": 3.0, "fc": 27580.0, "col_b": 0.4, "col_h": 0.4, "beam_b": 0.3, "beam_h": 0.5}
    log = [{"tool": "create_frame_model", "args": frame},
           {"tool": "apply_gravity_loads", "args": {"occupancy": "office", "superimposed_dead": 5.0, "custom_live_load": 2.0,
                                                    "tributary_width": 4.0}},
           {"tool": "generate_load_combinations", "args": {}},
           {"tool": "run_analysis", "args": {"analysis_case_id": "S"}},
           {"tool": "run_design", "args": {"analysis_case_id": "S", "design_case_id": "D"}},
           {"tool": "create_frame_model", "args": {**frame, "col_b": 0.6, "col_h": 0.6}}]
    project, dcr = replay({"configuration": "ablated", "tool_log": log})
    assert dcr is not None and next(s.b for s in project.model.sections if s.id == "COL") == pytest.approx(0.4)


def test_replay_does_not_write_deliverable_files(tmp_path):
    """Replays (audit, rescore --replay) wrote research_paper/drawings/*.dxf and results/*.e2k, the files a
    running campaign checks as its runs' deliverables."""
    from research_paper.benchmarks.audit_results import REPO_ROOT, replay

    target = tmp_path / "replayed_frame.dxf"
    frame = {"num_bays": 1, "num_stories": 1, "bay_width": 5.0, "story_height": 3.0, "fc": 27580.0, "col_b": 0.4, "col_h": 0.4, "beam_b": 0.3, "beam_h": 0.5}
    log = [{"tool": "create_frame_model", "args": frame},
           {"tool": "generate_drawings", "args": {"output_path": str(target), "drawing_type": "framing"}, "ok": True}]
    mismatches: list = []
    replay({"configuration": "full_agent", "tool_log": log}, mismatches=mismatches)
    assert not target.exists() and not mismatches
    assert not (REPO_ROOT / target.name).exists()


def test_not_applicable_cases_are_recorded_in_the_summary():
    from research_paper.benchmarks.run_benchmarks import summarize

    summary = summarize([], model="text-only", config="full_agent", temperature=0.2, seeds=5,
                        not_applicable_cases=["C03_PlanToModel_School"])
    assert summary["not_applicable_cases"] == ["C03_PlanToModel_School"] and summary["total_runs"] == 0


def test_replay_reports_calls_that_no_longer_behave_as_logged():
    """nemotron (ablated) design checks of unfactored load cases succeeded in the run and are refused by the
    current run_design: the replay must say so instead of rebuilding a different model silently."""
    from research_paper.benchmarks.audit_results import replay

    log = [{"tool": "create_frame_model", "args": {"num_bays": 1, "num_stories": 1, "bay_width": 5.0, "story_height": 3.0, "fc": 27580.0}, "ok": True},
           {"tool": "apply_gravity_loads", "args": {"occupancy": "office", "superimposed_dead": 5.0, "custom_live_load": 2.0,
                                                    "tributary_width": 4.0}, "ok": True},
           {"tool": "run_analysis", "args": {"analysis_case_id": "S"}, "ok": True},
           {"tool": "run_design", "args": {"analysis_case_id": "S", "design_case_id": "D"}, "ok": True}]
    mismatches = []
    replay({"configuration": "full_agent", "tool_log": log}, mismatches=mismatches)
    assert len(mismatches) == 1 and "run_design" in mismatches[0]


def test_campaign_stops_when_the_provider_cannot_answer(monkeypatch):
    """nemotron's last 19 ablated runs each failed within seconds on the Ollama cloud usage limit (HTTP 429)."""
    from research_paper.benchmarks import run_benchmarks as rb

    monkeypatch.setattr(rb, "llm_server_reachable", lambda api_base: True)
    quota = {"provider_error": True, "error_messages": [
        'LLM Provider error: LLM API request failed with status 429: {"error":{"message":"You reached the Free usage '
        'limit."}}']}
    server = {"provider_error": True, "error_messages": ["LLM Provider error: status 500: Internal Server Error"]}
    ok = {"provider_error": False, "error_messages": []}
    assert "usage or rate limit" in rb.provider_stop_reason([ok, quota], "")
    assert rb.provider_stop_reason([ok, server], "") is None  # a single server error: the next run may succeed
    assert "last 3 runs" in rb.provider_stop_reason([server, server, server], "")
    monkeypatch.setattr(rb, "llm_server_reachable", lambda api_base: False)
    assert "not reachable" in rb.provider_stop_reason([server], "")
    assert rb.provider_stop_reason([ok], "") is None


def test_rates_leave_out_runs_the_setup_ended():
    """nemotron's ablated CCR counted its 19 quota-failed runs (HTTP 429) as non-compliant designs."""
    from research_paper.benchmarks.run_benchmarks import summarize

    def run(cid, compliant, mode):
        return {"case_id": cid, "success": compliant, "design_required": True, "code_compliant": compliant,
                "claims_made_count": 0, "expected_oracle_metrics": [], "hallucinated_claims_count": 0,
                "calculation_hallucination_rate_pct": 0.0, "reference_initial_dcr": None, "behavior_passed": None,
                "material_economy_ratio": None, "prompt_to_schema_fidelity_passed": None, "wall_clock_time_sec": 1.0,
                "failure_mode": mode, "iterations_to_converge": None}

    runs = [run("A02", True, None), run("A04", False, "schema_fidelity"), run("D01", False, "provider_error")]
    s = summarize(runs, model="m", config="full_agent", temperature=0.2, seeds=1)
    assert s["code_compliance_rate_pct"] == 50.0 and s["setup_failed_runs"] == 1 and s["total_runs"] == 3
    assert s["provider_error_runs"] == 1 and len(s["case_results"]) == 3


def test_single_shot_runs_without_an_answer_are_runtime_errors():
    """gpt-oss code_gen A02: the script exited with 'No feasible design found'; that is no answer, not a design
    that failed to converge."""
    from research_paper.benchmarks.run_benchmarks import classify_failure

    record = {"configuration": "code_gen", "success": False, "design_task": "design", "code_compliant": False,
              "behavior_passed": None, "nodes_count": 0, "missing_expected_tools": [], "deliverables": None,
              "prompt_to_schema_fidelity_passed": None, "design_space_violations": [], "code_executed": False}
    assert classify_failure(record) == "runtime_error"
    answered = {**record, "success": True, "code_executed": True}
    assert classify_failure(answered) == "dcr_non_convergence"


def test_claim_parser_reads_meganewtons_and_nested_latex():
    """gpt-oss B04 wrote '\boxed{W = 4{,}135.8\ \text{kN}}' and later 'W ≈ 4.14 MN': both were misread
    (the LaTeX was unwrapped at the first brace, MN was taken as kN), scoring a correct W as 99.9 % off."""
    boxed = r"### 1. Total Dead Load" "\n" r"\[\boxed{W = 4{,}135.8\ \text{kN}}\]"
    assert parse_numerical_claims_from_text(boxed)["total_weight"] == pytest.approx(4135.8)
    assert parse_numerical_claims_from_text("Total dead load W ≈ 4.14 MN")["total_weight"] == pytest.approx(4140.0)
    assert parse_numerical_claims_from_text("Base shear Vb = 0.654 MN", "kip, ft")["base_shear"] == pytest.approx(
        654.0 / 4.448222, rel=1e-4)


def test_periods_are_read_from_a_table_of_modes():
    """minimax B03 reported the periods only in a table of modes, without a T1 label."""
    text = ("## 4. Modal Analysis\n\n| Mode | Period T (s) | Freq. (Hz) | Character |\n|---|---|---|---|\n"
            "| **1** | **0.4267** | 2.344 | Predominantly **Y** |\n| **2** | **0.4139** | 2.416 | X |\n"
            "| **3** | **0.3663** | 2.730 | torsion |\n| 4-12 | 0.2838 -> 0.1049 | 3.52 | higher |\n")
    claims = parse_numerical_claims_from_text(text)
    assert (claims["fundamental_period"], claims["period_t2"], claims["period_t3"]) == (0.4267, 0.4139, 0.3663)
    # A labeled value still wins, and a table without a period column gives none
    assert parse_numerical_claims_from_text("T1 = 0.50 s\n\n" + text)["fundamental_period"] == 0.50
    assert "period_t2" not in parse_numerical_claims_from_text("| Mode | Freq. (Hz) |\n|---|---|\n| 2 | 2.4 |\n")


def test_a_sentence_announcing_its_value_and_counts_that_are_not_values():
    """gemma A03 put the ratio in a bullet under '... for the first three modes is:'; a count ('first 3 modes',
    'the 2 stories') is not the value, and a table value before its next cell ('| 0.998 | Beam flexure') is."""
    announced = ("The cumulative X-direction modal mass participation ratio for the first three modes is:\n"
                 "- **$\\sum \\text{MPR}_x = 1.00$ (100%)**")
    assert parse_numerical_claims_from_text(announced)["modal_mass_ratio"] == 1.0
    assert parse_numerical_claims_from_text("Total dead load:\n- DEAD = 288.96 kN\n- SuperDead = 700 kN") == {}
    assert parse_numerical_claims_from_text(
        "The modal mass participation of the first 3 modes is 98.6%.")["modal_mass_ratio"] == pytest.approx(0.986)
    assert parse_numerical_claims_from_text("The total dead load W of the 2 stories is 1,516.07 kN")["total_weight"] == 1516.07
    assert parse_numerical_claims_from_text(
        "| **Governing Demand-Capacity Ratio (DCR)** | **0.998** | Beam flexure on beam B_3_2 |")["governing_dcr"] == 0.998


def test_values_under_a_label_line_and_in_a_cumulative_mass_table():
    """minimax B01 put the reaction in a display equation under a label with load factors; nemotron A06 under a
    bold label ending in a colon; minimax A03 gave the mass ratio only in a table with a cumulative column. A
    numbered list under a sentence ending in a colon is no value (nemotron A04: '... you would need to:' over
    '1. Run ...')."""
    reaction = ("**Maximum vertical support reaction under 1.2D + 1.6L:**\n\n"
                "$$R_{max} = 1149.7 \\text{ kN (compression)}$$\n\nat node 6")
    assert parse_numerical_claims_from_text(reaction)["max_base_reaction"] == 1149.7
    weight = "**Total Dead Load W (member self-weight + floor dead load):**  \nW = 1,628.81 kN"
    assert parse_numerical_claims_from_text(weight)["total_weight"] == 1628.81
    assert parse_numerical_claims_from_text(
        "To obtain the governing DCR you would need to:\n\n1. Run a linear static analysis\n2. Run the design") == {}
    table = ("### 3. Cumulative X-Direction Modal Mass Participation\n\n| Mode | Individual | Cumulative (first 3) |\n"
             "|---|---|---|\n| 1 | 0.9021 | 0.9021 |\n| 2 | 0.0843 | 0.9864 |\n| 3 | 0.0136 | **1.0000 (100%)** |\n")
    assert parse_numerical_claims_from_text(table)["modal_mass_ratio"] == 1.0
    both = "| Mode | Cum. Y | Cum. X |\n|---|---|---|\n| 3 | 0.95 | 98.6% |\n"
    assert parse_numerical_claims_from_text(both)["modal_mass_ratio"] == pytest.approx(0.986)


def test_slash_separated_period_list():
    """minimax C01: 'T1/T2/T3 = 0.4577 / 0.4167 / 0.3874 s' gave 0.3874 for all three (read as a division)."""
    claims = parse_numerical_claims_from_text("gives identical results (T1/T2/T3 = 0.4577 / 0.4167 / 0.3874 s).")
    assert (claims["fundamental_period"], claims["period_t2"], claims["period_t3"]) == (0.4577, 0.4167, 0.3874)


def test_component_weights_derivations_and_qualified_labels():
    """minimax production misreads: a self-weight label took the next sentence's live total (A02, C05), a value
    followed by its derivation was skipped as a term (C05), 'member-level' hid a governing DCR (C02), and a ratio
    of two masses read as the modal mass ratio over a table of cumulative ranges (B03)."""
    a02 = ("- Loads: floor DL 5.1 kPa, plus member self-weight (γ = 23.54 kN/m³). Total LL applied = 702.0 kN\n"
           "### 4. Total dead load W (final sections)\n| Component | kN |\n|---|---|\n| Beam self-weight | 143.0 |\n"
           "| **Total W** | **1456.2 kN** |")
    assert parse_numerical_claims_from_text(a02)["total_weight"] == 1456.2
    c05 = ("- Gravity: floor dead 5.1 kPa, plus member self-weight. Live total 3 228 kN.\n"
           "- **Total dead load W = 7 555.6 kN** = floor dead load 5.1 kPa × 168.44 m² × 4 = 3 436 kN + 4 120 kN")
    assert parse_numerical_claims_from_text(c05)["total_weight"] == 7555.6
    assert parse_numerical_claims_from_text("W = 288.96 + 700.00 = 988.96 kN")["total_weight"] == 988.96
    c02 = ("- Frame check governing: ACI 318-25 §6.2.5.3, governing column 17, DCR = **0.7548**.\n"
           "**Governing member-level DCR: 0.987 → PASS**\n- Governing shear DCR (frame): 0.152.")
    assert parse_numerical_claims_from_text(c02)["governing_dcr"] == 0.987
    b03 = ("a mass ratio of 1.055, matching 4,653.98/4,430.78 = 1.050\n\n### 3. Cumulative X-Direction Modal Mass "
           "Participation\n\n| Modes | Cumulative X |\n|---|---|\n| Mode 1 | 0.05% |\n| Modes 1–2 | 88.85% |\n"
           "| **Modes 1–3** | **89.77%** |")
    assert parse_numerical_claims_from_text(b03)["modal_mass_ratio"] == pytest.approx(0.8977)


def test_ordinals_and_words_before_a_slash_are_not_values():
    """deepseek C01 (pilot): in '| **T3** | **0.3874** | torsional / 2nd mode |' the word after the value was taken
    as its unit, the slash after the word as a division (0.3874 skipped as a term), and '2nd' gave T3 = 2.0."""
    c01 = ("| Period | Value (s) | Mode character | Mass participation |\n|---|---|---|---|\n"
           "| **T1** | **0.4577** | 1st translational X | 90.33 % UX |\n"
           "| **T2** | **0.4167** | 1st translational Y | 83.67 % UY |\n"
           "| **T3** | **0.3874** | torsional / 2nd mode | 0.00 % UX, 3.05 % UY |")
    claims = parse_numerical_claims_from_text(c01)
    assert (claims["fundamental_period"], claims["period_t2"], claims["period_t3"]) == (0.4577, 0.4167, 0.3874)
    assert "period_t3" not in parse_numerical_claims_from_text("T3: see the 2nd mode")
    assert parse_numerical_claims_from_text("Column 0.30 m × 0.45 m, governing DCR 0.95")["governing_dcr"] == 0.95


def test_heading_equations_unscaled_shears_and_second_order_checks():
    """deepseek full_agent production misreads: a mass ratio in a display equation under a heading that ends with a
    qualifier was omitted (B03); the unscaled modal base shear was read for the design Vb (B09); the DCR of the frame
    second-order check was read for the governing DCR (C02)."""
    b03 = ("**3. Cumulative X-direction modal mass participation (first three modes)**\n\n"
           "$$M_{X,1-3} = 0.0005 + 0.8880 + 0.0092 = \\mathbf{89.77\\ \\%}$$\n\n(Including modes 4–12 raises it to 97.86 %)")
    assert parse_numerical_claims_from_text(b03)["modal_mass_ratio"] == pytest.approx(0.8977)
    b09 = ("| Quantity | X direction | Y direction |\n|---|---|---|\n| Modal base shear | 676.8 kN | 653.7 kN |\n"
           "| **ELF base shear V (design)** | **816.4 kN** | **791.2 kN** |\n\n"
           "| **Base shear Vb, X direction** | **816 kN** (Y: 791 kN) |")
    assert parse_numerical_claims_from_text(b09)["base_shear"] == 816.4
    b05 = ("CQC bidirectional RSA scaled to ELF base shear (§12.9.1.4)\n\n## 2. Final member sizes (multiples of 0.05 m)"
           "\n\n- X-direction base shear Vb       615.5 kN   (= 0.125 W, ELF governing)")
    assert parse_numerical_claims_from_text(b05)["base_shear"] == 615.5
    c02 = ("- Governing second‑order condition: ACI 318‑25 §6.2.5.3 — second‑order end moment ≤ 1.4 × first‑order "
           "moment, DCR 0.755 (worst column: element 17) — **pass**.\n\n**Governing result:**\n\n"
           "> **DCR = 0.99 — Column element 16** (upper‑story interior column): **axial–flexure P‑M interaction**")
    assert parse_numerical_claims_from_text(c02)["governing_dcr"] == 0.99
    assert parse_numerical_claims_from_text("Final design (second-order analysis): DCR 0.97")["governing_dcr"] == 0.97


def test_cumulative_mass_ratio_in_a_list_of_mode_ranges():
    """deepseek ablated A03: the cumulative ratio of the first three modes as the 'Modes 1–3' item of a list."""
    a03 = ("**3. Cumulative X-direction modal mass participation, first three modes**\n\n- Mode 1: 90.21 %\n"
           "- Modes 1–2: 98.64 %\n- **Modes 1–3: 100.0 %**\n")
    assert parse_numerical_claims_from_text(a03)["modal_mass_ratio"] == pytest.approx(1.0)
    assert "modal_mass_ratio" not in parse_numerical_claims_from_text("Periods of modes 1-3: 0.52, 0.16, 0.09 s")
    assert "modal_mass_ratio" not in parse_numerical_claims_from_text("Modes 1–3: T = 0.52 s, 0.16 s, 0.09 s")


def test_trial_final_tables_equations_with_qualifiers_and_rows_that_are_not_the_value():
    """Seed-42 agent misreads (Fix 10): each response states the oracle's value, and the parser read another number."""
    # gemma A07: a table comparing the trial and the final design gave the trial column first
    a07 = ("### 3. Design Summary\n| Parameter | Trial Design | Final Design |\n| :--- | :--- | :--- |\n"
           "| **Governing DCR** | **1.311** | **0.985** |\n"
           "| **Total Dead Load ($W$)** | $270.23\\text{ kN}$ | **$313.89\\text{ kN}$** |")
    claims = parse_numerical_claims_from_text(a07)
    assert (claims["governing_dcr"], claims["total_weight"]) == (0.985, 313.89)
    # gemma C01: the qualifiers hid the '+' after the first term of the sum
    c01 = "- **Total Dead Load ($W$):** $288.96\\text{ kN (DEAD)} + 700.00\\text{ kN (SuperDead)} = \\mathbf{988.96\\text{ kN}}$"
    assert parse_numerical_claims_from_text(c01)["total_weight"] == 988.96
    # qwen C02: the label of a heading crossed into its first sub-item
    c02 = ("### Total Dead Load\n- **DEAD load case**: 288.96 kN\n- **SuperDead load case**: 700.0 kN\n"
           "- **Total dead load W = DEAD + SuperDead = 988.96 kN**")
    assert parse_numerical_claims_from_text(c02)["total_weight"] == 988.96
    # qwen B03: '3-story' is a count; the cumulative mode-3 item is the value
    b03 = ("### **Cumulative X-Direction Modal Mass Participation Ratio**\nFor the first three modes:\n"
           "- Mode 1: 0.0005 (0.05%)\n- Mode 2: 0.8885 (88.85% cumulative)\n- Mode 3: **0.8977 (89.77% cumulative)**\n\n"
           "The first three modes capture approximately **89.8%** of the total mass participation in the X-direction, "
           "which is typical for a 3-story building.")
    assert parse_numerical_claims_from_text(b03)["modal_mass_ratio"] == pytest.approx(0.8977)
    # minimax A03: in 'T2/T3 (0.163 s, 0.093 s)' the first value is T2's; the table of modes gives T3
    a03 = ("| Mode | T (s) | f (Hz) |\n|---|---|---|\n| 1 | 0.5186 | 1.9283 |\n| 2 | 0.1630 | 6.1365 |\n"
           "| 3 | 0.0932 | 10.7304 |\n\n- The very short T₂/T₃ (0.163 s, 0.093 s) reflect the stiff beams.")
    assert parse_numerical_claims_from_text(a03)["period_t3"] == 0.0932
    # minimax C01: a base shear coefficient is not the base shear; 'V_base' is
    c01_vb = ("**2. Base shear, load case EQx**\n**V_base = 132.37 kN** (acting in global X)\n"
              "Ratio check: V_base / W = 132.37 / 988.96 = **0.134**, consistent with a base shear coefficient C_s ≈ 0.13.")
    assert parse_numerical_claims_from_text(c01_vb)["base_shear"] == 132.37
    assert "base_shear" not in parse_numerical_claims_from_text("a base shear coefficient C_s ≈ 0.13")
    # minimax A05: the DCR on a row about the second-order frame checks; qwen B06: a footing DCR
    a05 = ("| Second order | Q = 0.026–0.030; all 15 analysis frame checks **passed** (governing DCR 0.756) |\n\n"
           "| **Governing DCR** | **1.17 — Joint 14 (x) joint shear (FAIL)** |")
    assert parse_numerical_claims_from_text(a05)["governing_dcr"] == 1.17
    assert "governing_dcr" not in parse_numerical_claims_from_text("- **All footings pass** with DCR between 0.85 and 1.00")


def test_a_run_that_could_not_resize_reports_its_trial_design():
    """minimax ablated A08 reported 'Governing DCR = 1.488' only under headings about the trial sections, the design it
    delivered; a proposed revision it could not carry out gave 'DCR ≈ 0.56' for a beam and was read instead."""
    a08 = ("### 4. ACI 318-25 design check of the trial sections\n\n**Governing DCR = 1.488 → DESIGN FAILS**\n\n"
           "### 5. Revision required — **not executable in this run**\n\n"
           "- **Beams 0.30 × 0.60 m** (all). φMn ≈ 415 kNm vs Mu ≈ 233 kNm (DCR ≈ 0.56)\n\n"
           "### 6. Requested report values (as tested — trial sections)\n\n| Governing DCR | **1.488** — FAIL |")
    assert parse_numerical_claims_from_text(a08)["governing_dcr"] == 1.488
    # a resized design still reports its final value, not the trial one
    resized = "### Trial sections\nGoverning DCR = 1.311\n\n### Resized design\nGoverning DCR = 0.962"
    assert parse_numerical_claims_from_text(resized)["governing_dcr"] == 0.962


def test_code_gen_runs_the_last_python_block():
    """qwen B03 drafted a block and promised 'a cleaner version in the final code block'; the last one is the answer."""
    from research_paper.benchmarks.run_benchmarks import script_from_reply

    reply = "```python\nprint('draft')\n```\nI will write a cleaner version.\n```python\nprint('final')\n```\n" \
            "Output:\n```json\n{\"x\": 1}\n```"
    assert script_from_reply(reply) == "print('final')"
    assert script_from_reply("```\nprint(1)\n```") == "print(1)"
    assert script_from_reply("```python\nprint(1)\n") == "print(1)"  # closing fence missing
    assert script_from_reply("print(1)") == "print(1)"


def test_a_direct_answer_can_answer_a_probe_in_its_notes(oracle, monkeypatch):
    """direct_llm answers in JSON only: without a notes field it passed 0 of 7 probes (minimax D02 gave the
    capped sections with DCR 1.97 and no words)."""
    from research_paper.benchmarks import run_benchmarks as rb

    case = BY_ID["D02_Infeasible_Section_Cap"]
    assert '"notes"' in rb.single_shot_messages(case, "direct_llm")[0]["content"]

    def run(notes):
        reply = json.dumps({"col_b": 0.30, "col_h": 0.30, "beam_b": 0.30, "beam_h": 0.45, "total_weight": 287.18,
                            "governing_dcr": 1.97, "notes": notes})
        monkeypatch.setattr(rb, "chat_completion", lambda *a, **k: (reply, {"finish_reason": "stop"}))
        return rb.run_single_shot(case, oracle, mode="direct_llm", model="mock", api_base="", api_key="",
                                  temperature=0.0, seed=None, timeout=1.0)

    assert run("")["behavior_passed"] is False
    assert run("No section within the 0.30 m column cap is adequate: the governing DCR is 1.97.")["behavior_passed"] is True


def test_the_single_shot_schema_asks_for_the_prompts_units():
    """A06 and B07 ask for the roof displacement in mm; the JSON schema asked for m, and answers followed either
    (deepseek code_gen A06 printed 47.39 mm). The schema now asks for the prompt's unit and the answer is converted
    from it; a record from before the change carries no 'answer_units' and was asked in spec units."""
    from research_paper.benchmarks.run_benchmarks import answer_units, single_shot_claims, single_shot_messages

    for cid in ("A06_Frame2D_THA_ElCentro_Analysis", "B07_Frame3D_THA_ElCentro_Analysis"):
        case = BY_ID[cid]
        assert answer_units(case) == {"peak_roof_displacement": "mm"}
        for mode in ("direct_llm", "code_gen"):
            assert "relative to the base in mm>" in single_shot_messages(case, mode)[0]["content"]
        claims = single_shot_claims(case, {"peak_roof_displacement": 47.39, "total_weight": 1.0}, answer_units(case))
        assert claims == {"peak_roof_displacement": pytest.approx(0.04739), "total_weight": 1.0}
        assert single_shot_claims(case, {"peak_roof_displacement": 0.047}, {})["peak_roof_displacement"] == 0.047
    assert all(answer_units(c) == {} for c in CASES if c.id[:3] not in ("A06", "B07"))


def test_a_crashed_script_does_not_answer_a_probe(oracle, monkeypatch):
    """qwen code_gen D03: the script's comments assumed a story height, then it crashed; minimax code_gen D02-D04
    passed on comments such as '# infeasible'. The user receives what the script printed, not its source: a
    crashed script printed nothing and answers no probe, also when a saved run is re-scored. A script that
    prints its request for the withheld input still answers it."""
    from research_paper.benchmarks import run_benchmarks as rb
    from research_paper.benchmarks.rescore_results import rescore_record

    case = BY_ID["D03_Underspecified_Story_Height"]

    def run(script):
        reply = f"```python\n{script}\n```"
        monkeypatch.setattr(rb, "chat_completion", lambda *a, **k: (reply, {"finish_reason": "stop"}))
        return rb.run_single_shot(case, oracle, mode="code_gen", model="mock", api_base="", api_key="",
                                  temperature=0.2, seed=42, timeout=1.0)

    crashed = run("# Assumed story height: 3.5 m (not specified)\nraise RuntimeError('unpacking failed')")
    assert crashed["behavior_passed"] is False and crashed["success"] is False
    assert crashed["failure_mode"] == "runtime_error"
    assert "Assumed" in crashed["final_message"]  # the script is kept for audits
    summary = rb.summarize([crashed], model="mock", config="code_gen", temperature=0.2, seeds=1)
    assert summary["probe_behavior_rate_pct"] == 0
    silent = run("# assume a story height of 3.5 m\nprint('done')")  # ran, but told the user nothing
    assert silent["behavior_passed"] is False
    asked = run("print('The story height is not specified; please provide it.')")
    assert asked["success"] is True and asked["failure_mode"] is None

    # A run scored by the old rule (probe matched in the script's source) is corrected when re-scored
    legacy = {**crashed, "behavior_passed": True, "success": True, "failure_mode": None, "seed_index": 0}
    rescored = rescore_record(legacy, oracle, BY_ID)
    assert rescored["behavior_passed"] is False and rescored["success"] is False
    assert rescored["failure_mode"] == "runtime_error"
    assert rescored["code_executed"] is False and rescored["final_message"] == crashed["final_message"]
    assert rescore_record({**asked, "seed_index": 0}, oracle, BY_ID)["behavior_passed"] is True


def test_runs_write_their_files_in_their_own_workspace(tmp_path):
    """Concurrent campaigns wrote the same deliverable paths (A01, A07, C01, C02, C06), and qwen A04 and C05 saved
    unrequested drawings as 'structural_design.dxf' in the repository root, where the next run overwrote them.
    Each run works in a fresh workspace holding the fixtures; its deliverables and other outputs move to the run's
    folder, except a file that existed before the agent wrote over it (an input fixture)."""
    from research_paper.benchmarks.run_benchmarks import keep_outputs, make_workspace, verify_deliverables

    case = BY_ID["C06_Pinned_Base_ELF_Design_CAD"]
    ws = make_workspace(case)
    try:
        assert (ws / "research_paper/benchmarks/fixtures/exported_seismic_frame.s2k").is_file()
        deliverable = ws / case.deliverables.files[0].path
        assert deliverable.parent.is_dir() and verify_deliverables(case, ws) == {case.deliverables.files[0].path: False}
        import ezdxf

        doc = ezdxf.new()
        doc.modelspace().add_line((0, 0), (1, 0))
        doc.saveas(deliverable)
        assert all(verify_deliverables(case, ws).values())
        extra, fixture = ws / "structural_design.dxf", ws / "research_paper/benchmarks/fixtures/exported_seismic_frame.s2k"
        extra.write_text("x")
        dest = tmp_path / "results_files" / "C06_seed42"
        moved = keep_outputs(case, ["structural_design.dxf", str(extra), str(fixture), str(deliverable)], ws, dest,
                             preexisting={fixture.resolve()})
        assert moved == ["structural_design.dxf"] and (dest / extra.name).is_file() and not extra.exists()
        assert (dest / deliverable.name).is_file() and not deliverable.exists() and fixture.is_file()
    finally:
        shutil.rmtree(ws, ignore_errors=True)


def test_symbol_labels_and_values_on_the_next_line():
    """Omissions found by searching the saved messages for the oracle values: minimax A02 and A03 labelled the weight
    'W (total dead)' in a table, and minimax C01 wrote the base shear as a bold line over 'V = 132.37 kN'. The next
    line counts only as an equation of the metric's own symbol."""
    a03 = "| Component | kN |\n|---|---|\n| Member self-weight | 385.5 |\n| **W (total dead)** | **1,533.0** |"
    assert parse_numerical_claims_from_text(a03)["total_weight"] == pytest.approx(1533.0)
    a02 = "| **W (total dead)** | | **1,561.2 kN** |"
    assert parse_numerical_claims_from_text(a02)["total_weight"] == pytest.approx(1561.2)
    c01 = ("**Total weight, DEAD + SuperDead** | W = 288.96 + 700.00 = **988.96 kN**\n\n"
           "**Base shear, load case EQx**\nV = **132.37 kN** (X direction, no Y component)")
    claims = parse_numerical_claims_from_text(c01)
    assert claims["base_shear"] == pytest.approx(132.37) and claims["total_weight"] == pytest.approx(988.96)
    # Another quantity's equation under the label is not its value
    assert "base_shear" not in parse_numerical_claims_from_text("**Base shear, load case EQx**\nW = 4,800 kN")
