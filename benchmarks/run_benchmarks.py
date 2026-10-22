"""
Autonomous Structural Engineering Benchmark Execution Harness
==============================================================

Automates batch testing of Large Language Models against the 24-case structural
benchmark suite across five experimental configurations (full_agent, ablated, direct_llm, code_gen, heuristic).
Records quantitative metrics (TCR, CCR, CHR, convergence iterations, material
economy ratio, runtime) to unique timestamped JSON files.

Usage Examples
--------------
# Run all 24 cases with Google Gemini 3.8 Flash (Full Agent vs. Ablated):
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --cases all --seeds 5
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --config ablated --cases all --seeds 5

# Run Direct Zero-Shot LLM baseline (no tools) to measure Calculation Hallucination Rate (CHR):
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --config direct_llm --cases all --seeds 1

# Run Group A (2D cases) with local/cloud Ollama models:
python "research_paper/benchmarks/run_benchmarks.py" --model qwen3.5:9b --cases Group_A_2D --seeds 5
python "research_paper/benchmarks/run_benchmarks.py" --model nemotron-3-super:cloud --cases Group_A_2D --seeds 5
python "research_paper/benchmarks/run_benchmarks.py" --model gemma4:31b-cloud --cases Group_A_2D --seeds 5
"""

import argparse
import inspect
import json
import math
import os
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure Windows terminal stdout handles unicode cleanly
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from struct_agent import (
    AgentRunner,
    CompleteEvent,
    ErrorEvent,
    StateUpdateEvent,
    ThoughtEvent,
    ToolCallEvent,
    ToolResultEvent,
)

# Tools that are purely diagnostic/validation or conditional on overstress;
# all other tools listed in `expected_tools` are strictly required for TCR.
NON_MANDATORY_EXPECTED_TOOLS = {
    "modify_project",
    "validate_model",
    "inspect_project",
    "inspect_analysis_results",
    "inspect_dynamic_results",
    "inspect_design_results",
    "inspect_detailing_results",
}

# Ensure benchmarks package can be imported
benchmarks_dir = Path(__file__).resolve().parent
repo_root_candidate = benchmarks_dir.parents[1]
if str(repo_root_candidate) not in sys.path:
    sys.path.insert(0, str(repo_root_candidate))

try:
    from research_paper.benchmarks.oracle_verifier import OracleVerifier, ORACLE_CASES_CATALOG
    from research_paper.benchmarks.benchmark_utils import (
        calculate_concrete_volume,
        evaluate_prompt_to_schema_fidelity,
        load_benchmark_cases,
        parse_numerical_claims_from_text,
    )
except ImportError:
    from oracle_verifier import OracleVerifier, ORACLE_CASES_CATALOG
    from benchmark_utils import (
        calculate_concrete_volume,
        evaluate_prompt_to_schema_fidelity,
        load_benchmark_cases,
        parse_numerical_claims_from_text,
    )

from struct_agent.tools.analysis import run_analysis
from struct_agent.tools.design import run_design



def sanitize_filename(name: str) -> str:
    """Sanitize model name for clean file naming."""
    return re.sub(r"[^a-zA-Z0-9_\-\.]", "_", name)


# Canonical volume calculation and case loading are imported from benchmark_utils.py.



# Single canonical goal-oriented prompts are used across all 4 configurations to eliminate prompt confounds.


def inject_cae_fixtures_if_needed(case: Dict[str, Any], prompt: str, repo_root: Path) -> str:
    """
    Inject raw text of .s2k or .e2k fixture files into user prompt on C03/C04
    for direct_llm and code_gen baselines, guaranteeing strict informational parity.
    """
    case_id = case.get("id", "")
    if "C03" in case_id or "C04" in case_id:
        file_path_str = case.get("file_path")
        if file_path_str:
            target_path = repo_root / file_path_str
            if not target_path.exists():
                target_path = Path(__file__).resolve().parent / file_path_str
            if target_path.exists():
                content = target_path.read_text(encoding="utf-8", errors="replace")
                return (
                    f"{prompt}\n\n"
                    f"--- Raw CAE Fixture File Content ({target_path.name}) ---\n"
                    f"{content}\n"
                    f"--- End of CAE Fixture File Content ---"
                )
    return prompt


# Prompt-to-Schema Fidelity Rate (PSFR) evaluation logic is canonically defined
# in benchmark_utils.py (evaluate_prompt_to_schema_fidelity) to ensure identical
# verification criteria across harness runners and unit test suites.


def run_direct_llm_baseline(
    case: Dict[str, Any],
    model: str,
    api_base: str,
    api_key: str,
    repo_root: Path,
    timeout: float = 180.0,
    temperature: float = 0.0,
    seed: Optional[int] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Execute Baseline 1 (Direct Zero-Shot LLM without symbolic tools) using
    Oracle Verification to evaluate Calculation Hallucination Rate (CHR) and
    true Code Compliance Rate (CCR) without equifinality or self-weight bias.
    """
    case_id = case["id"]
    prompt = case["prompt"]
    requires_design = bool(case.get("design_required", False))

    # Inject CAE fixture text for C03/C04 to guarantee informational parity
    prompt = inject_cae_fixtures_if_needed(case, prompt, repo_root)

    system_msg = (
        "You are an expert structural engineer performing preliminary structural sizing and calculations. "
        "Based on the structural geometry, loading, and constraints in the user prompt, propose candidate member "
        "cross-section dimensions (columns and beams in meters) and state your calculated physical mechanics values. "
        "You must output ONLY a valid JSON object with the following keys:\n"
        '{\n'
        '  "col_b_m": <float, column cross-section width in meters>,\n'
        '  "col_h_m": <float, column cross-section depth in meters>,\n'
        '  "beam_b_m": <float, beam cross-section width in meters>,\n'
        '  "beam_h_m": <float, beam cross-section depth in meters>,\n'
        '  "claimed_total_weight_kN": <float, total structural dead load + self-weight in kN>,\n'
        '  "claimed_base_shear_kN": <float, total lateral base shear in kN (0.0 if pure gravity)>,\n'
        '  "claimed_fundamental_period_s": <float, fundamental natural vibration period T1 in seconds (0.0 if not dynamic)>,\n'
        '  "claimed_period_t2_s": <float, second mode period T2 in seconds (0.0 if not modal)>,\n'
        '  "claimed_period_t3_s": <float, third mode period T3 in seconds (0.0 if not modal)>,\n'
        '  "claimed_modal_mass_ratio": <float, modal mass participation ratio (0.0 if not modal)>,\n'
        '  "claimed_peak_displacement_m": <float, peak roof lateral displacement in meters (0.0 if not time-history)>,\n'
        '  "claimed_governing_dcr": <float, governing ACI 318 demand-capacity ratio DCR (1.0 if not design case)>\n'
        '}\n'
        "Do not include markdown code fences, comments, or extra text. Output only the raw JSON string."
    )

    t_start = time.perf_counter()
    url = f"{api_base.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
    }
    if seed is not None:
        payload["seed"] = seed
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key or 'ollama'}",
    }

    raw_reply = ""
    error_messages = []
    parsed: Dict[str, Any] = {}

    try:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            raw_reply = (
                resp_data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
            )
            match = re.search(r"\{.*\}", raw_reply, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
    except Exception as exc:
        error_messages.append(str(exc))
        if verbose:
            print(f"  [Direct LLM Error]: {exc}")

    t_elapsed = round(time.perf_counter() - t_start, 2)

    # Deterministic Oracle Verification
    verifier = OracleVerifier(repo_root=repo_root)
    col_b = parsed.get("col_b_m") or parsed.get("col_b")
    col_h = parsed.get("col_h_m") or parsed.get("col_h")
    beam_b = parsed.get("beam_b_m") or parsed.get("beam_b")
    beam_h = parsed.get("beam_h_m") or parsed.get("beam_h")

    oracle_res = verifier.evaluate(
        case_id=case_id,
        col_b=col_b,
        col_h=col_h,
        beam_b=beam_b,
        beam_h=beam_h,
        claims=parsed,
    )

    chr_pct = oracle_res.calculation_hallucination_rate_pct
    code_compliant = oracle_res.code_compliant
    concrete_vol = oracle_res.concrete_volume_m3
    econ_ratio = oracle_res.material_economy_ratio
    gov_dcr = oracle_res.governing_dcr
    expected_metrics = getattr(oracle_res, "expected_metrics", oracle_res.active_metrics) or oracle_res.active_metrics
    num_claims = max(len(oracle_res.claims_made), 1)
    hallucinated_claims = len(oracle_res.hallucinated_metrics)

    if oracle_res.error_message:
        error_messages.append(f"OracleVerifier: {oracle_res.error_message}")

    print(
        f"\n--> Result: [DIRECT LLM BASELINE] | Hallucinations: {hallucinated_claims}/{num_claims} "
        f"(CHR: {chr_pct}%) | Oracle DCR: {gov_dcr} | Compliant: {code_compliant} | Time: {t_elapsed}s"
    )

    gov_member_id = oracle_res.governing_member_type
    gov_limit_state = oracle_res.governing_limit_state

    success = bool(oracle_res.code_compliant if requires_design else oracle_res.valid_sections)
    failure_mode = None
    if not success:
        if not oracle_res.valid_sections:
            failure_mode = "model_construction"
        elif requires_design and not oracle_res.code_compliant:
            failure_mode = "dcr_non_convergence"
        else:
            failure_mode = "runtime_error"

    return {
        "case_id": case_id,
        "name": case["name"],
        "group": case.get("group", ""),
        "model": model,
        "configuration": "direct_llm",
        "temperature": temperature,
        "seed": seed,
        "design_required": requires_design,
        "success": success,
        "code_compliant": code_compliant,
        "governing_member_id": gov_member_id,
        "governing_limit_state": gov_limit_state,
        "dcr_flexure": None,
        "dcr_shear": None,
        "dcr_pm": None,
        "final_stage": "UNVERIFIED_TEXT_ONLY",
        "stages_visited": [],
        "wall_clock_time_sec": t_elapsed,
        "turns_used": 1,
        "tools_called": [],
        "missing_expected_tools": case.get("expected_tools", []),
        "tool_failures_count": 0,
        "tool_failures": [],
        "initial_dcr": gov_dcr,
        "final_dcr": gov_dcr,
        "dcr_history": [gov_dcr] if gov_dcr is not None else [],
        "iterations_to_converge": None,
        "nodes_count": 0,
        "elements_count": 0,
        "concrete_volume_m3": concrete_vol,
        "baseline_concrete_volume_m3": case.get("baseline_concrete_volume_m3"),
        "material_economy_ratio": econ_ratio,
        "numerical_claims_count": len(oracle_res.claims_made),
        "claims_made": oracle_res.claims_made,
        "claims_made_count": len(oracle_res.claims_made),
        "omitted_metrics": oracle_res.omitted_metrics,
        "omitted_metrics_count": len(oracle_res.omitted_metrics),
        "expected_oracle_metrics": expected_metrics,
        "claim_completeness_pct": round(
            (len(set(oracle_res.claims_made) & set(expected_metrics)) / max(len(expected_metrics), 1)) * 100.0,
            1,
        ),
        "hallucinated_claims_count": hallucinated_claims,
        "calculation_hallucination_rate_pct": chr_pct,
        "active_oracle_metrics": oracle_res.active_metrics,
        "hallucinated_oracle_metrics": oracle_res.hallucinated_metrics,
        "oracle_metric_errors": oracle_res.metric_errors,
        "prompt_to_schema_fidelity_passed": False,
        "failure_mode": failure_mode,
        "error_messages": error_messages,
        "final_message_snippet": (raw_reply[:200] + "...") if len(raw_reply) > 200 else raw_reply,
    }


def run_code_gen_baseline(
    case: Dict[str, Any],
    model: str,
    api_base: str,
    api_key: str,
    repo_root: Path,
    timeout: float = 180.0,
    temperature: float = 0.0,
    seed: Optional[int] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Execute Baseline 2 (Code-Generation LLM) using Oracle Verification
    to evaluate code executability, syntax stability, Calculation Hallucination Rate (CHR),
    and true Code Compliance Rate (CCR).
    """
    import subprocess
    import tempfile

    case_id = case["id"]
    prompt = case["prompt"]
    requires_design = bool(case.get("design_required", False))

    # Inject CAE fixture text for C03/C04 to guarantee informational parity
    prompt = inject_cae_fixtures_if_needed(case, prompt, repo_root)

    system_msg = (
        "You are an expert structural engineer and scientific Python programmer. "
        "Write a standalone Python script using standard libraries (numpy, scipy) to solve the user's "
        "structural engineering problem directly from first principles. "
        "Your script must size the columns and beams, compute the structural metrics, and print a single valid JSON string to stdout with keys:\n"
        '{\n'
        '  "col_b_m": <float, column width in meters>,\n'
        '  "col_h_m": <float, column depth in meters>,\n'
        '  "beam_b_m": <float, beam width in meters>,\n'
        '  "beam_h_m": <float, beam depth in meters>,\n'
        '  "claimed_total_weight_kN": <float, total structural dead load + self-weight in kN>,\n'
        '  "claimed_base_shear_kN": <float, total lateral base shear in kN (0.0 if pure gravity)>,\n'
        '  "claimed_fundamental_period_s": <float, fundamental natural vibration period in seconds (0.0 if not dynamic)>,\n'
        '  "claimed_period_t2_s": <float, second mode period T2 in seconds (0.0 if not modal)>,\n'
        '  "claimed_period_t3_s": <float, third mode period T3 in seconds (0.0 if not modal)>,\n'
        '  "claimed_modal_mass_ratio": <float, modal mass participation ratio (0.0 if not modal)>,\n'
        '  "claimed_peak_displacement_m": <float, peak roof lateral displacement in meters (0.0 if not time-history)>,\n'
        '  "claimed_governing_dcr": <float, governing ACI 318 demand-capacity ratio DCR (1.0 if not design case)>\n'
        '}\n'
        "Output ONLY the python code inside ```python ... ``` fences."
    )

    t_start = time.perf_counter()
    url = f"{api_base.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
    }
    if seed is not None:
        payload["seed"] = seed
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key or 'ollama'}",
    }

    raw_reply = ""
    error_messages = []
    parsed: Dict[str, Any] = {}
    code_execution_ok = False

    try:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            raw_reply = (
                resp_data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
            )

        code_match = re.search(r"```(?:python)?(.*?)```", raw_reply, re.DOTALL)
        script_code = code_match.group(1).strip() if code_match else raw_reply.strip()

        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tf:
            tf.write(script_code)
            temp_script = tf.name

        try:
            res = subprocess.run(
                [sys.executable, temp_script],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if res.returncode == 0:
                code_execution_ok = True
                out_match = re.search(r"\{.*\}", res.stdout, re.DOTALL)
                if out_match:
                    parsed = json.loads(out_match.group(0))
            else:
                error_messages.append(f"Script runtime error: {res.stderr[:300]}")
        finally:
            if os.path.exists(temp_script):
                try:
                    os.unlink(temp_script)
                except Exception:
                    pass

    except Exception as exc:
        error_messages.append(str(exc))
        if verbose:
            print(f"  [Code-Gen Error]: {exc}")

    t_elapsed = round(time.perf_counter() - t_start, 2)

    # Oracle verification
    verifier = OracleVerifier(repo_root=repo_root)
    col_b = parsed.get("col_b_m") or parsed.get("col_b")
    col_h = parsed.get("col_h_m") or parsed.get("col_h")
    beam_b = parsed.get("beam_b_m") or parsed.get("beam_b")
    beam_h = parsed.get("beam_h_m") or parsed.get("beam_h")

    oracle_res = verifier.evaluate(
        case_id=case_id,
        col_b=col_b,
        col_h=col_h,
        beam_b=beam_b,
        beam_h=beam_h,
        claims=parsed,
    )

    expected_metrics = getattr(oracle_res, "expected_metrics", oracle_res.active_metrics) or oracle_res.active_metrics
    if not code_execution_ok:
        chr_pct = 100.0
        code_compliant = False if requires_design else None
        concrete_vol = 0.0
        econ_ratio = None
        gov_dcr = None
        claims_made_list = list(expected_metrics)
        num_claims = max(len(claims_made_list), 1)
        hallucinated_claims = num_claims
    else:
        chr_pct = oracle_res.calculation_hallucination_rate_pct
        code_compliant = oracle_res.code_compliant
        concrete_vol = oracle_res.concrete_volume_m3
        econ_ratio = oracle_res.material_economy_ratio
        gov_dcr = oracle_res.governing_dcr
        claims_made_list = oracle_res.claims_made
        num_claims = max(len(claims_made_list), 1)
        hallucinated_claims = len(oracle_res.hallucinated_metrics)

    if oracle_res.error_message and code_execution_ok:
        error_messages.append(f"OracleVerifier: {oracle_res.error_message}")

    print(
        f"\n--> Result: [CODE-GEN BASELINE] | Executed: {code_execution_ok} | "
        f"Hallucinations: {hallucinated_claims}/{num_claims} (CHR: {chr_pct}%) | "
        f"Oracle DCR: {gov_dcr} | Compliant: {code_compliant} | Time: {t_elapsed}s"
    )

    gov_member_id = oracle_res.governing_member_type
    gov_limit_state = oracle_res.governing_limit_state

    return {
        "case_id": case_id,
        "name": case["name"],
        "group": case.get("group", ""),
        "model": model,
        "configuration": "code_gen",
        "temperature": temperature,
        "seed": seed,
        "design_required": requires_design,
        "success": bool(code_execution_ok and (oracle_res.code_compliant if requires_design else oracle_res.valid_sections)),
        "code_compliant": code_compliant,
        "governing_member_id": gov_member_id,
        "governing_limit_state": gov_limit_state,
        "dcr_flexure": None,
        "dcr_shear": None,
        "dcr_pm": None,
        "final_stage": "PYTHON_SCRIPT_GENERATION",
        "stages_visited": [],
        "wall_clock_time_sec": t_elapsed,
        "turns_used": 1,
        "tools_called": [],
        "missing_expected_tools": case.get("expected_tools", []),
        "tool_failures_count": 0 if code_execution_ok else 1,
        "tool_failures": error_messages,
        "initial_dcr": gov_dcr,
        "final_dcr": gov_dcr,
        "dcr_history": [gov_dcr] if gov_dcr is not None else [],
        "iterations_to_converge": None,
        "nodes_count": 0,
        "elements_count": 0,
        "concrete_volume_m3": concrete_vol,
        "baseline_concrete_volume_m3": case.get("baseline_concrete_volume_m3"),
        "material_economy_ratio": econ_ratio,
        "numerical_claims_count": len(claims_made_list),
        "claims_made": claims_made_list,
        "claims_made_count": len(claims_made_list),
        "omitted_metrics": oracle_res.omitted_metrics if code_execution_ok else [],
        "omitted_metrics_count": len(oracle_res.omitted_metrics) if code_execution_ok else 0,
        "expected_oracle_metrics": expected_metrics,
        "claim_completeness_pct": (
            round(
                (len(set(claims_made_list) & set(expected_metrics)) / max(len(expected_metrics), 1)) * 100.0,
                1,
            )
            if code_execution_ok
            else 0.0
        ),
        "hallucinated_claims_count": hallucinated_claims,
        "calculation_hallucination_rate_pct": chr_pct,
        "active_oracle_metrics": oracle_res.active_metrics,
        "hallucinated_oracle_metrics": oracle_res.hallucinated_metrics if code_execution_ok else list(expected_metrics),
        "oracle_metric_errors": oracle_res.metric_errors,
        "prompt_to_schema_fidelity_passed": False,
        "failure_mode": (
            None
            if (code_execution_ok and (oracle_res.code_compliant if requires_design else oracle_res.valid_sections))
            else (
                "model_construction"
                if (not code_execution_ok or not oracle_res.valid_sections)
                else ("dcr_non_convergence" if (requires_design and not oracle_res.code_compliant) else "runtime_error")
            )
        ),
        "error_messages": error_messages,
        "final_message_snippet": (raw_reply[:200] + "...") if len(raw_reply) > 200 else raw_reply,
    }


def run_heuristic_baseline(
    case: Dict[str, Any],
    repo_root: Path,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Execute Baseline 0: Deterministic Engineering Heuristic (Non-LLM Floor).

    Sizes structural elements via classical civil engineering heuristics:
    - Columns: b = h = max(0.30, round(0.05 * H_total, 2)), rounded to nearest 0.05 m.
    - Beams: b = 0.30 m, h = max(0.35, round(L / 12.0, 2)), rounded to nearest 0.05 m.

    If overstressed (DCR > 1.0), iteratively resizes via the square-root DCR rule:
    h_new = round(h_curr * sqrt(DCR), 2), b_new = round(b_curr * sqrt(DCR), 2).
    """
    t_start = time.perf_counter()
    case_id = case["id"]
    requires_design = case.get("design_required", False)

    verifier = OracleVerifier(repo_root=repo_root)
    catalog = ORACLE_CASES_CATALOG.get(case_id, {})

    num_stories = catalog.get("num_stories", 1)
    story_h = catalog.get("story_height", 3.5)
    total_h = num_stories * story_h
    bay_w = catalog.get("bay_width") or catalog.get("bay_width_x") or 6.0

    # For non-design cases (e.g. eigenvalue dynamics A05/B04 or time-history C01/C02),
    # use prompt/catalog specified section dimensions rather than sizing heuristics
    is_cae = catalog.get("analysis") == "cae_interop"
    if not requires_design or is_cae:
        col_b, col_h = catalog.get("default_col", (0.40, 0.40))
        beam_b, beam_h = catalog.get("default_beam", (0.30, 0.50))
    else:
        # Classical preliminary proportions for design cases
        col_dim = max(0.30, round(round(0.05 * total_h, 2) * 20.0) / 20.0)
        col_b, col_h = col_dim, col_dim
        beam_b = 0.30
        beam_h = max(0.35, round(round(bay_w / 12.0, 2) * 20.0) / 20.0)

    dcr_history: List[float] = []
    max_iters = 6 if requires_design else 1
    oracle_res = None

    for it in range(max_iters):
        oracle_res = verifier.evaluate(
            case_id=case_id,
            col_b=col_b,
            col_h=col_h,
            beam_b=beam_b,
            beam_h=beam_h,
            claims={},
        )
        gov_dcr = oracle_res.governing_dcr
        if gov_dcr is not None:
            dcr_history.append(gov_dcr)

        if not requires_design or (gov_dcr is not None and gov_dcr <= 1.0) or it == max_iters - 1:
            break

        # Scale sections by sqrt(DCR)
        scale_fac = math.sqrt(max(gov_dcr, 1.05))
        col_b = min(1.50, max(col_b + 0.05, round(round(col_b * scale_fac, 2) * 20.0) / 20.0))
        col_h = min(1.50, max(col_h + 0.05, round(round(col_h * scale_fac, 2) * 20.0) / 20.0))
        beam_b = min(1.00, max(beam_b + 0.05, round(round(beam_b * scale_fac, 2) * 20.0) / 20.0))
        beam_h = min(1.50, max(beam_h + 0.05, round(round(beam_h * scale_fac, 2) * 20.0) / 20.0))

    t_elapsed = round(time.perf_counter() - t_start, 2)
    gov_dcr = oracle_res.governing_dcr
    code_compliant = oracle_res.code_compliant
    concrete_vol = oracle_res.concrete_volume_m3
    econ_ratio = oracle_res.material_economy_ratio
    expected_metrics = getattr(oracle_res, "expected_metrics", oracle_res.active_metrics) or oracle_res.active_metrics

    iterations_to_converge = None
    if requires_design and dcr_history:
        initial_dcr = dcr_history[0]
        if initial_dcr is not None and initial_dcr > 1.0:
            iterations_to_converge = (len(dcr_history) - 1) if code_compliant else None
        elif initial_dcr is not None and initial_dcr <= 1.0:
            iterations_to_converge = 0

    if is_cae:
        success = None
        failure_mode = "not_applicable"
    else:
        success = bool(code_compliant if requires_design else oracle_res.valid_sections)
        failure_mode = None if success else ("dcr_non_convergence" if (requires_design and not code_compliant) else "heuristic_failure")

    if verbose:
        print(
            f"\n--> Result: [HEURISTIC BASELINE] | Final DCR: {gov_dcr} | "
            f"Compliant: {code_compliant} | Iterations: {iterations_to_converge} | Time: {t_elapsed}s"
        )

    return {
        "case_id": case_id,
        "name": case["name"],
        "group": case.get("group", ""),
        "model": "deterministic_heuristic",
        "configuration": "heuristic",
        "temperature": 0.0,
        "seed": None,
        "design_required": requires_design,
        "success": success,
        "code_compliant": code_compliant,
        "governing_member_id": oracle_res.governing_member_type,
        "governing_limit_state": oracle_res.governing_limit_state,
        "dcr_flexure": None,
        "dcr_shear": None,
        "dcr_pm": None,
        "final_stage": "HEURISTIC_RULE_BASED",
        "stages_visited": [],
        "wall_clock_time_sec": t_elapsed,
        "turns_used": len(dcr_history),
        "tools_called": ["classical_proportions_rule", "dcr_rescaling_rule"],
        "missing_expected_tools": [],
        "tool_failures_count": 0,
        "tool_failures": [],
        "initial_dcr": dcr_history[0] if dcr_history else gov_dcr,
        "final_dcr": gov_dcr,
        "dcr_history": dcr_history,
        "iterations_to_converge": iterations_to_converge,
        "nodes_count": 0,
        "elements_count": 0,
        "concrete_volume_m3": concrete_vol,
        "baseline_concrete_volume_m3": case.get("baseline_concrete_volume_m3"),
        "material_economy_ratio": econ_ratio,
        "numerical_claims_count": 0,
        "claims_made": [],
        "claims_made_count": 0,
        "omitted_metrics": expected_metrics,
        "omitted_metrics_count": len(expected_metrics),
        "expected_oracle_metrics": expected_metrics,
        "claim_completeness_pct": 0.0,
        "hallucinated_claims_count": 0,
        "calculation_hallucination_rate_pct": 0.0,
        "active_oracle_metrics": oracle_res.active_metrics,
        "hallucinated_oracle_metrics": [],
        "oracle_metric_errors": {},
        "prompt_to_schema_fidelity_passed": None,
        "failure_mode": failure_mode,
        "error_messages": [oracle_res.error_message] if oracle_res.error_message else [],
        "final_message_snippet": f"Heuristic sizing: col=({col_b}x{col_h}), beam=({beam_b}x{beam_h}), DCR={gov_dcr}",
    }


def run_single_case(
    case: Dict[str, Any],
    model: str,
    provider: str,
    api_base: str,
    api_key: str,
    config: str,
    max_turns: int,
    repo_root: Path,
    timeout: float = 300.0,
    temperature: float = 0.0,
    seed: Optional[int] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Execute a single benchmark test case with the neuro-symbolic agent."""
    case_id = case["id"]
    prompt = case["prompt"]
    expected_tools = case.get("expected_tools", [])

    print(f"\n{'='*75}")
    print(f"CASE: [{case_id}] {case['name']} (Group: {case.get('group', 'N/A')} | Config: {config})")
    print(f"{'='*75}")

    if config == "heuristic":
        return run_heuristic_baseline(
            case=case,
            repo_root=repo_root,
            verbose=verbose,
        )
    elif config == "direct_llm":
        return run_direct_llm_baseline(
            case=case,
            model=model,
            api_base=api_base,
            api_key=api_key,
            repo_root=repo_root,
            timeout=timeout,
            temperature=temperature,
            seed=seed,
            verbose=verbose,
        )
    elif config == "code_gen":
        return run_code_gen_baseline(
            case=case,
            model=model,
            api_base=api_base,
            api_key=api_key,
            repo_root=repo_root,
            timeout=timeout,
            temperature=temperature,
            seed=seed,
            verbose=verbose,
        )

    custom_instr = ""
    if config == "ablated":
        custom_instr = (
            "IMPORTANT RESTRICTION FOR THIS RUN: Do not enter an optimization or reflection loop. "
            "Do not call modify_project to resize members after running design checks. "
            "Perform only a single linear pass through the workflow."
        )

    runner = AgentRunner(
        provider=provider,
        model=model,
        base_url=api_base,
        api_key=api_key or "ollama",
        custom_instructions=custom_instr,
        max_turns=max_turns,
        temperature=temperature,
        seed=seed,
        timeout=timeout,
        allow_model_recreation=bool(config != "ablated"),
    )

    if config == "ablated":
        # 2. Physically remove modify_project from tool schemas to enforce no-reflection ablation
        runner.tools = [
            t for t in runner.tools
            if t.get("function", {}).get("name") != "modify_project" and t.get("name") != "modify_project"
        ]

    t_start = time.perf_counter()
    tools_called: List[str] = []
    tool_failures: List[Dict[str, Any]] = []
    stages_visited: List[str] = []
    dcr_history: List[float] = []
    error_messages: List[str] = []
    final_message = ""
    governing_dcr: Optional[float] = None
    passed_flag: Optional[bool] = None

    # Resolve optional multimodal image attachment for Vision cases (C05, C06)
    image_path_str = case.get("image_path")
    resolved_image: Optional[Path] = None
    if image_path_str:
        candidate_img = Path(image_path_str)
        if candidate_img.is_absolute() and candidate_img.exists():
            resolved_image = candidate_img
        else:
            for base_dir in [repo_root, Path(__file__).resolve().parent]:
                candidate = (base_dir / candidate_img).resolve()
                if candidate.exists():
                    resolved_image = candidate
                    break

    try:
        # Pass image attachment if supported by AgentRunner.run_stream
        sig = inspect.signature(runner.run_stream)
        if resolved_image:
            if "attachments" in sig.parameters:
                generator = runner.run_stream(prompt, attachments=[str(resolved_image)])
            elif "image_path" in sig.parameters:
                generator = runner.run_stream(prompt, image_path=str(resolved_image))
            else:
                warn_msg = (
                    f"Runner does not accept multimodal image attachments; "
                    f"image '{resolved_image.name}' for case '{case_id}' was omitted."
                )
                print(f"  [WARNING] {warn_msg}")
                error_messages.append(warn_msg)
                generator = runner.run_stream(prompt)
        else:
            generator = runner.run_stream(prompt)

        for event in generator:
            if isinstance(event, ToolCallEvent):
                tools_called.append(event.tool_name)
                if verbose:
                    print(f"  -> Tool Call: {event.tool_name}")
            elif isinstance(event, ToolResultEvent):
                if not event.ok:
                    tool_failures.append({"tool": event.tool_name, "error": event.error_message})
                    if verbose:
                        print(f"     ! Tool Failed: {event.tool_name}: {event.error_message}")
                if event.data and isinstance(event.data, dict) and "governing_dcr" in event.data:
                    dcr_val = float(event.data["governing_dcr"])
                    dcr_history.append(dcr_val)
            elif isinstance(event, StateUpdateEvent):
                if event.stage not in stages_visited:
                    stages_visited.append(event.stage)
                if verbose:
                    print(f"  [Stage]: {event.stage}")
            elif isinstance(event, ErrorEvent):
                error_messages.append(event.message)
                if verbose:
                    print(f"  [Agent Error]: {event.message}")
            elif isinstance(event, CompleteEvent):
                final_message = event.final_message
                governing_dcr = event.governing_dcr
                passed_flag = event.passed
                if event.governing_dcr is not None and event.governing_dcr not in dcr_history:
                    dcr_history.append(event.governing_dcr)

    except Exception as exc:
        error_messages.append(str(exc))
        if verbose:
            print(f"  [Exception during run]: {exc}")

    t_elapsed = round(time.perf_counter() - t_start, 2)

    # Extract final project state
    project = runner.project
    nodes_count = len(project.model.nodes) if project and hasattr(project, "model") else 0
    elems_count = len(project.model.elements) if project and hasattr(project, "model") else 0
    concrete_vol = calculate_concrete_volume(project)
    final_stage = runner.state.stage.value

    # Determine design requirement
    design_run = "run_design" in tools_called
    requires_design = case.get("design_required")
    if requires_design is None:
        requires_design = (
            ("max_dcr" in case.get("target_constraints", {}))
            or ("run_design" in expected_tools)
            or design_run
        )

    # Strict Task Completion Rate (TCR) check:
    # 1. Model has valid nodes and elements
    # 2. All mandatory expected tools were executed without fatal errors
    has_model = nodes_count > 0 and elems_count > 0
    mandatory_tools = [t for t in expected_tools if t not in NON_MANDATORY_EXPECTED_TOOLS]
    failed_tool_names = {f["tool"] for f in tool_failures}
    successful_tools = [t for t in tools_called if t not in failed_tool_names]
    missing_expected_tools = [t for t in mandatory_tools if t not in successful_tools]

    # Model creation equivalence: if a model was successfully created via any valid creation tool,
    # don't fail for alternative creation tools (e.g. create_model_from_plan_draft vs create_frame_model)
    MODEL_CREATION_TOOLS = {
        "create_frame_model",
        "create_model_from_plan_draft",
        "build_structural_model",
        "create_project",
        "import_from_sap2000",
        "import_from_etabs",
    }
    if has_model and any(t in successful_tools for t in MODEL_CREATION_TOOLS):
        missing_expected_tools = [t for t in missing_expected_tools if t not in MODEL_CREATION_TOOLS]

    if mandatory_tools:
        task_completed = has_model and (len(missing_expected_tools) == 0)
    else:
        analysis_run = any(
            t in successful_tools for t in ["run_analysis", "run_time_history", "run_response_spectrum"]
        )
        interop_or_vision = any(
            t in successful_tools
            for t in ["import_from_sap2000", "import_from_etabs", "create_model_from_plan_draft"]
        )
        task_completed = has_model and (analysis_run or interop_or_vision)

    # Strict artifact verification on disk for drawings and CAE export deliverables (P0.4)
    dxf_found = False
    cae_found = False
    roundtrip_fidelity = None

    if task_completed:
        if case.get("target_constraints", {}).get("drawings_generated") is True or "generate_drawings" in expected_tools:
            dxf_found = False
            candidate_dirs = [
                Path("."),
                Path("./outputs"),
                repo_root / "research_paper" / "drawings",
                repo_root / "outputs",
            ]
            if hasattr(runner, "working_dir") and getattr(runner, "working_dir"):
                candidate_dirs.append(Path(runner.working_dir))
            if hasattr(runner, "output_dir") and getattr(runner, "output_dir"):
                candidate_dirs.append(Path(runner.output_dir))

            for cdir in candidate_dirs:
                if cdir.exists():
                    for dxf_file in cdir.glob("*.dxf"):
                        try:
                            if dxf_file.stat().st_size > 500:
                                import ezdxf
                                doc = ezdxf.readfile(str(dxf_file))
                                if len(doc.modelspace()) >= 1:
                                    dxf_found = True
                                    break
                        except Exception:
                            pass
                if dxf_found:
                    break
            if not dxf_found:
                task_completed = False
                error_messages.append(
                    "Artifact verification failed: DXF drawing file not found or invalid on disk (<500 bytes or 0 entities)."
                )

        if "C03" in case_id or "C04" in case_id:
            if "export_to_sap2000" in tools_called or "export_to_etabs" in tools_called:
                cae_found = False
                candidate_dirs = [
                    Path("."),
                    Path("./outputs"),
                    repo_root / "research_paper" / "benchmarks" / "results",
                    repo_root / "outputs",
                ]
                if hasattr(runner, "working_dir") and getattr(runner, "working_dir"):
                    candidate_dirs.append(Path(runner.working_dir))
                if hasattr(runner, "output_dir") and getattr(runner, "output_dir"):
                    candidate_dirs.append(Path(runner.output_dir))

                for cdir in candidate_dirs:
                    if cdir.exists():
                        for cae_file in list(cdir.glob("*.s2k")) + list(cdir.glob("*.e2k")):
                            try:
                                if cae_file.stat().st_size > 0:
                                    from struct_link import read_project
                                    p_check = read_project(cae_file)
                                    if p_check and hasattr(p_check, "model") and len(p_check.model.nodes) > 0:
                                        cae_found = True
                                        # Numerical roundtrip fidelity check against runner.project.model
                                        orig_nodes = len(runner.project.model.nodes) if runner.project and hasattr(runner.project, "model") else 0
                                        reimp_nodes = len(p_check.model.nodes)
                                        orig_elems = len(runner.project.model.elements) if runner.project and hasattr(runner.project, "model") else 0
                                        reimp_elems = len(p_check.model.elements)
                                        orig_vol = calculate_concrete_volume(runner.project) if runner.project else 0.0
                                        reimp_vol = calculate_concrete_volume(p_check)
                                        vol_err = abs(reimp_vol - orig_vol) / max(orig_vol, 1e-4) if orig_vol > 0 else 0.0

                                        orig_bc = sum(1 for n in runner.project.model.nodes.values() if getattr(n, "is_restrained", False)) if runner.project and hasattr(runner.project, "model") else 0
                                        reimp_bc = sum(1 for n in p_check.model.nodes.values() if getattr(n, "is_restrained", False))

                                        orig_t1 = None
                                        reimp_t1 = None
                                        t1_err = 0.0
                                        try:
                                            from struct_agent.tools.analysis import run_analysis
                                            if runner.project and hasattr(runner.project, "model") and len(runner.project.model.nodes) > 0:
                                                run_analysis(runner.project, analysis_case_id="RT_orig_modal", analysis_type="modal", num_modes=1)
                                                if "RT_orig_modal" in runner.project.analysis_results and runner.project.analysis_results["RT_orig_modal"].modal_result:
                                                    orig_t1 = runner.project.analysis_results["RT_orig_modal"].modal_result.modes[0].period

                                            run_analysis(p_check, analysis_case_id="RT_reimp_modal", analysis_type="modal", num_modes=1)
                                            if "RT_reimp_modal" in p_check.analysis_results and p_check.analysis_results["RT_reimp_modal"].modal_result:
                                                reimp_t1 = p_check.analysis_results["RT_reimp_modal"].modal_result.modes[0].period

                                            if orig_t1 is not None and reimp_t1 is not None:
                                                t1_err = abs(reimp_t1 - orig_t1) / max(orig_t1, 1e-4)
                                        except Exception:
                                            pass

                                        fidelity_passed = (
                                            reimp_nodes == orig_nodes
                                            and reimp_elems == orig_elems
                                            and vol_err < 0.01
                                            and reimp_bc == orig_bc
                                            and (t1_err < 0.01 if (orig_t1 is not None and reimp_t1 is not None) else True)
                                        )
                                        roundtrip_fidelity = {
                                            "file": cae_file.name,
                                            "nodes_original": orig_nodes,
                                            "nodes_reimported": reimp_nodes,
                                            "elements_original": orig_elems,
                                            "elements_reimported": reimp_elems,
                                            "concrete_volume_original_m3": round(orig_vol, 3),
                                            "concrete_volume_reimported_m3": round(reimp_vol, 3),
                                            "volume_rel_error": round(vol_err, 4),
                                            "boundary_conditions_original": orig_bc,
                                            "boundary_conditions_reimported": reimp_bc,
                                            "t1_original": round(orig_t1, 4) if orig_t1 is not None else None,
                                            "t1_reimported": round(reimp_t1, 4) if reimp_t1 is not None else None,
                                            "t1_rel_error": round(t1_err, 4) if (orig_t1 is not None and reimp_t1 is not None) else None,
                                            "fidelity_passed": fidelity_passed,
                                        }
                                        if not fidelity_passed:
                                            task_completed = False
                                            error_messages.append(
                                                f"CAE roundtrip numerical fidelity failed: {roundtrip_fidelity}"
                                            )
                                        break
                            except Exception as c_err:
                                error_messages.append(f"CAE reimport error on {cae_file.name}: {c_err}")
                    if cae_found:
                        break
                if not cae_found:
                    task_completed = False
                    error_messages.append(
                        "Artifact verification failed: exported CAE file (.s2k/.e2k) not found or invalid on disk."
                    )

    # -----------------------------------------------------------------------
    # Independent Re-verification of Final Deliverable
    # -----------------------------------------------------------------------
    oracle_dcr: Optional[float] = None
    oracle_reverified_ok: bool = False
    gov_member_id: Optional[str] = None
    gov_limit_state: Optional[str] = None
    dcr_flexure: Optional[float] = None
    dcr_shear: Optional[float] = None
    dcr_pm: Optional[float] = None

    if requires_design and has_model and runner.project:
        try:
            # Re-solve the actual final model directly to guard against stale DCRs
            run_analysis(runner.project, analysis_case_id="oracle_independent_eval")
            res_des = run_design(runner.project, design_case_id="oracle_independent_eval")
            if res_des.ok and res_des.data:
                oracle_dcr = round(float(res_des.data.get("governing_dcr", 0.0)), 3)
                oracle_reverified_ok = True
                gov_member_id = res_des.data.get("governing_member_id")
                gov_limit_state = res_des.data.get("governing_limit_state")
                dcr_flexure = res_des.data.get("dcr_flexure")
                dcr_shear = res_des.data.get("dcr_shear")
                dcr_pm = res_des.data.get("dcr_pm")
        except Exception as exc:
            error_messages.append(f"Independent oracle re-verification failed: {exc}")

    if requires_design:
        if oracle_reverified_ok and oracle_dcr is not None:
            final_dcr = oracle_dcr
            code_compliant = (oracle_dcr <= 1.00)
        elif governing_dcr is not None:
            final_dcr = governing_dcr
            code_compliant = (governing_dcr <= 1.00)
        else:
            final_dcr = None
            code_compliant = False
    else:
        final_dcr = governing_dcr
        code_compliant = None

    # Extract agent's final member cross-sections from runner.project
    col_b, col_h, beam_b, beam_h = None, None, None, None
    if runner.project and hasattr(runner.project, "model") and runner.project.model:
        sections = getattr(runner.project.model, "sections", [])
        for s in sections:
            sid = (getattr(s, "id", "") or "").lower()
            b_val = getattr(s, "b", None) or getattr(s, "width", None)
            h_val = getattr(s, "h", None) or getattr(s, "height", None) or getattr(s, "depth", None)
            if ("col" in sid) and b_val and h_val and col_b is None:
                col_b, col_h = float(b_val), float(h_val)
            elif ("beam" in sid or "girder" in sid) and b_val and h_val and beam_b is None:
                beam_b, beam_h = float(b_val), float(h_val)
        if (col_b is None or beam_b is None) and sections:
            for s in sections:
                b_val = getattr(s, "b", None) or getattr(s, "width", None)
                h_val = getattr(s, "h", None) or getattr(s, "height", None) or getattr(s, "depth", None)
                if b_val and h_val:
                    if col_b is None:
                        col_b, col_h = float(b_val), float(h_val)
                    elif beam_b is None:
                        beam_b, beam_h = float(b_val), float(h_val)

    # Measure Calculation Hallucinations (CHR) from agent text claims vs. ground-truth physics
    claims_extracted = parse_numerical_claims_from_text(final_message)
    parsed_claims = {
        "claimed_total_weight_kN": claims_extracted.get("total_weight_kN"),
        "claimed_base_shear_kN": claims_extracted.get("base_shear_kN"),
        "claimed_fundamental_period_s": claims_extracted.get("fundamental_period_s"),
        "claimed_period_t2_s": claims_extracted.get("period_t2_s"),
        "claimed_period_t3_s": claims_extracted.get("period_t3_s"),
        "claimed_governing_dcr": claims_extracted.get("governing_dcr"),
        "claimed_modal_mass_ratio": claims_extracted.get("modal_mass_ratio"),
        "claimed_peak_displacement_m": claims_extracted.get("peak_displacement_m"),
    }

    verifier = OracleVerifier(repo_root=repo_root)
    oracle_eval = verifier.evaluate(
        case_id=case_id,
        col_b=col_b,
        col_h=col_h,
        beam_b=beam_b,
        beam_h=beam_h,
        claims=parsed_claims,
    )

    active_oracle_metrics = oracle_eval.active_metrics
    expected_oracle_metrics = getattr(oracle_eval, "expected_metrics", active_oracle_metrics) or active_oracle_metrics
    hallucinated_oracle_metrics = oracle_eval.hallucinated_metrics
    oracle_metric_errors = oracle_eval.metric_errors
    measured_chr_pct = oracle_eval.calculation_hallucination_rate_pct
    num_claims = max(len(active_oracle_metrics), 1)
    num_hallucinations = len(hallucinated_oracle_metrics)

    if not gov_limit_state and oracle_eval.governing_limit_state:
        gov_limit_state = oracle_eval.governing_limit_state
        gov_member_id = oracle_eval.governing_member_type

    # Convergence iterations (N_iter) for self-healing / reflection cases
    iterations_to_converge = None
    if requires_design and dcr_history:
        initial_dcr = dcr_history[0]
        if initial_dcr is not None and initial_dcr > 1.0:
            iterations_to_converge = (len(dcr_history) - 1) if code_compliant else None
        elif initial_dcr is not None and initial_dcr <= 1.0:
            iterations_to_converge = 0

    # Prompt-to-Schema Fidelity Rate (PSFR)
    psfr_passed, psfr_details = evaluate_prompt_to_schema_fidelity(runner.project, case, runner=runner)

    # Failure Mode Taxonomy (Item #10)
    failure_mode = None
    MODEL_CREATION_TOOLS = {
        "create_frame_model", "create_model_from_plan_draft",
        "import_from_sap2000", "import_from_etabs",
    }
    expected_creation = [t for t in expected_tools if t in MODEL_CREATION_TOOLS]
    if not (task_completed and (code_compliant if requires_design else True)):
        if nodes_count == 0 or elems_count == 0 or (expected_creation and not any(t in successful_tools for t in expected_creation)):
            failure_mode = "model_construction"
        elif missing_expected_tools:
            failure_mode = "missing_tool"
        elif (case.get("target_constraints", {}).get("drawings_generated") and not dxf_found) or (("C03" in case_id or "C04" in case_id) and not cae_found):
            failure_mode = "artifact_missing"
        elif psfr_passed is False:
            failure_mode = "schema_fidelity"
        elif requires_design and (final_dcr is None or final_dcr > 1.0):
            failure_mode = "dcr_non_convergence"
        else:
            failure_mode = "runtime_error"

    res = {
        "case_id": case_id,
        "name": case["name"],
        "group": case.get("group", ""),
        "model": model,
        "configuration": config,
        "temperature": temperature,
        "seed": seed,
        "design_required": requires_design,
        "success": task_completed,
        "code_compliant": code_compliant if requires_design else None,
        "governing_member_id": gov_member_id,
        "governing_limit_state": gov_limit_state,
        "dcr_flexure": dcr_flexure,
        "dcr_shear": dcr_shear,
        "dcr_pm": dcr_pm,
        "final_stage": final_stage,
        "stages_visited": stages_visited,
        "wall_clock_time_sec": t_elapsed,
        "turns_used": len(runner.messages) // 2,
        "tools_called": tools_called,
        "missing_expected_tools": missing_expected_tools,
        "tool_failures_count": len(tool_failures),
        "tool_failures": tool_failures,
        "initial_dcr": dcr_history[0] if dcr_history else None,
        "final_dcr": final_dcr,
        "dcr_history": dcr_history,
        "iterations_to_converge": iterations_to_converge,
        "nodes_count": nodes_count,
        "elements_count": elems_count,
        "concrete_volume_m3": concrete_vol,
        "baseline_concrete_volume_m3": case.get("baseline_concrete_volume_m3"),
        "material_economy_ratio": (
            round(concrete_vol / case["baseline_concrete_volume_m3"], 3)
            if (case.get("baseline_concrete_volume_m3") and concrete_vol > 0 and code_compliant)
            else None
        ),
        "numerical_claims_count": len(oracle_eval.claims_made),
        "claims_made": oracle_eval.claims_made,
        "claims_made_count": len(oracle_eval.claims_made),
        "omitted_metrics": oracle_eval.omitted_metrics,
        "omitted_metrics_count": len(oracle_eval.omitted_metrics),
        "expected_oracle_metrics": expected_oracle_metrics,
        "claim_completeness_pct": round(
            (len(set(oracle_eval.claims_made) & set(expected_oracle_metrics)) / max(len(expected_oracle_metrics), 1)) * 100.0,
            1,
        ),
        "hallucinated_claims_count": num_hallucinations,
        "calculation_hallucination_rate_pct": measured_chr_pct,
        "active_oracle_metrics": active_oracle_metrics,
        "hallucinated_oracle_metrics": hallucinated_oracle_metrics,
        "oracle_metric_errors": oracle_metric_errors,
        "prompt_to_schema_fidelity_passed": psfr_passed,
        "prompt_to_schema_fidelity_details": psfr_details,
        "failure_mode": failure_mode,
        "roundtrip_fidelity": roundtrip_fidelity,
        "error_messages": error_messages,
        "final_message_snippet": (
            (final_message[:200] + "...") if len(final_message) > 200 else final_message
        ),
    }

    if task_completed and not requires_design:
        status_badge = "[SUCCESS]"
    elif task_completed and code_compliant:
        status_badge = "[SUCCESS - COMPLIANT]"
    elif task_completed:
        status_badge = "[COMPLETED - OVERSTRESSED]"
    else:
        status_badge = (
            f"[FAILED - MISSING TOOLS: {missing_expected_tools}]"
            if missing_expected_tools
            else "[FAILED]"
        )

    dcr_str = f"DCR: {res['final_dcr']:.3f}" if res["final_dcr"] is not None else "DCR: N/A"
    print(f"\n--> Result: {status_badge} | Stage: {final_stage} | {dcr_str} | Time: {t_elapsed}s")
    return res


def main():
    parser = argparse.ArgumentParser(description="Autonomous Structural AI Benchmarking Suite")
    parser.add_argument("--model", type=str, default="gemini-3.8-flash", help="Model identifier")
    parser.add_argument("--provider", type=str, default="auto", help="Provider: ollama, native, gemini, etc.")
    parser.add_argument("--api-base", type=str, default="", help="Custom API endpoint (e.g. http://localhost:11434/v1)")
    parser.add_argument("--api-key", type=str, default="", help="API key")
    parser.add_argument("--cases", type=str, default="all", help="Case ID(s) comma-separated, group name (Group_A_2D), or 'all'")
    parser.add_argument(
        "--config",
        type=str,
        default="full_agent",
        choices=["full_agent", "ablated", "direct_llm", "code_gen", "heuristic"],
        help="Benchmark configuration (full_agent, ablated, direct_llm, code_gen, heuristic)",
    )
    parser.add_argument("--max-turns", type=int, default=20, help="Maximum dialogue turns per case")
    parser.add_argument("--timeout", type=float, default=300.0, help="LLM request timeout in seconds (default: 300.0)")
    parser.add_argument("--temperature", type=float, default=None, help="Sampling temperature (default: 0.2 if seeds > 1, else 0.0)")
    parser.add_argument("--seeds", type=int, default=None, help="Number of random seed repetitions per case (default: 5 for full_agent/ablated, 1 for single-shot/heuristic)")
    parser.add_argument("--cases-file", type=str, default="", help="Custom benchmark cases JSON path")
    parser.add_argument("--output-dir", type=str, default="", help="Custom output directory for results")
    parser.add_argument("--update-file", type=str, default="", help="Existing results JSON file to update in-place with new case run(s)")
    args = parser.parse_args()

    benchmarks_dir = Path(__file__).resolve().parent
    repo_root = benchmarks_dir.parents[1]

    # Automatically load GEMINI_API_KEY or other keys from struct_agent/.env or workspace .env
    for env_file in [repo_root / "struct_agent" / ".env", repo_root / ".env"]:
        if env_file.exists():
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip('"').strip("'")
                        if k and k not in os.environ:
                            os.environ[k] = v

    cases_file = Path(args.cases_file) if args.cases_file else benchmarks_dir / "benchmark_cases.json"
    output_dir = Path(args.output_dir) if args.output_dir else benchmarks_dir / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not cases_file.exists():
        print(f"Error: Benchmark cases file not found at: {cases_file}")
        sys.exit(1)

    all_cases = load_benchmark_cases(cases_file)

    # Filter cases
    selected_cases = []
    if args.cases.lower() == "all":
        selected_cases = all_cases
    elif args.cases.lower().startswith("group_"):
        target_group = args.cases.lower()
        selected_cases = [c for c in all_cases if c.get("group", "").lower() == target_group]
    else:
        req_ids = [x.strip() for x in args.cases.split(",")]
        selected_cases = [
            c for c in all_cases
            if any(c["id"] == rid or c["id"].lower().startswith(rid.lower()) for rid in req_ids)
        ]

    if not selected_cases:
        print(f"Warning: No benchmark cases matched filter: {args.cases}")
        sys.exit(1)

    # Configure endpoint
    api_base = args.api_base
    provider = args.provider
    if not api_base:
        if "gemini" in args.model.lower() or provider == "gemini":
            api_base = "https://generativelanguage.googleapis.com/v1beta/openai"
            provider = "gemini"
        else:
            api_base = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
            if not api_base.endswith("/v1"):
                api_base = f"{api_base.rstrip('/')}/v1"
            if provider == "auto":
                provider = "native"

    api_key = (
        args.api_key
        or os.environ.get("GEMINI_API_KEY", "")
        or os.environ.get("OPENAI_API_KEY", "ollama")
    )

    print("\n" + "=" * 80)
    print(" STRUCTURAL ENGINEERING AGENT: 24-CASE BENCHMARK SUITE EXECUTION")
    print("=" * 80)
    print(f" Model:         {args.model}")
    print(f" Provider:      {provider}")
    print(f" API Base:      {api_base}")
    print(f" Configuration: {args.config}")
    if args.config == "heuristic":
        seeds_count = 1
    elif args.seeds is None:
        seeds_count = 5 if args.config in ("full_agent", "ablated") else 1
    else:
        seeds_count = max(args.seeds, 1)

    run_temperature = (
        args.temperature
        if args.temperature is not None
        else (0.2 if seeds_count > 1 else 0.0)
    )

    print(f" Temperature:   {run_temperature}")
    print(f" Total Cases:   {len(selected_cases)}")
    print(f" Timestamp:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    results = []
    case_results_mean_std: Dict[str, Any] = {}

    for case in selected_cases:
        seed_runs = []
        for s_idx in range(seeds_count):
            current_seed = 42 + s_idx
            if seeds_count > 1:
                print(f"\n--- [Seed {s_idx + 1}/{seeds_count} (seed={current_seed}, temp={run_temperature})] Executing case {case['id']} ---")
            case_res = run_single_case(
                case=case,
                model=args.model,
                provider=provider,
                api_base=api_base,
                api_key=api_key,
                config=args.config,
                max_turns=args.max_turns,
                repo_root=repo_root,
                timeout=args.timeout,
                temperature=run_temperature,
                seed=current_seed,
            )
            case_res["seed_index"] = s_idx
            case_res["random_seed"] = current_seed
            seed_runs.append(case_res)
            results.append(case_res)

        if seeds_count > 1:
            import numpy as np
            tcrs = [1.0 if r["success"] else 0.0 for r in seed_runs]
            ccrs = [1.0 if r.get("code_compliant") is True else 0.0 for r in seed_runs if r.get("code_compliant") is not None]
            chrs = [r.get("calculation_hallucination_rate_pct", 0.0) for r in seed_runs]
            runtimes = [r["wall_clock_time_sec"] for r in seed_runs]
            etas = [r["material_economy_ratio"] for r in seed_runs if r.get("material_economy_ratio") is not None]

            case_results_mean_std[case["id"]] = {
                "tcr_mean": round(float(np.mean(tcrs)) * 100.0, 1),
                "tcr_std": round(float(np.std(tcrs)) * 100.0, 1),
                "ccr_mean": round(float(np.mean(ccrs)) * 100.0, 1) if ccrs else None,
                "ccr_std": round(float(np.std(ccrs)) * 100.0, 1) if ccrs else None,
                "chr_mean": round(float(np.mean(chrs)), 1),
                "chr_std": round(float(np.std(chrs)), 1),
                "runtime_mean": round(float(np.mean(runtimes)), 2),
                "runtime_std": round(float(np.std(runtimes)), 2),
                "material_economy_mean": round(float(np.mean(etas)), 3) if etas else None,
                "material_economy_std": round(float(np.std(etas)), 3) if etas else None,
            }

    out_file = None
    if args.update_file:
        update_path = Path(args.update_file)
        if not update_path.exists():
            print(f"Error: Update file does not exist: {update_path}")
            sys.exit(1)
        with open(update_path, "r", encoding="utf-8") as f:
            existing_data = json.load(f)

        existing_cases = existing_data.get("case_results", [])
        new_cases_map = {r["case_id"]: r for r in results}

        merged_results = []
        replaced_ids = set()
        for ec in existing_cases:
            cid = ec.get("case_id")
            if cid in new_cases_map:
                merged_results.append(new_cases_map[cid])
                replaced_ids.add(cid)
            else:
                merged_results.append(ec)

        for cid, nr in new_cases_map.items():
            if cid not in replaced_ids:
                merged_results.append(nr)

        results = merged_results
        out_file = update_path

    # Compute aggregate metrics
    n_total = len(results)
    n_success = sum(1 for r in results if r["success"])
    design_cases = [r for r in results if r.get("design_required", False)]
    n_design_cases = len(design_cases)
    n_compliant = sum(1 for r in design_cases if r.get("code_compliant") is True)
    avg_time = round(sum(r["wall_clock_time_sec"] for r in results) / max(n_total, 1), 2)
    tcr = round((n_success / max(n_total, 1)) * 100, 1)
    ccr = round((n_compliant / max(n_design_cases, 1)) * 100, 1) if n_design_cases > 0 else None

    # Calculation Hallucination Rate (CHR) across active metrics (measured, not hardcoded)
    total_claims = sum(r.get("claims_made_count", r.get("numerical_claims_count", 0)) for r in results)
    total_hallucinations = sum(r.get("hallucinated_claims_count", 0) for r in results)
    avg_chr = (
        round((total_hallucinations / max(total_claims, 1)) * 100.0, 1)
        if total_claims > 0
        else 0.0
    )
    non_heuristic = [r for r in results if r.get("configuration") != "heuristic"]
    total_expected_metrics = sum(len(r.get("expected_oracle_metrics", r.get("active_oracle_metrics", []))) for r in non_heuristic)
    total_matched_claims = sum(
        len(set(r.get("claims_made", [])) & set(r.get("expected_oracle_metrics", r.get("active_oracle_metrics", []))))
        for r in non_heuristic
        if not (r.get("configuration") == "code_gen" and not r.get("success") and r.get("claim_completeness_pct", 0.0) == 0.0)
    )
    avg_claim_completeness = (
        round((total_matched_claims / max(total_expected_metrics, 1)) * 100.0, 1)
        if total_expected_metrics > 0
        else None
    )

    failure_modes_summary: Dict[str, int] = {}
    for r in results:
        fm = r.get("failure_mode")
        if fm:
            failure_modes_summary[fm] = failure_modes_summary.get(fm, 0) + 1

    # Prompt-to-Schema Fidelity Rate (PSFR) for agent configurations
    psfr_evaluated = [
        r for r in results
        if r.get("prompt_to_schema_fidelity_passed") is not None and args.config in ("full_agent", "ablated")
    ]
    n_psfr_passed = sum(1 for r in psfr_evaluated if r.get("prompt_to_schema_fidelity_passed") is True)
    psfr_pct = (
        round((n_psfr_passed / max(len(psfr_evaluated), 1)) * 100.0, 1)
        if psfr_evaluated
        else None
    )

    # Convergence iterations for self-healing reflection cases
    reflection_cases = [
        r for r in results if (r.get("initial_dcr") is not None and r["initial_dcr"] > 1.0)
    ]
    n_reflection = len(reflection_cases)
    converged_reflection = [
        r for r in reflection_cases if r.get("iterations_to_converge") is not None
    ]
    avg_iterations = (
        round(
            sum(r["iterations_to_converge"] for r in converged_reflection)
            / len(converged_reflection),
            2,
        )
        if converged_reflection
        else None
    )

    valid_etas = [
        r["material_economy_ratio"]
        for r in results
        if r.get("material_economy_ratio") is not None
    ]
    avg_eta = round(sum(valid_etas) / len(valid_etas), 3) if valid_etas else None

    # Per-case averages across seeds
    by_case_eta: Dict[str, List[float]] = {}
    by_case_iters: Dict[str, List[float]] = {}
    for r in results:
        cid = r.get("case_id", "")
        if r.get("material_economy_ratio") is not None:
            by_case_eta.setdefault(cid, []).append(r["material_economy_ratio"])
        if r.get("iterations_to_converge") is not None:
            by_case_iters.setdefault(cid, []).append(r["iterations_to_converge"])

    avg_eta_per_case = (
        round(sum(sum(vals) / len(vals) for vals in by_case_eta.values()) / len(by_case_eta), 3)
        if by_case_eta else None
    )
    avg_iters_per_case = (
        round(sum(sum(vals) / len(vals) for vals in by_case_iters.values()) / len(by_case_iters), 2)
        if by_case_iters else None
    )

    summary = {
        "model": args.model,
        "configuration": args.config,
        "timestamp": datetime.now().isoformat(),
        "temperature": run_temperature,
        "seeds": seeds_count,
        "total_cases": n_total,
        "total_runs": n_total,
        "unique_cases": len({r["case_id"] for r in results}),
        "design_cases": n_design_cases,
        "design_runs": n_design_cases,
        "unique_design_cases": len({r["case_id"] for r in results if r.get("design_required")}),
        "successful_cases": n_success,
        "compliant_cases": n_compliant,
        "task_completion_rate_pct": tcr,
        "code_compliance_rate_pct": ccr,
        "calculation_hallucination_rate_pct": avg_chr,
        "claim_completeness_rate_pct": avg_claim_completeness,
        "failure_modes_summary": failure_modes_summary,
        "prompt_to_schema_fidelity_rate_pct": psfr_pct,
        "reflection_cases_count": n_reflection,
        "converged_reflection_cases_count": len(converged_reflection),
        "avg_convergence_iterations": avg_iterations,
        "avg_convergence_iterations_per_case": avg_iters_per_case,
        "avg_material_economy_ratio": avg_eta,
        "avg_material_economy_ratio_per_case": avg_eta_per_case,
        "avg_runtime_sec": avg_time,
        "case_results": results,
    }
    if seeds_count > 1:
        summary["case_results_mean_std"] = case_results_mean_std

    # Save to unique timestamped JSON if not updating an existing file
    if out_file is None:
        safe_model = sanitize_filename(args.model)
        safe_config = sanitize_filename(args.config)
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = output_dir / f"results_{safe_model}_{safe_config}_{timestamp_str}.json"
        counter = 1
        while out_file.exists():
            out_file = output_dir / f"results_{safe_model}_{safe_config}_{timestamp_str}_{counter}.json"
            counter += 1

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    ccr_str = (
        f"{n_compliant} / {n_design_cases} ({ccr}%)"
        if n_design_cases > 0
        else "N/A (no design cases)"
    )

    print("\n" + "=" * 80)
    print(" BENCHMARK RUN COMPLETE")
    print("=" * 80)
    print(f" Completed (TCR):         {n_success} / {n_total} ({tcr}%)")
    print(f" Code-Compliant (CCR):    {ccr_str}")
    print(f" Hallucination Rate (CHR):{avg_chr:.1f}%")
    if psfr_pct is not None:
        print(f" Schema Fidelity (PSFR):  {n_psfr_passed} / {len(psfr_evaluated)} ({psfr_pct}%)")
    if n_reflection > 0:
        iter_str = (
            f"Avg {avg_iterations} iters" if avg_iterations is not None else "Did not converge"
        )
        print(f" Reflection Convergence:  {len(converged_reflection)} / {n_reflection} ({iter_str})")
    if avg_eta is not None:
        print(f" Material Economy (eta):  {avg_eta:.3f} [V_agent / V_baseline]")
    print(f" Average Runtime:         {avg_time}s / case")
    print(f" Detailed Log Saved:      {out_file}")
    print("=" * 80)


if __name__ == "__main__":
    main()