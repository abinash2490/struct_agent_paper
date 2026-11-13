"""
Re-score saved agent runs with the current oracle, claim parser, and probe rules (no LLM calls)
==============================================================================================

The agent's final sections, final message, design-check history, and verification flag are kept in each
record, so code compliance, claims (CHR, completeness), material economy, probe behavior, and failure
modes can be recomputed after a scoring fix. With ``--replay``, prompt-to-schema fidelity and the final
design check's verification (did it use an analysis of the delivered model?) are recomputed too: the tools
are deterministic, so replaying a run's logged tool calls rebuilds the agent's model exactly
(see audit_results.py). Tool success and deliverables keep their recorded values. Single-shot records (direct_llm,
code_gen) are re-scored from their answer as run_single_shot scores it: sections, claims, and success from the
JSON answer, probe behavior from its text (for code_gen, what the script printed; a crashed script printed nothing).

The file is rewritten in place; the original is kept next to it as ``<name>.bak`` (written once, so
repeated re-scoring keeps the file as first produced by run_benchmarks.py).

Usage
-----
python research_paper/benchmarks/rescore_results.py research_paper/benchmarks/results/results_<...>.json
    [--replay]                    also recompute PSFR by replaying the logged tool calls
    [--rerun-timed-out-scripts]   code_gen: execute again the saved scripts that a shorter, earlier time limit
                                  stopped (run_benchmarks.SCRIPT_TIME_LIMIT)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

BENCHMARKS_DIR = Path(__file__).resolve().parent
REPO_ROOT = BENCHMARKS_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research_paper.benchmarks.audit_results import replay, replayable  # noqa: E402
from research_paper.benchmarks.benchmark_utils import (  # noqa: E402
    DesignCheckTracker,
    evaluate_prompt_to_schema_fidelity,
    parse_numerical_claims_from_text,
)
from research_paper.benchmarks.case_schema import SectionPair, cases_by_id  # noqa: E402
from research_paper.benchmarks.oracle_verifier import OracleVerifier  # noqa: E402
from research_paper.benchmarks.run_benchmarks import (  # noqa: E402
    SCRIPT_TIME_LIMIT,
    _parse_json_object,
    is_answer,
    _sections_from_answer,
    build_record,
    classify_failure,
    context_limits,
    execute_script,
    inconsistent_usage,
    reference_load_totals,
    script_from_reply,
    single_shot_claims,
    summarize,
)

AGENT_CONFIGS = ("full_agent", "ablated")
SINGLE_SHOT_CONFIGS = ("direct_llm", "code_gen")
CARRIED = ("seed_index", "agent_concrete_volume", "turn_limit_reached", "max_prompt_tokens", "truncated_responses",
           "prompt_truncations", "final_response_truncated", "max_output_tokens", "output_cap_hits", "final_response_capped",
           "max_completion_tokens", "provider_error", "llm_calls", "repeated_calls", "tool_log", "final_message",
           "code_executed", "script_output", "reasoning_effort", "output_dir", "undeclared_outputs", "overwritten_files",
           "answer_units", "replay_mismatches", "rejected_tool_calls", "script_rerun")
_TIMED_OUT = re.compile(r"^TimeoutExpired:.*timed out after ([\d.]+) seconds", re.DOTALL)


def rerun_timed_out_script(r: dict, cases: dict) -> bool:
    """Execute again, at the current ``SCRIPT_TIME_LIMIT``, a code_gen script that an earlier and shorter limit
    stopped, and update the record as ``run_single_shot`` would have written it: the execution flag, the printed
    output, the errors, and the wall-clock time (the earlier limit replaced by the new execution time). The script
    is the one saved in the record, so no LLM is called. Returns whether the record was a timed-out script."""
    if r.get("configuration") != "code_gen":
        return False
    timed_out = [m for m in (_TIMED_OUT.match(str(e)) for e in r.get("error_messages") or []) if m]
    if not timed_out or float(timed_out[0].group(1)) >= SCRIPT_TIME_LIMIT:
        return False
    previous = float(timed_out[0].group(1))
    errors = [e for e in r["error_messages"] if not _TIMED_OUT.match(str(e)) and not str(e).startswith("Oracle:")]
    t0 = time.perf_counter()
    try:
        executed, stdout, stderr = execute_script(cases[r["case_id"]], script_from_reply(r["final_message"]))
        if not executed:
            errors.append(f"Script error: {stderr[-500:]}")
    except subprocess.TimeoutExpired as exc:
        executed, stdout = None, ""
        errors.append(f"{type(exc).__name__}: {exc}")
    elapsed = time.perf_counter() - t0
    r["code_executed"] = executed
    r["script_output"] = stdout[-4000:]
    r["error_messages"] = errors
    r["wall_clock_time_sec"] = round(r["wall_clock_time_sec"] - previous + elapsed, 2)
    r["script_rerun"] = {"previous_limit_s": previous, "limit_s": SCRIPT_TIME_LIMIT,
                         "execution_s": round(elapsed, 1), "executed": executed}
    print(f"  {r['case_id']}: script re-executed at {SCRIPT_TIME_LIMIT:g} s (stopped at {previous:g} s before): "
          f"{'ran to the end' if executed else 'error' if executed is False else 'stopped again'} in {elapsed:.0f} s")
    return True


def rescore_record(r: dict, oracle: OracleVerifier, cases: dict, replay_psfr: bool = False) -> dict:
    case = cases[r["case_id"]]
    single_shot = r["configuration"] in SINGLE_SHOT_CONFIGS
    answer = r.get("final_message", "")
    if r["configuration"] == "code_gen":  # the user receives the script's output, not its source
        answer = r.get("script_output", "") if r.get("code_executed") else ""
    success = r["success"]
    if single_shot:  # as run_single_shot scores it: the JSON answer gives the sections and claims
        parsed = _parse_json_object(answer)
        sections = _sections_from_answer(parsed)
        claims = single_shot_claims(case, parsed, r.get("answer_units") or {})
    else:
        s = r.get("final_sections")
        sections = None
        if case.deliverables.design != "none" and s:
            sections = SectionPair(column=tuple(s["column"]), beam=tuple(s["beam"]))
        claims = parse_numerical_claims_from_text(answer, case.spec.units)
    res = oracle.evaluate(case.id, sections, claims)
    if single_shot:  # the recorded success of a withheld-input probe followed the old probe verdict
        success = is_answer(parsed) and r.get("code_executed") is not False and res.solution.error is None
    psfr = None
    if r.get("prompt_to_schema_fidelity_passed") is not None:
        psfr = (r["prompt_to_schema_fidelity_passed"], r.get("prompt_to_schema_fidelity_details") or {})
    verified = r.get("final_design_verified")
    mismatches: list = []
    if replay_psfr and r.get("nodes_count") and replayable(r):
        # The tools are deterministic: replaying the logged calls rebuilds the agent's model exactly, unless a
        # tool changed since the run; then the recorded values are kept and the run is listed for a re-run
        checks = DesignCheckTracker()
        project, _ = replay(r, checks, mismatches)
        if verified is not None and not mismatches:
            verified = checks.design_current(project)
        if not mismatches and project is not None and project.model is not None and project.model.nodes:
            tool_args = [(t["tool"], t["args"]) for t in r["tool_log"] if t.get("ok")]
            psfr = evaluate_prompt_to_schema_fidelity(
                project, case, tool_args, reference_load_totals(oracle, case, sections))
    errors = [e for e in r.get("error_messages", []) if not e.startswith("Oracle:")]
    new = build_record(
        case, config=r["configuration"], model=r["model"], temperature=r["temperature"], seed=r["seed"],
        oracle=res, success=success, elapsed=r["wall_clock_time_sec"], final_message=answer,
        tools_called=r.get("tools_called"), tool_failures=r.get("tool_failures"),
        missing_expected_tools=r.get("missing_expected_tools"), dcr_history=r.get("dcr_history"),
        final_stage=r.get("final_stage", ""), stages_visited=r.get("stages_visited"), turns_used=r.get("turns_used", 1),
        nodes_count=r.get("nodes_count", 0), elements_count=r.get("elements_count", 0), psfr=psfr,
        deliverables=r.get("deliverables"), uniform_sections=r.get("uniform_sections"),
        error_messages=errors + ([f"Oracle: {res.solution.error}"] if res.solution.error else []),
        final_design_verified=verified,
    )
    for key in CARRIED:
        if key in r:
            new[key] = r[key]
    if r.get("code_executed") is False:  # a crashed script gave no answer, whatever its comments assume or ask
        new["success"] = False
    had_error_finish = any(c.get("finish_reason") == "error" or (single_shot and inconsistent_usage(c))
                           for c in (r.get("llm_calls") or []))
    if "provider_error" not in r or had_error_finish:  # recorded before the flag or finish_reason='error' check
        new["provider_error"] = (
            bool(r.get("provider_error"))
            or any(e.startswith("LLM Provider error") for e in errors)
            or had_error_finish
        )
    if r.get("llm_calls") and not single_shot:  # single-shot records keep their recorded call flags
        calls = [dict(c) for c in r["llm_calls"]]
        if r.get("turn_limit_reached") and "tools_offered" not in calls[-1]:
            calls[-1]["tools_offered"] = False  # logged before the flag existed: the tool-free report turn
        new.update(context_limits(calls, r.get("max_output_tokens")))
    if replay_psfr:
        new["replay_mismatches"] = mismatches
    new["failure_mode"] = classify_failure(new)
    return new


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("results_file", help="results_*.json written by run_benchmarks.py")
    parser.add_argument("--replay", action="store_true",
                        help="Also recompute PSFR by replaying each run's logged tool calls (no LLM calls)")
    parser.add_argument("--rerun-timed-out-scripts", action="store_true",
                        help="code_gen: execute again, at the current time limit, the saved scripts that an earlier "
                             "and shorter limit stopped (no LLM calls)")
    args = parser.parse_args()
    path = Path(args.results_file)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("configuration") not in AGENT_CONFIGS + SINGLE_SHOT_CONFIGS:
        sys.exit(f"{path.name}: configuration '{data.get('configuration')}' has no LLM answer; nothing to re-score.")

    oracle, cases = OracleVerifier(), cases_by_id()
    if args.rerun_timed_out_scripts:
        rerun = [r["case_id"] for r in data["case_results"] if rerun_timed_out_script(r, cases)]
        print(f"  timed-out scripts re-executed: {len(rerun)}")
    results = [rescore_record(r, oracle, cases, replay_psfr=args.replay) for r in data["case_results"]]
    summary = summarize(results, model=data["model"], config=data["configuration"],
                        temperature=data["temperature"], seeds=data["seeds"],
                        not_applicable_cases=data.get("not_applicable_cases"))
    summary["timestamp"] = data["timestamp"]  # same run: keep its place in the run history
    summary["rescored"] = True

    if not path.with_suffix(".bak").exists():  # keep the file as first written, across repeated re-scoring
        shutil.copyfile(path, path.with_suffix(".bak"))
    path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    for key in ("code_compliance_rate_pct", "calculation_hallucination_rate_pct", "claim_completeness_rate_pct",
                "probe_behavior_rate_pct", "avg_material_economy_ratio"):
        print(f"  {key:38s} {data.get(key)} -> {summary[key]}")
    print(f"  re-scored {len(results)} records -> {path} (original: {path.with_suffix('.bak').name})")
    diverged = [f"{r['case_id']} seed {r['seed_index']}" for r in results if r.get("replay_mismatches")]
    if diverged:
        print(f"  WARNING: {len(diverged)} runs no longer replay (the tools changed since the run); their recorded "
              f"PSFR and verification were kept, see 'replay_mismatches'. Re-run them for results on the current "
              f"tools: {'; '.join(diverged)}")


if __name__ == "__main__":
    main()
