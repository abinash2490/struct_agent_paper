"""
Autonomous Structural Engineering Benchmark Execution Harness
==============================================================

Automates batch testing of Large Language Models against the 24-case structural
benchmark suite across different configurations (full_agent, ablated, direct_llm).
Records quantitative metrics (TCR, CCR, CHR, convergence iterations, material
economy ratio, runtime) to unique timestamped JSON files.

Usage Examples
--------------
# Run all 24 cases with Google Gemini 3.8 Flash (Full Agent vs. Ablated):
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --cases all
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --config ablated --cases all

# Run Direct Zero-Shot LLM baseline (no tools) to measure Calculation Hallucination Rate (CHR):
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --config direct_llm --cases all

# Run Group A (2D cases) with local/cloud Ollama models:
python "research_paper/benchmarks/run_benchmarks.py" --model qwen3.5:9b --cases Group_A_2D
python "research_paper/benchmarks/run_benchmarks.py" --model gpt-oss:120b-cloud --cases Group_A_2D
python "research_paper/benchmarks/run_benchmarks.py" --model nemotron-3-ultra:cloud --cases Group_A_2D
"""

import argparse
import inspect
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def sanitize_filename(name: str) -> str:
    """Sanitize model name for clean file naming."""
    return re.sub(r"[^a-zA-Z0-9_\-\.]", "_", name)


def load_benchmark_cases(cases_path: Path) -> List[Dict[str, Any]]:
    """Load benchmark cases from JSON."""
    with open(cases_path, "r", encoding="utf-8") as f:
        return json.load(f)


def calculate_concrete_volume(project: Any) -> float:
    """Calculate total concrete volume in cubic meters from elements."""
    if not project or not hasattr(project, "model"):
        return 0.0
    nodes_map = {n.id: n for n in getattr(project.model, "nodes", [])}
    sections_map = {s.id: s for s in getattr(project.model, "sections", [])}
    vol = 0.0
    for elem in getattr(project.model, "elements", []):
        sec = sections_map.get(getattr(elem, "section_id", None))
        a = 0.0
        if sec:
            a = getattr(sec, "A", 0.0) or getattr(sec, "area", 0.0)
            if not a:
                b = getattr(sec, "b", 0.0) or getattr(sec, "width", 0.0)
                h = (
                    getattr(sec, "h", 0.0)
                    or getattr(sec, "height", 0.0)
                    or getattr(sec, "depth", 0.0)
                )
                a = b * h
        a = a or 0.15  # standard fallback
        ni = nodes_map.get(getattr(elem, "start_node", None))
        nj = nodes_map.get(getattr(elem, "end_node", None))
        length = 0.0
        if ni and nj:
            xi, yi, zi = getattr(ni, "x", 0.0), getattr(ni, "y", 0.0), getattr(ni, "z", 0.0)
            xj, yj, zj = getattr(nj, "x", 0.0), getattr(nj, "y", 0.0), getattr(nj, "z", 0.0)
            length = ((xj - xi) ** 2 + (yj - yi) ** 2 + (zj - zi) ** 2) ** 0.5
        vol += float(a) * float(length)
    return round(vol, 3)


def run_direct_llm_baseline(
    case: Dict[str, Any],
    model: str,
    api_base: str,
    api_key: str,
    timeout: float = 180.0,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Execute Baseline 1 (Direct Zero-Shot LLM without symbolic tools) to measure
    Calculation Hallucination Rate (CHR) against verified ground-truth mechanics.
    """
    case_id = case["id"]
    prompt = case["prompt"]
    requires_design = bool(case.get("design_required", False))
    base_vol = case.get("baseline_concrete_volume_m3")
    base_dcr = (case.get("baseline_design") or {}).get("governing_dcr")

    system_msg = (
        "You are performing a direct zero-shot structural calculation without external FEA or design tools. "
        "Solve the user's structural engineering problem directly and output ONLY a valid JSON object with keys: "
        '{"concrete_volume_m3": <float>, "governing_dcr": <float>, "code_compliant": <bool>, '
        '"max_moment_kNm": <float>, "max_shear_kN": <float>}. Do not include markdown fences or extra text.'
    )

    t_start = time.perf_counter()
    url = f"{api_base.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
    }
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

    est_vol = parsed.get("concrete_volume_m3")
    est_dcr = parsed.get("governing_dcr")

    # Evaluate Calculation Hallucination Rate (CHR) against ground truth (>5% error = hallucination)
    numerical_claims = 0
    hallucinated_claims = 0

    if base_vol is not None:
        numerical_claims += 1
        try:
            vol_err = abs(float(est_vol) - float(base_vol)) / max(float(base_vol), 1e-6)
            if vol_err > 0.05:
                hallucinated_claims += 1
        except (TypeError, ValueError):
            hallucinated_claims += 1

    if base_dcr is not None:
        numerical_claims += 1
        try:
            dcr_err = abs(float(est_dcr) - float(base_dcr)) / max(float(base_dcr), 1e-6)
            if dcr_err > 0.05:
                hallucinated_claims += 1
        except (TypeError, ValueError):
            hallucinated_claims += 1

    if numerical_claims == 0:
        numerical_claims = 1
        hallucinated_claims = 1

    chr_pct = round((hallucinated_claims / numerical_claims) * 100.0, 1)

    print(
        f"\n--> Result: [DIRECT LLM BASELINE] | Hallucinations: {hallucinated_claims}/{numerical_claims} "
        f"(CHR: {chr_pct}%) | Time: {t_elapsed}s"
    )

    return {
        "case_id": case_id,
        "name": case["name"],
        "group": case.get("group", ""),
        "model": model,
        "configuration": "direct_llm",
        "design_required": requires_design,
        "success": False,  # Direct LLM cannot produce verified FEA states, .s2k/.e2k, or .dxf deliverables
        "code_compliant": False if requires_design else None,
        "final_stage": "UNVERIFIED_TEXT_ONLY",
        "stages_visited": [],
        "wall_clock_time_sec": t_elapsed,
        "turns_used": 1,
        "tools_called": [],
        "missing_expected_tools": case.get("expected_tools", []),
        "tool_failures_count": 0,
        "tool_failures": [],
        "initial_dcr": est_dcr if isinstance(est_dcr, (int, float)) else None,
        "final_dcr": est_dcr if isinstance(est_dcr, (int, float)) else None,
        "dcr_history": [est_dcr] if isinstance(est_dcr, (int, float)) else [],
        "iterations_to_converge": None,
        "nodes_count": 0,
        "elements_count": 0,
        "concrete_volume_m3": float(est_vol) if isinstance(est_vol, (int, float)) else 0.0,
        "baseline_concrete_volume_m3": base_vol,
        "material_economy_ratio": None,
        "numerical_claims_count": numerical_claims,
        "hallucinated_claims_count": hallucinated_claims,
        "calculation_hallucination_rate_pct": chr_pct,
        "error_messages": error_messages,
        "final_message_snippet": (raw_reply[:200] + "...") if len(raw_reply) > 200 else raw_reply,
    }


def run_code_gen_baseline(
    case: Dict[str, Any],
    model: str,
    api_base: str,
    api_key: str,
    timeout: float = 180.0,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Execute Baseline 2 (Code-Generation LLM) to measure syntax/execution failure
    and Calculation Hallucination Rate (CHR). The LLM is prompted to write a standalone
    Python structural analysis script from scratch without struct_agent tools.
    """
    import subprocess
    import tempfile

    case_id = case["id"]
    prompt = case["prompt"]
    requires_design = bool(case.get("design_required", False))
    base_vol = case.get("baseline_concrete_volume_m3")
    base_dcr = (case.get("baseline_design") or {}).get("governing_dcr")

    system_msg = (
        "You are an expert structural engineer and scientific Python programmer. "
        "Write a standalone Python script using standard libraries (numpy, scipy) to solve the user's "
        "structural engineering problem directly. "
        "Your script must compute and print a single valid JSON string to stdout with keys: "
        '{"concrete_volume_m3": <float>, "governing_dcr": <float>, "code_compliant": <bool>, '
        '"max_moment_kNm": <float>, "max_shear_kN": <float>}. '
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
        "temperature": 0.0,
    }
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
    est_vol = parsed.get("concrete_volume_m3")
    est_dcr = parsed.get("governing_dcr")

    numerical_claims = 0
    hallucinated_claims = 0

    if base_vol is not None:
        numerical_claims += 1
        try:
            vol_err = abs(float(est_vol) - float(base_vol)) / max(float(base_vol), 1e-6)
            if vol_err > 0.05 or not code_execution_ok:
                hallucinated_claims += 1
        except (TypeError, ValueError):
            hallucinated_claims += 1

    if base_dcr is not None:
        numerical_claims += 1
        try:
            dcr_err = abs(float(est_dcr) - float(base_dcr)) / max(float(base_dcr), 1e-6)
            if dcr_err > 0.05 or not code_execution_ok:
                hallucinated_claims += 1
        except (TypeError, ValueError):
            hallucinated_claims += 1

    if numerical_claims == 0:
        numerical_claims = 1
        hallucinated_claims = 1 if not code_execution_ok else 0

    chr_pct = round((hallucinated_claims / max(numerical_claims, 1)) * 100.0, 1)

    print(
        f"\n--> Result: [CODE-GEN BASELINE] | Executed: {code_execution_ok} | "
        f"Hallucinations: {hallucinated_claims}/{numerical_claims} (CHR: {chr_pct}%) | Time: {t_elapsed}s"
    )

    return {
        "case_id": case_id,
        "name": case["name"],
        "group": case.get("group", ""),
        "model": model,
        "configuration": "code_gen",
        "design_required": requires_design,
        "success": code_execution_ok,
        "code_compliant": False if requires_design else None,
        "final_stage": "PYTHON_SCRIPT_GENERATION",
        "stages_visited": [],
        "wall_clock_time_sec": t_elapsed,
        "turns_used": 1,
        "tools_called": [],
        "missing_expected_tools": case.get("expected_tools", []),
        "tool_failures_count": 0 if code_execution_ok else 1,
        "tool_failures": error_messages,
        "initial_dcr": est_dcr if isinstance(est_dcr, (int, float)) else None,
        "final_dcr": est_dcr if isinstance(est_dcr, (int, float)) else None,
        "dcr_history": [est_dcr] if isinstance(est_dcr, (int, float)) else [],
        "iterations_to_converge": None,
        "nodes_count": 0,
        "elements_count": 0,
        "concrete_volume_m3": float(est_vol) if isinstance(est_vol, (int, float)) else 0.0,
        "baseline_concrete_volume_m3": base_vol,
        "material_economy_ratio": None,
        "numerical_claims_count": numerical_claims,
        "hallucinated_claims_count": hallucinated_claims,
        "calculation_hallucination_rate_pct": chr_pct,
        "error_messages": error_messages,
        "final_message_snippet": (raw_reply[:200] + "...") if len(raw_reply) > 200 else raw_reply,
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
    verbose: bool = True,
) -> Dict[str, Any]:
    """Execute a single benchmark test case with the neuro-symbolic agent."""
    case_id = case["id"]
    prompt = case["prompt"]
    expected_tools = case.get("expected_tools", [])

    print(f"\n{'='*75}")
    print(f"CASE: [{case_id}] {case['name']} (Group: {case.get('group', 'N/A')} | Config: {config})")
    print(f"{'='*75}")

    if config == "direct_llm":
        return run_direct_llm_baseline(
            case=case,
            model=model,
            api_base=api_base,
            api_key=api_key,
            timeout=timeout,
            verbose=verbose,
        )
    elif config == "code_gen":
        return run_code_gen_baseline(
            case=case,
            model=model,
            api_base=api_base,
            api_key=api_key,
            timeout=timeout,
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
        temperature=0.0,
        timeout=timeout,
    )

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
        if resolved_image and "attachments" in sig.parameters:
            generator = runner.run_stream(prompt, attachments=[str(resolved_image)])
        elif resolved_image and "image_path" in sig.parameters:
            generator = runner.run_stream(prompt, image_path=str(resolved_image))
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

    code_compliant = (governing_dcr is not None and governing_dcr <= 1.0) or (passed_flag is True)

    # Convergence iterations (N_iter) for self-healing / reflection cases
    iterations_to_converge = None
    if requires_design and dcr_history:
        initial_dcr = dcr_history[0]
        if initial_dcr is not None and initial_dcr > 1.0:
            iterations_to_converge = (len(dcr_history) - 1) if code_compliant else None
        elif initial_dcr is not None and initial_dcr <= 1.0:
            iterations_to_converge = 0

    res = {
        "case_id": case_id,
        "name": case["name"],
        "group": case.get("group", ""),
        "model": model,
        "configuration": config,
        "design_required": requires_design,
        "success": task_completed,
        "code_compliant": code_compliant if requires_design else None,
        "final_stage": final_stage,
        "stages_visited": stages_visited,
        "wall_clock_time_sec": t_elapsed,
        "turns_used": len(runner.messages) // 2,
        "tools_called": tools_called,
        "missing_expected_tools": missing_expected_tools,
        "tool_failures_count": len(tool_failures),
        "tool_failures": tool_failures,
        "initial_dcr": dcr_history[0] if dcr_history else None,
        "final_dcr": dcr_history[-1] if dcr_history else governing_dcr,
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
        "numerical_claims_count": len(dcr_history) + (1 if concrete_vol > 0 else 0),
        "hallucinated_claims_count": 0,
        "calculation_hallucination_rate_pct": 0.0,
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
    parser.add_argument("--model", type=str, default="nemotron-3-ultra:cloud", help="Model identifier")
    parser.add_argument("--provider", type=str, default="auto", help="Provider: ollama, native, gemini, etc.")
    parser.add_argument("--api-base", type=str, default="", help="Custom API endpoint (e.g. http://localhost:11434/v1)")
    parser.add_argument("--api-key", type=str, default="", help="API key")
    parser.add_argument("--cases", type=str, default="all", help="Case ID(s) comma-separated, group name (Group_A_2D), or 'all'")
    parser.add_argument(
        "--config",
        type=str,
        default="full_agent",
        choices=["full_agent", "ablated", "direct_llm", "code_gen"],
        help="Benchmark configuration (full_agent, ablated, direct_llm, code_gen)",
    )
    parser.add_argument("--max-turns", type=int, default=10, help="Maximum dialogue turns per case")
    parser.add_argument("--timeout", type=float, default=300.0, help="LLM request timeout in seconds (default: 300.0)")
    parser.add_argument("--cases-file", type=str, default="", help="Custom benchmark cases JSON path")
    parser.add_argument("--output-dir", type=str, default="", help="Custom output directory for results")
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
        selected_cases = [c for c in all_cases if c["id"] in req_ids]

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
    print(f" Total Cases:   {len(selected_cases)}")
    print(f" Timestamp:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    results = []
    for case in selected_cases:
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
        )
        results.append(case_res)

    # Compute aggregate metrics
    n_total = len(results)
    n_success = sum(1 for r in results if r["success"])
    design_cases = [r for r in results if r.get("design_required", False)]
    n_design_cases = len(design_cases)
    n_compliant = sum(1 for r in design_cases if r.get("code_compliant") is True)
    avg_time = round(sum(r["wall_clock_time_sec"] for r in results) / max(n_total, 1), 2)
    tcr = round((n_success / max(n_total, 1)) * 100, 1)
    ccr = round((n_compliant / max(n_design_cases, 1)) * 100, 1) if n_design_cases > 0 else None

    # Calculation Hallucination Rate (CHR)
    total_claims = sum(r.get("numerical_claims_count", 0) for r in results)
    total_hallucinations = sum(r.get("hallucinated_claims_count", 0) for r in results)
    avg_chr = (
        round((total_hallucinations / max(total_claims, 1)) * 100.0, 1)
        if args.config == "direct_llm"
        else 0.0
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

    summary = {
        "model": args.model,
        "configuration": args.config,
        "timestamp": datetime.now().isoformat(),
        "total_cases": n_total,
        "design_cases": n_design_cases,
        "successful_cases": n_success,
        "compliant_cases": n_compliant,
        "task_completion_rate_pct": tcr,
        "code_compliance_rate_pct": ccr,
        "calculation_hallucination_rate_pct": avg_chr,
        "reflection_cases_count": n_reflection,
        "converged_reflection_cases_count": len(converged_reflection),
        "avg_convergence_iterations": avg_iterations,
        "avg_material_economy_ratio": avg_eta,
        "avg_runtime_sec": avg_time,
        "case_results": results,
    }

    # Save to unique timestamped JSON (guaranteeing never to overwrite existing files)
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