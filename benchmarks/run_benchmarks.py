"""
Autonomous Structural Engineering Benchmark Execution Harness
=============================================================

Runs the benchmark suite (``benchmark_cases.json``, schema in ``case_schema.py``) under five
configurations and records per-run metrics to timestamped JSON files in ``results/``:

* ``full_agent``  — neuro-symbolic agent with tools and closed-loop reflection
* ``ablated``     — same agent without ``modify_project``, and without re-creating or resizing the model after design
* ``direct_llm``  — single-shot LLM answer (sections + claimed values), no tools
* ``code_gen``    — single-shot LLM-written Python script (numpy/scipy), executed in isolation
* ``heuristic``   — deterministic rule-of-thumb sizing with sqrt(DCR) resizing (no LLM)

Every configuration is scored by the deterministic oracle on the case's canonical model:
code compliance (governing DCR <= 1.0 within the stated design space), calculation hallucination
rate on the metrics the prompt asks for, claim completeness, material economy against the
minimum-volume baseline, and — for agents — task completion, prompt-to-schema fidelity,
deliverable files, reflection convergence, and robustness-probe behavior.

Usage
-----
python research_paper/benchmarks/run_benchmarks.py --model gemini-3.8-flash --cases all --seeds 5
python research_paper/benchmarks/run_benchmarks.py --model gemini-3.8-flash --config ablated --cases all --seeds 5
python research_paper/benchmarks/run_benchmarks.py --model qwen3.5:9b --config direct_llm --cases A_2D
python research_paper/benchmarks/run_benchmarks.py --config heuristic --cases all
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BENCHMARKS_DIR = Path(__file__).resolve().parent
REPO_ROOT = BENCHMARKS_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research_paper.benchmarks.benchmark_utils import (  # noqa: E402
    DesignCheckTracker,
    calculate_concrete_volume,
    evaluate_prompt_to_schema_fidelity,
    gravity_load_totals,
    lateral_load_totals,
    parse_numerical_claims_from_text,
)
from research_paper.benchmarks.case_schema import METRICS, BenchmarkCase, SectionPair, load_cases  # noqa: E402
from research_paper.benchmarks.oracle_verifier import OracleResult, OracleVerifier  # noqa: E402
from struct_agent import (  # noqa: E402
    AgentRunner,
    CompleteEvent,
    ErrorEvent,
    StateUpdateEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from struct_agent.vision.encoding import build_multimodal_message  # noqa: E402
from struct_core import conversion_factor  # noqa: E402

# Diagnostic tools and conditional resizing are not required for task completion.
NON_MANDATORY_EXPECTED_TOOLS = {
    "modify_project",
    "validate_model",
    "inspect_project",
    "inspect_analysis_results",
    "inspect_dynamic_results",
    "inspect_design_results",
    "inspect_detailing_results",
}
MODEL_CREATION_TOOLS = {
    "create_frame_model",
    "create_model_from_plan_draft",
    "create_project",
    "import_from_sap2000",
    "import_from_etabs",
}
# AgentRunner settings per agent configuration; the ablation removes the resizing tool (and its prompt
# stage) and re-creating or resizing the model after a design check. Also used to replay a run (audit_results).
RUNNER_SETTINGS = {
    "full_agent": {},
    "ablated": {"allow_resizing": False, "allow_model_recreation": False},
}
METRIC_DESCRIPTIONS = {
    "total_weight": "total dead load W = member self-weight + superimposed dead load",
    "base_shear": "X-direction base shear Vb",
    "fundamental_period": "fundamental period T1 in seconds",
    "period_t2": "second-mode period T2 in seconds",
    "period_t3": "third-mode period T3 in seconds",
    "modal_mass_ratio": "cumulative X-direction modal mass participation ratio of the first three modes (0-1)",
    "peak_roof_displacement": "peak roof displacement relative to the base",
    "max_base_reaction": "maximum vertical support reaction under 1.2D + 1.6L",
    "governing_dcr": "governing demand-capacity ratio over all checks: beams, columns, beam-column joints, "
                     "and story drift and stability",
}
BEHAVIOR_PATTERNS = {
    "report_infeasible": r"infeasib|not (?:be )?possible|impossible|"
                         r"(?:cannot|can ?not|can't|could not|couldn't|unable to) (?:be )?(?:satisf|achiev|meet|design|compl)|"
                         r"no (?:feasible|adequate|compliant) (?:design|section)|exceed(?:s|ed)? the (?:limit|cap)|"
                         # "no column-beam combination satisfying the limits can achieve ACI 318-25 compliance", and
                         # "no section within the 0.30 m cap is adequate" (one sentence: a decimal point does not end it)
                         r"\bno (?:[^.\n]|\.(?=\d)){0,60}?(?:combination|section|size|design|solution)"
                         r"(?:[^.\n]|\.(?=\d)){0,80}?"
                         r"\b(?:(?:can|could|will|would) (?:achieve|satisfy|meet|comply|work)|"
                         # minimax direct D02: 'No reinforcement-detailed design satisfying DCR <= 1.0 exists'
                         r"(?:is|are) (?:adequate|sufficient|feasible|compliant)|exists?)|"
                         # gemma code_gen D02: 'The demand exceeds capacity for the given architectural constraints'
                         r"\bdemands? exceeds? (?:the )?capacity|"
                         r"insufficient|inadequate|not adequate|undersized|\bfail(?:s|ed|ure)?\b|"
                         r"prevents? (?:[^.]|\.(?=\d)){0,60}(?:achiev|satisf|meet)",
    "declare_assumption": r"assum|not (?:specified|given|provided|stated)|missing|clarif|"
                          # a request for the input: "please specify", "could you provide"
                          r"please (?:provide|confirm|specify|give|tell|share|let me know)|"
                          r"(?:could|can|would) you (?:please )?(?:provide|confirm|specify|give|tell|share|let me know)",
    "flag_contradiction": r"inconsisten|contradict|conflict|mismatch|discrepan|does not (?:match|add up)|"
                          r"(?:3|three)\s*[x×]\s*5(?:\.0)?\s*m?\s*=\s*15|"
                          # D04: the stated 18 m and the bays' 15 m named in one sentence ("the prompt requested
                          # 18.0 m, but ... 15.0 m total"); a restatement of the prompt never names 15 m
                          r"\b18(?:\.0+)?\s*m\b(?:(?!\.\s)[^\n]){0,150}?\b15(?:\.0+)?\s*m\b|"
                          r"\b15(?:\.0+)?\s*m\b(?:(?!\.\s)[^\n]){0,150}?\b18(?:\.0+)?\s*m\b",
}


def sanitize_filename(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-\.]", "_", name)


def _length_unit(case: BenchmarkCase) -> str:
    return case.spec.units.split(",")[1].strip()


def _force_unit(case: BenchmarkCase) -> str:
    return case.spec.units.split(",")[0].strip()


def ccr_eligible(case: BenchmarkCase) -> bool:
    """Design cases with a feasible, fully specified problem count toward the code-compliance rate."""
    return case.design_required and case.taxonomy.probe in (None, "units")


# =============================================================================
# Shared scoring record
# =============================================================================
def build_record(
    case: BenchmarkCase,
    *,
    config: str,
    model: str,
    temperature: float,
    seed: Optional[int],
    oracle: OracleResult,
    success: Optional[bool],
    elapsed: float,
    final_message: str = "",
    tools_called: Optional[List[str]] = None,
    tool_failures: Optional[List[Dict[str, Any]]] = None,
    missing_expected_tools: Optional[List[str]] = None,
    dcr_history: Optional[List[float]] = None,
    final_stage: str = "",
    stages_visited: Optional[List[str]] = None,
    turns_used: int = 1,
    nodes_count: int = 0,
    elements_count: int = 0,
    psfr: Optional[Tuple[bool, Dict[str, Any]]] = None,
    deliverables: Optional[Dict[str, Any]] = None,
    uniform_sections: Optional[bool] = None,
    error_messages: Optional[List[str]] = None,
    final_design_verified: Optional[bool] = None,
) -> Dict[str, Any]:
    sol = oracle.solution
    # Tool-using agents must have checked the sections they deliver (run_design after the last model change)
    compliant = oracle.code_compliant and final_design_verified is not False
    design = sol.design or {}
    final_dcr = sol.governing_dcr
    history = list(dcr_history or [])
    iterations = None
    if case.spec.initial_sections is not None and history and compliant:
        iterations = next((i for i, d in enumerate(history) if d <= case.deliverables.max_dcr), len(history) - 1)
    behavior = None
    if case.evaluation.expected_behavior is not None:
        behavior = assess_expected_behavior(case, final_message, oracle)
    # A probe that withholds an input (D03, D04) is answered by asking for it before modelling: the run is
    # complete, and there is no model whose fidelity could be checked
    if case.evaluation.withheld and nodes_count == 0 and behavior:
        success, psfr = True, None
    baseline = case.baseline_design
    return {
        "case_id": case.id,
        "name": case.name,
        "group": case.group,
        "difficulty": case.difficulty.label,
        "taxonomy": case.taxonomy.model_dump(),
        "model": model,
        "configuration": config,
        "temperature": temperature,
        "seed": seed,
        "design_required": ccr_eligible(case),
        "design_task": case.deliverables.design,
        "success": success,
        "code_compliant": compliant if ccr_eligible(case) or case.deliverables.design == "check" else None,
        "final_design_verified": final_design_verified,
        "design_space_violations": oracle.design_space_violations,
        "uniform_sections": uniform_sections,
        "final_sections": None if sol.sections is None else sol.sections.model_dump(),
        "governing_member_id": design.get("governing_member_id"),
        "governing_limit_state": design.get("governing_limit_state"),
        "dcr_flexure": design.get("dcr_flexure"),
        "dcr_shear": design.get("dcr_shear"),
        "initial_dcr": history[0] if history else None,
        "reference_initial_dcr": None if case.reference_solution is None else case.reference_solution.initial_dcr,
        "final_dcr": final_dcr,
        "dcr_history": history,
        "iterations_to_converge": iterations,
        "concrete_volume": sol.concrete_volume,
        "baseline_concrete_volume": None if baseline is None or not baseline.feasible else baseline.concrete_volume,
        "material_economy_ratio": oracle.material_economy_ratio,
        # Metrics the oracle can score (a withheld input can leave some without a reference value)
        "expected_oracle_metrics": list(oracle.claims_made) + list(oracle.omitted_metrics),
        "claims_made": oracle.claims_made,
        "claims_made_count": len(oracle.claims_made),
        "omitted_metrics": oracle.omitted_metrics,
        "claim_completeness_pct": oracle.claim_completeness_pct,
        "hallucinated_oracle_metrics": oracle.hallucinated_metrics,
        "hallucinated_claims_count": len(oracle.hallucinated_metrics),
        "calculation_hallucination_rate_pct": oracle.calculation_hallucination_rate_pct,
        "oracle_metric_errors": oracle.metric_errors,
        "oracle_metrics": sol.metrics,
        "oracle_error": sol.error,
        "prompt_to_schema_fidelity_passed": None if psfr is None else psfr[0],
        "prompt_to_schema_fidelity_details": None if psfr is None else psfr[1],
        "deliverables": deliverables,
        "expected_behavior": case.evaluation.expected_behavior,
        "behavior_passed": behavior,
        "final_stage": final_stage,
        "stages_visited": stages_visited or [],
        "wall_clock_time_sec": round(elapsed, 2),
        "turns_used": turns_used,
        "tools_called": tools_called or [],
        "missing_expected_tools": missing_expected_tools or [],
        "tool_failures_count": len(tool_failures or []),
        "tool_failures": tool_failures or [],
        "nodes_count": nodes_count,
        "elements_count": elements_count,
        "failure_mode": None,
        "error_messages": error_messages or [],
        "final_message_snippet": (final_message[:300] + "...") if len(final_message) > 300 else final_message,
    }


def assess_expected_behavior(case: BenchmarkCase, final_message: str, oracle: OracleResult) -> bool:
    """Robustness probes: the response must acknowledge the problem instead of silently proceeding."""
    behavior = case.evaluation.expected_behavior
    acknowledged = bool(re.search(BEHAVIOR_PATTERNS[behavior], final_message or "", re.IGNORECASE))
    if behavior == "report_infeasible":
        # Honest infeasibility: no compliant design within the limits is claimed, and the response says so
        return acknowledged and not oracle.code_compliant and not oracle.design_space_violations
    return acknowledged


def classify_failure(record: Dict[str, Any]) -> Optional[str]:
    if record["configuration"] == "heuristic" or record["success"] is None:
        return None
    # Check cases (design_task 'check') succeed by reporting the existing design, compliant or not
    judged_compliance = record["code_compliant"] if record["design_task"] == "design" else None
    ok = record["success"] and (judged_compliance is not False)
    if record["behavior_passed"] is not None:
        ok = ok and record["behavior_passed"]
    if ok:
        return None
    # Setup failures, not the model's: the LLM server failed (a crash, a refused connection) or the context
    # window ended the run or dropped the task from the prompt. Such runs are re-run (--resume).
    if record.get("provider_error"):
        return "provider_error"
    if record.get("final_response_truncated") or record.get("prompt_truncations"):
        return "context_limit"
    if record.get("final_response_capped"):
        return "runaway_generation"  # the model generated (mostly thought) until the cap or the window cut it
    if record["configuration"] in ("direct_llm", "code_gen") and not record["success"]:
        return "runtime_error"  # no usable answer: the script failed, or no JSON answer was found
    if record["nodes_count"] == 0 and record["configuration"] in ("full_agent", "ablated"):
        return "model_construction"
    if record["missing_expected_tools"]:
        return "missing_tool"
    if record["deliverables"] and not all(record["deliverables"].values()):
        return "artifact_missing"
    if record["prompt_to_schema_fidelity_passed"] is False:
        return "schema_fidelity"
    if record["behavior_passed"] is False:
        return "probe_behavior"
    if record["design_space_violations"]:
        return "design_space_violation"
    if record.get("final_design_verified") is False:
        return "unverified_design"
    if judged_compliance is False:
        return "dcr_non_convergence"
    return "runtime_error"


# =============================================================================
# Single-shot baselines (direct LLM, code generation)
# =============================================================================
def single_shot_messages(case: BenchmarkCase, mode: str) -> List[Dict[str, Any]]:
    length, force = _length_unit(case), _force_unit(case)
    keys = []
    if case.spec.sections is None and case.spec.cae is None:
        keys += [f'"{k}": <float, {d} in {length}>' for k, d in (
            ("col_b", "column width"), ("col_h", "column depth"), ("beam_b", "beam width"), ("beam_h", "beam depth"))]
    units = {"total_weight": force, "base_shear": force, "max_base_reaction": force, "peak_roof_displacement": length,
             **answer_units(case)}  # the prompt's unit where it asks for another (the schema must not contradict it)
    keys += [f'"{m}": <float, {METRIC_DESCRIPTIONS[m]}{" in " + units[m] if m in units else ""}>'
             for m in case.evaluation.required_metrics]
    # The JSON-only answer has no prose: without this field the robustness probes (stating an infeasible design, a
    # missing input, a contradiction) could never be answered (direct_llm passed 0 of 7). Neutral, so it hints at none.
    keys.append('"notes": <string, any remarks for the user about the problem or your answer, or "" if none>')
    schema = "{\n  " + ",\n  ".join(keys) + "\n}"
    if mode == "direct_llm":
        system = ("You are an expert structural engineer. Solve the user's problem and output ONLY a JSON object "
                  f"with these keys (no markdown, no comments):\n{schema}")
    else:
        system = ("You are an expert structural engineer and scientific Python programmer. Write one standalone "
                  "Python script (numpy/scipy only) that solves the user's problem from first principles and prints "
                  f"a single JSON object with these keys to stdout:\n{schema}\n"
                  "Relative file paths in the problem are relative to the script's working directory. "
                  "Output only the code inside ```python ... ``` fences.")
    prompt = case.prompt
    if case.spec.cae is not None:  # informational parity: the agent reads this file through its tools
        text = (REPO_ROOT / case.spec.cae.file).read_text(encoding="utf-8", errors="replace")
        prompt += f"\n\n--- Contents of {case.spec.cae.file} ---\n{text}\n--- End of file ---"
    images = [str(REPO_ROOT / case.spec.plan_image)] if case.spec.plan_image else None
    return [{"role": "system", "content": system}, build_multimodal_message(prompt, images)]


def chat_completion(api_base: str, api_key: str, model: str, messages: List[Dict[str, Any]],
                    temperature: float, seed: Optional[int], timeout: float,
                    max_tokens: Optional[int] = None, reasoning_effort: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    """The reply text and its log entry: token usage, the finish reason ('length' when the token limit cut it
    off) and the length of a thinking model's reasoning."""
    payload: Dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
    if seed is not None:
        payload["seed"] = seed
    if max_tokens:
        payload["max_tokens"] = max_tokens
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    req = urllib.request.Request(
        f"{api_base.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key or 'ollama'}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    choice = data.get("choices", [{}])[0]
    message = choice.get("message", {})
    usage = data.get("usage") or {}
    entry = {
        "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
        "finish_reason": choice.get("finish_reason"), "reasoning_chars": len(message.get("reasoning") or ""),
    }
    if entry["finish_reason"] == "length":
        entry["reasoning_tail"] = reasoning_tail(message.get("reasoning"))
    return message.get("content", "") or "", entry


def reasoning_tail(reasoning: Optional[str]) -> str:
    """The end of a cut-off response's reasoning: shows what a runaway was doing (gemma code_gen B01 thought 131k
    tokens in one run and answered in 13k in another, at temperature 0)."""
    return (reasoning or "")[-2000:]


def script_from_reply(reply: str) -> str:
    """The code_gen script: the last Python code block of the reply (a model may draft a block and then write the
    final one: qwen B03 ended a draft with 'I will write a cleaner version in the final code block'). A block
    whose closing fence is missing runs from its opening fence; a reply without fences runs as it is."""
    blocks = re.findall(r"```[ \t]*(\w*)[^\n]*\n(.*?)```", reply or "", re.DOTALL)
    python = [code for lang, code in blocks if lang.lower() in ("python", "py", "python3", "")]
    if python or blocks:
        return (python or [code for _, code in blocks])[-1].strip()
    opened = re.search(r"```[ \t]*\w*[^\n]*\n(.*)", reply or "", re.DOTALL)
    return (opened.group(1) if opened else reply or "").strip()


def _parse_json_object(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    # 1. Try markdown code blocks first
    code_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = list(code_blocks)

    # 2. Add greedy block match
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match and match.group(0) not in candidates:
        candidates.append(match.group(0))

    for cand in candidates:
        try:
            return json.loads(cand)
        except ValueError:
            pass
        # Clean trailing commas (e.g. {"a": 1, })
        cleaned = re.sub(r",\s*([}\]])", r"\1", cand)
        try:
            return json.loads(cleaned)
        except ValueError:
            pass
    return {}


_PROMPT_DISPLACEMENT_UNIT = re.compile(r"roof displacement[^.]*?\((mm|cm|m|in|ft)\)", re.IGNORECASE)


def answer_units(case: BenchmarkCase) -> Dict[str, str]:
    """Length units the single-shot JSON schema asks for where they differ from the spec's: the prompt's unit of the
    roof displacement (A06 and B07 ask for mm). The schema once gave the spec's unit (m) there, and answers followed
    either the prompt or the schema (deepseek code_gen A06 printed 47.39, in mm)."""
    asked = _PROMPT_DISPLACEMENT_UNIT.search(case.prompt)
    if asked and asked.group(1) != _length_unit(case) and "peak_roof_displacement" in case.evaluation.required_metrics:
        return {"peak_roof_displacement": asked.group(1)}
    return {}


def single_shot_claims(case: BenchmarkCase, parsed: Dict[str, Any], units: Dict[str, str]) -> Dict[str, Any]:
    """The metric values of a JSON answer, converted to spec units from the ``units`` its schema asked for (a record
    without them was asked in spec units)."""
    claims = {m: parsed[m] for m in METRICS if m in parsed}
    for metric, unit in units.items():
        if isinstance(claims.get(metric), (int, float)):
            claims[metric] = claims[metric] * conversion_factor(f"kN, {unit}", case.spec.units, "length")
    return claims


def _sections_from_answer(parsed: Dict[str, Any]) -> Optional[SectionPair]:
    try:
        return SectionPair(column=(float(parsed["col_b"]), float(parsed["col_h"])),
                           beam=(float(parsed["beam_b"]), float(parsed["beam_h"])))
    except (KeyError, TypeError, ValueError):
        return None


def run_single_shot(case: BenchmarkCase, oracle: OracleVerifier, *, mode: str, model: str, api_base: str,
                    api_key: str, temperature: float, seed: Optional[int], timeout: float,
                    max_tokens: Optional[int] = None, reasoning_effort: Optional[str] = None) -> Dict[str, Any]:
    t0 = time.perf_counter()
    errors: List[str] = []
    reply = ""
    parsed: Dict[str, Any] = {}
    executed = None
    stdout = ""
    call: Dict[str, Any] = {}
    provider_error = False
    try:
        try:
            reply, call = chat_completion(api_base, api_key, model, single_shot_messages(case, mode), temperature,
                                            seed, timeout, max_tokens, reasoning_effort)
        except Exception:
            provider_error = True
            raise
        if mode == "direct_llm":
            parsed = _parse_json_object(reply)
        else:
            script = script_from_reply(reply)
            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tf:
                tf.write(script)
            workspace = make_workspace(case)
            try:
                run = subprocess.run([sys.executable, tf.name], capture_output=True, text=True, timeout=120,
                                     cwd=str(workspace))
                executed = run.returncode == 0
                stdout = run.stdout
                if executed:
                    parsed = _parse_json_object(run.stdout)
                else:
                    errors.append(f"Script error: {run.stderr[-500:]}")
            finally:
                os.unlink(tf.name)
                shutil.rmtree(workspace, ignore_errors=True)
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")

    sections = _sections_from_answer(parsed)
    claims = single_shot_claims(case, parsed, answer_units(case))
    res = oracle.evaluate(case.id, sections, claims)
    success = bool(parsed) and (executed is not False) and res.solution.error is None
    answer = reply if mode == "direct_llm" else stdout  # code_gen: the user receives the script's output, not its source
    record = build_record(
        case, config=mode, model=model, temperature=temperature, seed=seed, oracle=res, success=success,
        elapsed=time.perf_counter() - t0, final_message=answer, final_stage="SINGLE_SHOT",
        error_messages=errors + ([f"Oracle: {res.solution.error}"] if res.solution.error else []),
    )
    record["code_executed"] = executed
    record["answer_units"] = answer_units(case)  # units the JSON schema asked for, where not the spec's
    if executed is False:  # a crashed script gave no answer, whatever its comments assume or ask
        record["success"] = False
    record["final_message"] = reply  # the answer (direct_llm) or the script (code_gen), for audits
    if mode == "code_gen":
        record["script_output"] = stdout[-4000:]
    record["llm_calls"] = [call] if call else []
    record["max_output_tokens"] = max_tokens
    record["reasoning_effort"] = reasoning_effort
    record["final_response_capped"] = runaway_response(call, max_tokens)
    record["final_response_truncated"] = call.get("finish_reason") == "length" and not record["final_response_capped"]
    record["provider_error"] = provider_error
    record["failure_mode"] = classify_failure(record)
    print(f"--> [{mode}] DCR={record['final_dcr']} compliant={record['code_compliant']} "
          f"CHR={record['calculation_hallucination_rate_pct']}% ({time.perf_counter() - t0:.1f}s)")
    return record


# =============================================================================
# Heuristic baseline
# =============================================================================
def _snap(value: float, step: float) -> float:
    return round(math.ceil(value / step - 1e-9) * step, 4)


def heuristic_sections(case: BenchmarkCase) -> SectionPair:
    """Rule of thumb: square columns H_total/20, beams b = 0.30 m (12 in on the US grid) and h = max(span/12, l/18.5)
    (all >= the stated minimums, on the design grid)."""
    g, geo = case.design_grid, case.spec.geometry
    to_m = conversion_factor(case.spec.units, "kN, m", "length")
    col = max(g.column_min, _snap(sum(geo.story_heights) / 20.0, g.step))
    beam_b = max(g.beam_width_min, _snap(0.30 / to_m, g.step))
    beam_h = max(beam_b, _snap(max(geo.bay_widths_x + (geo.bay_widths_y or [])) / 12.0, g.step),
                 _snap(case.min_beam_depth, g.step))
    return _clamp(case, SectionPair(column=(col, col), beam=(beam_b, beam_h)))


def _clamp(case: BenchmarkCase, s: SectionPair) -> SectionPair:
    lim = case.spec.section_limits
    if lim is None:
        return s
    col = min(s.column[0], lim.max_width, lim.max_depth)
    bb = min(s.beam[0], lim.max_width)
    bh = max(bb, min(s.beam[1], lim.max_depth))
    return SectionPair(column=(col, col), beam=(bb, bh))


def run_heuristic(case: BenchmarkCase, oracle: OracleVerifier) -> Dict[str, Any]:
    t0 = time.perf_counter()
    if case.deliverables.design != "design":
        res = oracle.evaluate(case.id, None)
        record = build_record(case, config="heuristic", model="deterministic_heuristic", temperature=0.0, seed=None,
                              oracle=res, success=None, elapsed=time.perf_counter() - t0, final_stage="NOT_APPLICABLE")
        return record
    g = case.design_grid
    sections = heuristic_sections(case)
    history: List[float] = []
    for _ in range(6):
        sol = oracle.solve(case.id, sections)
        if sol.governing_dcr is None:
            break
        history.append(sol.governing_dcr)
        if sol.governing_dcr <= case.deliverables.max_dcr:
            break
        k = math.sqrt(max(sol.governing_dcr, 1.05))
        col = min(_snap(sections.column[0] * k, g.step), g.column_max)
        bb = min(_snap(sections.beam[0] * k, g.step), g.beam_width_max)
        bh = max(bb, min(_snap(sections.beam[1] * k, g.step), g.beam_depth_max))
        grown = _clamp(case, SectionPair(column=(col, col), beam=(bb, bh)))
        if grown == sections:
            break
        sections = grown
    res = oracle.evaluate(case.id, sections)
    record = build_record(case, config="heuristic", model="deterministic_heuristic", temperature=0.0, seed=None,
                          oracle=res, success=res.solution.error is None, elapsed=time.perf_counter() - t0,
                          dcr_history=history, final_stage="HEURISTIC_RULE_BASED", turns_used=len(history))
    record["failure_mode"] = None if res.code_compliant else "dcr_non_convergence"
    print(f"--> [heuristic] sections={sections.model_dump()} DCR={record['final_dcr']} compliant={record['code_compliant']}")
    return record


# =============================================================================
# Tool-using agents
# =============================================================================
def agent_sections(case: BenchmarkCase, project: Any) -> Tuple[Optional[SectionPair], Optional[bool]]:
    """Most common column and beam sections of the agent's model, in spec units, and whether each is uniform."""
    model = getattr(project, "model", None)
    if model is None or not model.elements:
        return None, None
    model_units = getattr(project.metadata, "units", None) or "kN, m"
    scale = conversion_factor(model_units, case.spec.units, "length")
    nodes = {n.id: n for n in model.nodes}
    sections = {s.id: s for s in model.sections}
    is_3d = any(abs(getattr(n, "z", 0.0)) > 1e-6 for n in model.nodes)
    counts: Dict[str, Dict[str, int]] = {"column": {}, "beam": {}}
    for e in model.elements:
        a, b = nodes.get(e.start_node), nodes.get(e.end_node)
        if a is None or b is None:
            continue
        vertical = (abs(a.x - b.x) < 1e-6 and abs(a.y - b.y) < 1e-6) if is_3d else abs(a.x - b.x) < 1e-6
        kind = "column" if vertical else "beam"
        counts[kind][e.section_id] = counts[kind].get(e.section_id, 0) + 1
    dims = {}
    for kind, by_section in counts.items():
        if not by_section:
            return None, None
        sec = sections.get(max(by_section, key=by_section.get))
        b, h = getattr(sec, "b", None), getattr(sec, "h", None)
        if b is None or h is None:
            return None, None
        dims[kind] = (round(b * scale, 4), round(h * scale, 4))
    uniform = all(len(v) == 1 for v in counts.values())
    return SectionPair(column=dims["column"], beam=dims["beam"]), uniform


def verify_deliverables(case: BenchmarkCase, root: Path = REPO_ROOT) -> Dict[str, bool]:
    """Each requested file must exist at its path under ``root`` (the run's workspace) and be readable (DXF
    entities, or a CAE model matching the fixture)."""
    found: Dict[str, bool] = {}
    for f in case.deliverables.files:
        path = root / f.path
        ok = False
        if path.exists() and path.stat().st_size > 0:
            try:
                if f.kind == "dxf":
                    import ezdxf

                    ok = len(ezdxf.readfile(str(path)).modelspace()) > 0
                else:
                    from struct_link import read_project

                    exported = read_project(path).model
                    fixture = read_project(REPO_ROOT / case.spec.cae.file).model
                    ok = (len(exported.nodes), len(exported.elements), len(exported.supports)) == (
                        len(fixture.nodes), len(fixture.elements), len(fixture.supports))
            except Exception:
                ok = False
        found[f.path] = ok
    return found


def reference_load_totals(oracle: OracleVerifier, case: BenchmarkCase,
                          sections: Optional[SectionPair]) -> Optional[Dict[str, float]]:
    """Dead, live, and partition resultants of the oracle's model with the same sections, and the horizontal force
    of each ELF seismic case (spec units)."""
    if case.spec.cae is not None or case.spec.loads is None:
        return None
    used = oracle.sections_for(case, sections)
    if used is None:
        return None
    project = oracle.build_project(case, used)
    return {**gravity_load_totals(project, case.spec.units), **lateral_load_totals(project, case.spec.units)}


def _compact(value: Any, depth: int = 0) -> Any:
    """Short JSON-safe copy of tool arguments or results for the run log (long values are truncated)."""
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    if isinstance(value, str):
        return value if len(value) <= 200 else value[:200] + "..."
    if depth >= 4:
        return f"<{type(value).__name__}>"
    if isinstance(value, dict):
        return {str(k): _compact(v, depth + 1) for k, v in list(value.items())[:40]}
    if isinstance(value, (list, tuple)):
        items = [_compact(v, depth + 1) for v in list(value)[:20]]
        return items + ([f"... {len(value) - 20} more"] if len(value) > 20 else [])
    return f"<{type(value).__name__}>"


def _log_llm_calls(runner: AgentRunner) -> List[Dict[str, Any]]:
    """Token usage and finish reason of each LLM response of the run (the run log keeps them)."""
    calls: List[Dict[str, Any]] = []
    generate = runner.provider.generate

    def logged(*args: Any, **kwargs: Any) -> Any:
        resp = generate(*args, **kwargs)
        usage = resp.usage or {}
        calls.append({"prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
                      "finish_reason": resp.finish_reason, "tool_calls": len(resp.tool_calls),
                      "tools_offered": bool(kwargs.get("tools"))})
        if resp.finish_reason == "length":
            calls[-1]["reasoning_tail"] = reasoning_tail(resp.reasoning)
        return resp

    runner.provider.generate = logged
    return calls


# A response cut off after this many generated tokens ran away, whatever cut it: qwen3.5:9b's 64k Ollama window
# ends its thinking before the output cap. A shorter cut is the context window's (a 16k window cut qwen's answers).
RUNAWAY_TOKENS = 32000


def runaway_response(call: Dict[str, Any], max_tokens: Optional[int]) -> bool:
    """Whether a response was cut off (finish_reason 'length') while generating without end: at the output-token
    cap (``--max-output-tokens``), or at the context window after ``RUNAWAY_TOKENS`` or more."""
    if call.get("finish_reason") != "length":
        return False
    limit = min(0.95 * max_tokens if max_tokens else math.inf, RUNAWAY_TOKENS)
    return (call.get("completion_tokens") or 0) >= limit


def context_limits(llm_calls: List[Dict[str, Any]], max_tokens: Optional[int] = None) -> Dict[str, Any]:
    """Signs that the model's context window, not the model, ended or degraded the run.

    A response cut off at the token limit (finish_reason 'length') without a tool call ends the run with
    whatever text it holds (often none). A runaway (``runaway_response``: at the output-token cap, or after
    ``RUNAWAY_TOKENS`` or more) is the model's failure, generating (mostly thinking) without end; a shorter
    cut is the context window's. The conversation only grows, so a prompt shorter than the previous
    one was truncated by the server (Ollama keeps the last tokens of an over-long prompt, dropping the system
    prompt, the tools and the task). Only prompts with the same tool offer are compared: the tool-free report
    turn after an exhausted turn budget omits the tool schemas (about 9k tokens) and is legitimately shorter.
    """
    calls = [c for c in llm_calls if c.get("prompt_tokens")]
    prompts = [c["prompt_tokens"] for c in calls]
    last = llm_calls[-1] if llm_calls else {}
    ended = last.get("finish_reason") == "length" and not last.get("tool_calls")
    return {
        "max_prompt_tokens": max(prompts, default=None),
        "max_completion_tokens": max((c.get("completion_tokens") or 0 for c in llm_calls), default=None),
        "truncated_responses": sum(1 for c in llm_calls if c.get("finish_reason") == "length"),
        "output_cap_hits": sum(1 for c in llm_calls if runaway_response(c, max_tokens)),
        "prompt_truncations": sum(1 for a, b in zip(calls, calls[1:])
                                  if b["prompt_tokens"] < a["prompt_tokens"]
                                  and b.get("tools_offered", True) == a.get("tools_offered", True)),
        "final_response_truncated": ended and not runaway_response(last, max_tokens),
        "final_response_capped": ended and runaway_response(last, max_tokens),
    }


SETUP_FAILURES = ("provider_error", "context_limit")  # failure modes caused by the setup, not the model


def llm_server_reachable(api_base: str) -> bool:
    """Whether the OpenAI-compatible server answers at all (any HTTP status counts as an answer)."""
    try:
        urllib.request.urlopen(f"{api_base.rstrip('/')}/models", timeout=30).close()
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False
    return True


QUOTA_ERROR = re.compile(r"status 429|usage limit|rate limit|quota", re.IGNORECASE)
MAX_CONSECUTIVE_PROVIDER_ERRORS = 3


def provider_stop_reason(recent: List[Dict[str, Any]], api_base: str) -> Optional[str]:
    """Why the campaign cannot go on: every further run would fail at once, measuring no model behavior.

    An Ollama crash ended C03 and refused C06; the Ollama cloud free-usage limit (HTTP 429) failed nemotron's
    last 19 ablated runs within seconds each. ``recent`` are the campaign's runs so far, latest last.
    """
    if not recent[-1].get("provider_error"):
        return None
    if any(QUOTA_ERROR.search(e) for e in recent[-1].get("error_messages", []) if e.startswith("LLM Provider error")):
        return "the LLM provider reports a usage or rate limit"
    if not llm_server_reachable(api_base):
        return f"the LLM server at {api_base} is not reachable"
    tail = recent[-MAX_CONSECUTIVE_PROVIDER_ERRORS:]
    if len(tail) == MAX_CONSECUTIVE_PROVIDER_ERRORS and all(r.get("provider_error") for r in tail):
        return f"the last {MAX_CONSECUTIVE_PROVIDER_ERRORS} runs failed with LLM provider errors"
    return None


# The agent's first request (system prompt and tool schemas) is about 12k tokens; a run adds the tool results of up
# to 30 turns, and a reasoning model's thinking must fit in the same window
MIN_CONTEXT_TOKENS = 65536


def check_ollama_context(api_base: str, model: str, min_tokens: int) -> None:
    """Refuse to start when the local Ollama server would run the model with a smaller context window.

    Ollama's OpenAI-compatible endpoint takes the context length from the server (OLLAMA_CONTEXT_LENGTH or a
    VRAM-based default) and cuts over-long prompts and responses silently; a 16k window ended 103 of 135
    qwen3.5:9b runs with an empty message.
    """
    if not min_tokens:
        return
    root = api_base[: -len("/v1")] if api_base.endswith("/v1") else api_base
    try:
        chat_completion(api_base, "ollama", model, [{"role": "user", "content": "OK"}], 0.0, None, 600.0)  # loads it
        with urllib.request.urlopen(f"{root}/api/ps", timeout=30) as resp:
            loaded = json.loads(resp.read().decode("utf-8")).get("models", [])
    except Exception as exc:
        print(f"Context check skipped ({type(exc).__name__}: {exc})")
        return
    ctx = next((m.get("context_length") for m in loaded if m.get("name") == model or m.get("model") == model), None)
    if ctx is None:  # cloud models are not loaded locally
        print(f"Context check skipped: {model} is not loaded on the local server.")
        return
    print(f"Ollama context window for {model}: {ctx} tokens")
    if ctx < min_tokens:
        sys.exit(f"The Ollama server runs {model} with a {ctx}-token context; agent runs need at least {min_tokens} "
                 f"(prompts and responses beyond it are cut silently). Restart Ollama with "
                 f"OLLAMA_CONTEXT_LENGTH={min_tokens} (or larger), or pass --min-context to override.")


FILE_OUTPUT_TOOLS = ("generate_drawings", "export_to_sap2000", "export_to_etabs")  # each writes its output_path


FIXTURES_DIR = BENCHMARKS_DIR / "fixtures"


def make_workspace(case: BenchmarkCase) -> Path:
    """A fresh working directory for one run, in which the prompt's repository-relative paths resolve: a copy of
    the input fixtures and the deliverables' folders. Concurrent campaigns then neither overwrite nor score each
    other's deliverables, and an agent that exports over an input fixture spoils only its own copy."""
    root = Path(tempfile.mkdtemp(prefix=f"bench_{case.id[:3]}_")).resolve()
    shutil.copytree(FIXTURES_DIR, root / FIXTURES_DIR.relative_to(REPO_ROOT))
    for f in case.deliverables.files:
        (root / f.path).parent.mkdir(parents=True, exist_ok=True)
    return root


def keep_outputs(case: BenchmarkCase, written: List[str], workspace: Path, dest: Path,
                 preexisting: Optional[set] = None) -> List[str]:
    """Move a run's files out of its workspace into ``dest``: the case's deliverables, and the files the agent
    wrote besides them (drawings or exports it was not asked for, e.g. qwen's 'structural_design.dxf'). A path
    that existed before the agent wrote it (``preexisting``: an input fixture it exported over, or a file outside
    the workspace) stays where it is. Returns the moved undeclared paths as written."""
    def move(path: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(dest / path.name))

    declared = {(workspace / f.path).resolve() for f in case.deliverables.files}
    for path in declared:
        if path.is_file():
            move(path)
    moved = []
    for p in dict.fromkeys(written):
        path = (Path(p) if Path(p).is_absolute() else workspace / p).resolve()
        if path in declared or path in (preexisting or set()) or not path.is_file():
            continue
        move(path)
        moved.append(p)
    return moved


def run_agent(case: BenchmarkCase, oracle: OracleVerifier, *, config: str, model: str, provider: str, api_base: str,
              api_key: str, max_turns: int, timeout: float, temperature: float, seed: Optional[int],
              artifact_dir: Optional[Path] = None, max_tokens: Optional[int] = None,
              reasoning_effort: Optional[str] = None) -> Dict[str, Any]:
    custom = ""
    if config == "ablated":
        custom = ("IMPORTANT RESTRICTION FOR THIS RUN: perform a single linear pass through the workflow. Do not "
                  "enter an optimization or reflection loop and do not resize members after running design checks.")
    runner = AgentRunner(provider=provider, model=model, base_url=api_base, api_key=api_key or "ollama",
                         custom_instructions=custom, max_turns=max_turns, temperature=temperature, seed=seed,
                         timeout=timeout, max_tokens=max_tokens, reasoning_effort=reasoning_effort,
                         **RUNNER_SETTINGS[config])
    llm_calls = _log_llm_calls(runner)

    t0 = time.perf_counter()
    tools_called: List[str] = []
    succeeded: set = set()
    tool_args: List[Tuple[str, Dict[str, Any]]] = []  # successful calls, full arguments
    pending_args: List[Tuple[str, Dict[str, Any]]] = []
    tool_failures: List[Dict[str, Any]] = []
    tool_log: List[Dict[str, Any]] = []
    written: List[str] = []  # files saved by FILE_OUTPUT_TOOLS
    preexisting: set = set()  # their paths that existed before the call (overwritten repository files)
    stages: List[str] = []
    history: List[float] = []
    errors: List[str] = []
    final_message = ""
    turn_limit_reached = False
    checks = DesignCheckTracker()  # did the last design check use an analysis of the delivered model?
    attachments = [str(REPO_ROOT / case.spec.plan_image)] if case.spec.plan_image else None
    cwd = os.getcwd()
    workspace = make_workspace(case)
    os.chdir(workspace)  # prompt file paths are repository-relative
    try:
        for event in runner.run_stream(case.prompt, attachments=attachments):
            if isinstance(event, ToolCallEvent):
                tools_called.append(event.tool_name)
                pending_args.append((event.tool_name, dict(event.arguments or {})))
                tool_log.append({"tool": event.tool_name, "args": _compact(dict(event.arguments or {}))})
                target = (event.arguments or {}).get("output_path") if event.tool_name in FILE_OUTPUT_TOOLS else None
                if target and Path(str(target)).resolve().is_file():
                    preexisting.add(Path(str(target)).resolve())
                print(f"  -> {event.tool_name}")
            elif isinstance(event, ToolResultEvent):
                entry = next((t for t in reversed(tool_log) if t["tool"] == event.tool_name and "ok" not in t), None)
                if entry is not None:
                    entry["ok"] = event.ok
                    entry["result"] = event.error_message if not event.ok else _compact(
                        {k: v for k, v in (event.data or {}).items() if k != "project"})
                call = next((c for c in reversed(pending_args) if c[0] == event.tool_name), None)
                if call is not None:
                    pending_args.remove(call)
                checks.record(event.tool_name, runner.project, event.ok)
                if not event.ok:
                    tool_failures.append({"tool": event.tool_name, "error": event.error_message})
                    continue
                if call is not None:
                    tool_args.append(call)
                succeeded.add(event.tool_name)
                if event.tool_name in FILE_OUTPUT_TOOLS and (event.data or {}).get("output_path"):
                    written.append(str(Path(str(event.data["output_path"])).resolve()))
                if event.tool_name == "run_design" and event.data.get("governing_dcr") is not None:
                    history.append(float(event.data["governing_dcr"]))
            elif isinstance(event, StateUpdateEvent) and event.stage not in stages:
                stages.append(event.stage)
            elif isinstance(event, ErrorEvent):
                errors.append(event.message)
            elif isinstance(event, CompleteEvent):
                final_message = event.final_message
                turn_limit_reached = event.turn_limit_reached
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        os.chdir(cwd)
    elapsed = time.perf_counter() - t0

    project = runner.project
    n_nodes = len(project.model.nodes) if project is not None and project.model is not None else 0
    n_elems = len(project.model.elements) if project is not None and project.model is not None else 0

    mandatory =[t for t in case.evaluation.expected_tools if t not in NON_MANDATORY_EXPECTED_TOOLS]
    missing = [t for t in mandatory if t not in succeeded]
    if n_nodes and succeeded & MODEL_CREATION_TOOLS:
        missing = [t for t in missing if t not in MODEL_CREATION_TOOLS]
    deliverables = verify_deliverables(case, workspace) if case.deliverables.files else None
    success = bool(n_nodes and n_elems and not missing and (deliverables is None or all(deliverables.values())))

    # Design and check cases are verified with the agent's own final sections; analysis cases use the prescribed ones
    sections, uniform = agent_sections(case, project) if case.deliverables.design != "none" else (None, None)
    claims = parse_numerical_claims_from_text(final_message, case.spec.units)
    res = oracle.evaluate(case.id, sections, claims)
    psfr = (evaluate_prompt_to_schema_fidelity(project, case, tool_args, reference_load_totals(oracle, case, sections))
            if n_nodes else (False, {"error": "no model"}))

    record = build_record(
        case, config=config, model=model, temperature=temperature, seed=seed, oracle=res, success=success,
        elapsed=elapsed, final_message=final_message, tools_called=tools_called, tool_failures=tool_failures,
        missing_expected_tools=missing, dcr_history=history, final_stage=runner.state.stage.value,
        stages_visited=stages, turns_used=len(runner.messages) // 2, nodes_count=n_nodes, elements_count=n_elems,
        psfr=psfr, deliverables=deliverables, uniform_sections=uniform,
        error_messages=errors + ([f"Oracle: {res.solution.error}"] if res.solution.error else []),
        final_design_verified=checks.design_current(project) if case.deliverables.design != "none" else None,
    )
    record["agent_concrete_volume"] = calculate_concrete_volume(project) if project is not None else None
    record["turn_limit_reached"] = turn_limit_reached
    record["max_output_tokens"] = max_tokens
    record["reasoning_effort"] = reasoning_effort
    record.update(context_limits(llm_calls, max_tokens))
    record["provider_error"] = any(e.startswith("LLM Provider error") for e in errors)
    record["llm_calls"] = llm_calls
    record["repeated_calls"] = runner.repeated_calls
    record["rejected_tool_calls"] = runner.rejected_tool_calls
    record["tool_log"] = tool_log
    record["final_message"] = final_message
    declared = {(workspace / f.path).resolve() for f in case.deliverables.files}
    record["overwritten_files"] = sorted(str(p.relative_to(workspace)) if p.is_relative_to(workspace) else str(p)
                                         for p in preexisting if p not in declared)
    record["undeclared_outputs"] = []
    if artifact_dir is not None:  # otherwise the workspace and its files stay
        dest = artifact_dir / f"{case.id}_seed{seed}"
        record["undeclared_outputs"] = [str(Path(p).relative_to(workspace)) if Path(p).is_relative_to(workspace)
                                        else p for p in keep_outputs(case, written, workspace, dest, preexisting)]
        record["output_dir"] = str(dest) if dest.is_dir() else None
        shutil.rmtree(workspace, ignore_errors=True)
    record["failure_mode"] = classify_failure(record)
    print(f"--> [{config}] success={success} DCR={record['final_dcr']} compliant={record['code_compliant']} "
          f"PSFR={psfr[0]} CHR={record['calculation_hallucination_rate_pct']}% ({elapsed:.1f}s)")
    return record


# =============================================================================
# Aggregation
# =============================================================================
def _pct(num: int, den: int) -> Optional[float]:
    return round(100.0 * num / den, 1) if den else None


def summarize(results: List[Dict[str, Any]], *, model: str, config: str, temperature: float, seeds: int,
              not_applicable_cases: Optional[List[str]] = None) -> Dict[str, Any]:
    agentic = config in ("full_agent", "ablated")
    # Runs ended by the setup (LLM server, context window) measure no model behavior: the rates leave them out
    # (they are counted, and --resume re-runs them)
    all_results = results
    results = [r for r in all_results if r.get("failure_mode") not in SETUP_FAILURES]
    scored = [r for r in results if r["success"] is not None]
    design = [r for r in results if r["design_required"]]
    claims = sum(r["claims_made_count"] for r in results)
    reflection = [r for r in results if r.get("reference_initial_dcr") is not None]
    converged = [r for r in reflection if r["iterations_to_converge"] is not None]
    probes = [r for r in results if r["behavior_passed"] is not None]
    etas = [r["material_economy_ratio"] for r in results if r["material_economy_ratio"] is not None]
    psfr = [r for r in results if r["prompt_to_schema_fidelity_passed"] is not None] if agentic else []
    failure_modes: Dict[str, int] = {}
    for r in all_results:
        if r["failure_mode"]:
            failure_modes[r["failure_mode"]] = failure_modes.get(r["failure_mode"], 0) + 1

    per_case: Dict[str, Dict[str, Any]] = {}
    for cid in dict.fromkeys(r["case_id"] for r in results):
        runs = [r for r in results if r["case_id"] == cid]
        ccr_vals = [1.0 if r["code_compliant"] else 0.0 for r in runs if r["design_required"]]
        per_case[cid] = {
            "runs": len(runs),
            "tcr_pct": _pct(sum(1 for r in runs if r["success"]), sum(1 for r in runs if r["success"] is not None)),
            "ccr_mean": round(mean(ccr_vals), 3) if ccr_vals else None,
            "ccr_std": round(pstdev(ccr_vals), 3) if len(ccr_vals) > 1 else None,
            "chr_mean": round(mean(r["calculation_hallucination_rate_pct"] for r in runs), 1),
            "runtime_mean": round(mean(r["wall_clock_time_sec"] for r in runs), 2),
        }

    return {
        "model": model,
        "configuration": config,
        "timestamp": datetime.now().isoformat(),
        "temperature": temperature,
        "seeds": seeds,
        "total_runs": len(all_results),
        "setup_failed_runs": len(all_results) - len(results),
        "unique_cases": len(per_case),
        "not_applicable_cases": list(not_applicable_cases or []),
        "task_completion_rate_pct": _pct(sum(1 for r in scored if r["success"]), len(scored)),
        "design_runs": len(design),
        "compliant_runs": sum(1 for r in design if r["code_compliant"]),
        "code_compliance_rate_pct": _pct(sum(1 for r in design if r["code_compliant"]), len(design)),
        "calculation_hallucination_rate_pct": _pct(sum(r["hallucinated_claims_count"] for r in results), claims) or 0.0,
        "claim_completeness_rate_pct": (
            None if config == "heuristic" else
            _pct(claims, sum(len(r["expected_oracle_metrics"]) for r in results))
        ),
        "prompt_to_schema_fidelity_rate_pct": _pct(sum(1 for r in psfr if r["prompt_to_schema_fidelity_passed"]), len(psfr)),
        "probe_behavior_rate_pct": _pct(sum(1 for r in probes if r["behavior_passed"]), len(probes)),
        "reflection_runs": len(reflection),
        "converged_reflection_runs": len(converged),
        "avg_convergence_iterations": round(mean(r["iterations_to_converge"] for r in converged), 2) if converged else None,
        "avg_material_economy_ratio": round(mean(etas), 3) if etas else None,
        "avg_runtime_sec": round(mean(r["wall_clock_time_sec"] for r in results), 2) if results else None,
        "failure_modes_summary": failure_modes,
        "context_limited_runs": sum(1 for r in all_results if r.get("failure_mode") == "context_limit"),
        "provider_error_runs": sum(1 for r in all_results if r.get("failure_mode") == "provider_error"),
        "runaway_generation_runs": sum(1 for r in all_results if r.get("failure_mode") == "runaway_generation"),
        "per_case": per_case,
        "case_results": all_results,
    }


def select_cases(cases: List[BenchmarkCase], spec: str) -> List[BenchmarkCase]:
    if spec.lower() == "all":
        return cases
    groups = {c.group.lower() for c in cases}
    if spec.lower() in groups:
        return [c for c in cases if c.group.lower() == spec.lower()]
    wanted = [s.strip().lower() for s in spec.split(",") if s.strip()]
    return [c for c in cases if any(c.id.lower() == w or c.id.lower().startswith(w) for w in wanted)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Structural engineering agent benchmark harness")
    parser.add_argument("--model", default="gemini-3.8-flash")
    parser.add_argument("--provider", default="auto", help="ollama, native, gemini, ...")
    parser.add_argument("--api-base", default="", help="OpenAI-compatible endpoint (e.g. http://localhost:11434/v1)")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--cases", default="all", help="'all', a group (A_2D, B_3D, C_Multimodal, D_Robustness), or IDs/prefixes")
    parser.add_argument("--config", default="full_agent", choices=["full_agent", "ablated", "direct_llm", "code_gen", "heuristic"])
    parser.add_argument("--max-turns", type=int, default=30,
                        help="LLM turns per agent run (same budget for full_agent and ablated)")
    parser.add_argument("--timeout", type=float, default=1800.0,
                        help="Seconds per LLM request: a backstop for a stalled server, longer than the output cap "
                             "takes to generate (128k tokens: ~20 min at 110 tok/s). qwen3.5:9b on a local GPU "
                             "(~15 tok/s, its 64k window ending a runaway) needs --timeout 5400")
    parser.add_argument("--max-output-tokens", type=int, default=131072,
                        help="Most tokens (thinking included) one LLM response may generate; a response that "
                             "reaches it ends the run as the model's failure ('runaway_generation'). 0: no cap")
    parser.add_argument("--reasoning-effort", default="high",
                        help="reasoning_effort sent with every request ('low', 'medium', 'high'; 'none' sends none). "
                             "gemma4 thinks only when it is set; qwen3.5 and minimax think regardless")
    parser.add_argument("--temperature", type=float, default=None, help="Default: 0.2 when seeds > 1, else 0.0")
    parser.add_argument("--seeds", type=int, default=None, help="Default: 5 for agents, 1 otherwise")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--update-file", default="",
                        help="Existing results JSON to update in place (runs with the same case and seed are replaced)")
    parser.add_argument("--no-vision", action="store_true",
                        help="The model takes no image input: the drawing cases are not run and are recorded as "
                             "not applicable")
    parser.add_argument("--resume", action="store_true",
                        help="With --update-file: run only the case/seed pairs the file lacks or that failed because "
                             "of the setup (provider_error, context_limit)")
    parser.add_argument("--min-context", type=int, default=MIN_CONTEXT_TOKENS,
                        help="Smallest Ollama context window (tokens) an agent run may start with; 0 skips the check")
    args = parser.parse_args()
    if args.resume and not args.update_file:
        sys.exit("--resume continues an existing results file: pass it with --update-file.")
    if args.no_vision and args.config == "heuristic":
        sys.exit("--no-vision applies to LLM configurations; the heuristic reads no drawings.")

    for env_file in (REPO_ROOT / "struct_agent" / ".env", REPO_ROOT / ".env"):
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    cases = select_cases(load_cases(), args.cases)
    # A drawing case without image input is a different task, not a failure: it is excluded from every rate
    not_applicable = [c.id for c in cases if args.no_vision and c.spec.plan_image]
    cases = [c for c in cases if c.id not in not_applicable]
    if not_applicable:
        print(f"Not applicable without image input: {', '.join(not_applicable)}")
    if not cases:
        sys.exit(f"No benchmark cases to run: {args.cases}")
    output_dir = Path(args.output_dir) if args.output_dir else BENCHMARKS_DIR / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    api_base, provider = args.api_base, args.provider
    if not api_base:
        if "gemini" in args.model.lower() or provider == "gemini":
            api_base, provider = "https://generativelanguage.googleapis.com/v1beta/openai", "gemini"
        else:
            api_base = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
            api_base = api_base if api_base.endswith("/v1") else f"{api_base}/v1"
            provider = "native" if provider == "auto" else provider
    api_key = args.api_key or os.environ.get("GEMINI_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "ollama")

    agentic = args.config in ("full_agent", "ablated")
    effort = None if args.reasoning_effort.lower() in ("none", "") else args.reasoning_effort
    seeds = 1 if args.config == "heuristic" else (args.seeds or (5 if agentic else 1))
    temperature = args.temperature if args.temperature is not None else (0.2 if seeds > 1 else 0.0)
    model_name = "deterministic_heuristic" if args.config == "heuristic" else args.model
    print(f"\n{'=' * 80}\n BENCHMARK: {len(cases)} cases | {args.config} | {model_name} | seeds={seeds} | T={temperature}\n{'=' * 80}")

    if args.config != "heuristic" and provider != "gemini" and "11434" in api_base:
        check_ollama_context(api_base, args.model, min_tokens=args.min_context)

    if args.update_file:
        out_file = Path(args.update_file)
        previous = json.loads(out_file.read_text(encoding="utf-8"))
        seeds_total = max(seeds, previous.get("seeds", 1))
        not_applicable = sorted(set(not_applicable) | set(previous.get("not_applicable_cases", [])))
    else:
        previous, seeds_total = None, seeds
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = output_dir / f"results_{sanitize_filename(model_name)}_{args.config}_{stamp}.json"

    def write(results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Write the results so far (after every run: an interrupted campaign keeps its completed runs)."""
        if previous is not None:
            fresh = {(r["case_id"], r["seed_index"]) for r in results}
            results = [r for r in previous["case_results"] if (r["case_id"], r["seed_index"]) not in fresh] + results
            results = [r for r in results if r["case_id"] not in not_applicable]
        summary = summarize(results, model=model_name, config=args.config, temperature=temperature,
                            seeds=seeds_total, not_applicable_cases=not_applicable)
        out_file.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        return summary

    # --resume: keep the runs the file already holds, except setup failures (server errors, context limits)
    done = set()
    if args.resume:
        done = {(r["case_id"], r["seed_index"]) for r in previous["case_results"]
                if r.get("failure_mode") not in SETUP_FAILURES}

    oracle = OracleVerifier()
    results: List[Dict[str, Any]] = []
    summary = write(results)
    for case in cases:
        for s_idx in range(seeds):
            if (case.id, s_idx) in done:
                continue
            seed = 42 + s_idx
            print(f"\n[{case.id}] {case.name} (seed {seed})")
            if args.config == "heuristic":
                rec = run_heuristic(case, oracle)
            elif agentic:
                rec = run_agent(case, oracle, config=args.config, model=args.model, provider=provider, api_base=api_base,
                                api_key=api_key, max_turns=args.max_turns, timeout=args.timeout,
                                temperature=temperature, seed=seed, artifact_dir=out_file.with_name(out_file.stem + "_files"),
                                max_tokens=args.max_output_tokens, reasoning_effort=effort)
            else:
                rec = run_single_shot(case, oracle, mode=args.config, model=args.model, api_base=api_base,
                                      api_key=api_key, temperature=temperature, seed=seed, timeout=args.timeout,
                                      max_tokens=args.max_output_tokens, reasoning_effort=effort)
            rec["seed_index"] = s_idx
            results.append(rec)
            summary = write(results)
            stop = provider_stop_reason(results, api_base)
            if stop:
                sys.exit(f"\nStopping: {stop}. Completed runs are in {out_file}. When the provider is available "
                         f"again, continue with the same command plus --update-file \"{out_file}\" --resume.")

    print(f"\n{'=' * 80}\n RUN COMPLETE")
    for key in ("task_completion_rate_pct", "code_compliance_rate_pct", "calculation_hallucination_rate_pct",
                "claim_completeness_rate_pct", "prompt_to_schema_fidelity_rate_pct", "probe_behavior_rate_pct",
                "avg_convergence_iterations", "avg_material_economy_ratio", "avg_runtime_sec", "context_limited_runs",
                "provider_error_runs"):
        print(f"  {key:38s} {summary[key]}")
    setup_failed = summary["context_limited_runs"] + summary["provider_error_runs"]
    if setup_failed:
        print(f"  WARNING: {setup_failed} runs failed because of the setup (failure modes 'context_limit', "
              f"'provider_error'), not the model; re-run them with --update-file \"{out_file}\" --resume.")
    print(f"  results -> {out_file}\n{'=' * 80}")


if __name__ == "__main__":
    main()
