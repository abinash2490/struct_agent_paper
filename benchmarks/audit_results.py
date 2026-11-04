"""
Post-run consistency audit of agent results (finds harness and tool bugs, not agent mistakes)
=============================================================================================

For each agent design run that passed prompt-to-schema fidelity and checked its delivered model, the
agent's own model reproduces the specification, so its final design check should agree with the oracle.
The audit replays the run's logged tool calls through the same tools (no LLM calls) and reports:

* ``replay``   - the replayed final governing DCR differs from the recorded one, or a call succeeds where it
                 failed in the run or vice versa (a tool changed since the run or is not deterministic, or
                 the tool log is incomplete);
* ``stale``    - the final design check used an analysis of an earlier state of the model (sections or
                 loads changed without a new analysis). Re-scoring with ``--replay`` marks such runs as
                 unverified;
* ``oracle``   - the agent's final DCR differs from the oracle's DCR on the canonical model by more
                 than the tolerance, although fidelity passed. Either the fidelity check misses an input
                 the oracle uses (as a hidden vertical-seismic input once did), or a tool and the
                 oracle disagree. Each flag needs a look before the results are reported.

Runs whose logged arguments were truncated cannot be replayed and are listed as skipped.

Usage
-----
python research_paper/benchmarks/audit_results.py research_paper/benchmarks/results/results_<...>.json [--tol 0.02]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BENCHMARKS_DIR = Path(__file__).resolve().parent
REPO_ROOT = BENCHMARKS_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research_paper.benchmarks.benchmark_utils import DesignCheckTracker  # noqa: E402
from research_paper.benchmarks.run_benchmarks import RUNNER_SETTINGS  # noqa: E402
from struct_agent.llm import AgentRunner, BaseLLMProvider, LLMResponse  # noqa: E402


class _NoLLM(BaseLLMProvider):
    def __init__(self) -> None:
        super().__init__(model="audit-replay")

    def generate(self, messages, tools=None, temperature=0.0):
        return LLMResponse(content="")

    def generate_stream(self, messages, tools=None, temperature=0.0):
        yield self.generate(messages)


def _truncated(value: Any) -> bool:
    """True when the run log shortened an argument (run_benchmarks._compact), so it cannot be replayed."""
    if isinstance(value, str):
        return (value.startswith("<") and value.endswith(">")) or value.endswith("...") or " more" in value[:12]
    if isinstance(value, dict):
        return any(_truncated(v) for v in value.values())
    if isinstance(value, list):
        return any(_truncated(v) for v in value)
    return False


# File-writing tools and their output argument: a replay writes to a scratch directory, never to the deliverable
# paths that a running campaign checks (an audit during a campaign would otherwise supply a run's files)
FILE_OUTPUT_ARGS = {"generate_drawings": "output_path", "export_to_sap2000": "output_path",
                    "export_to_etabs": "output_path"}


def replayable(record: Dict[str, Any]) -> bool:
    return bool(record.get("tool_log")) and not any(_truncated(t.get("args")) for t in record["tool_log"])


def replay(record: Dict[str, Any], tracker: Optional[DesignCheckTracker] = None,
           mismatches: Optional[List[str]] = None) -> Tuple[Any, Optional[float]]:
    """Execute the logged tool calls again (no LLM): the agent's final project and its last governing DCR.

    The runner has the record's configuration, so calls the run refused (a tool removed by the ablation,
    a blocked model re-creation) are refused again. A ``tracker`` follows the replayed calls. Calls whose
    success differs from the log (the tools changed since the run: nemotron's design checks of unfactored
    load cases, refused by a later run_design) are appended to ``mismatches``; the replay then no longer
    rebuilds the run's model.
    """
    runner = AgentRunner(provider=_NoLLM(), **RUNNER_SETTINGS[record["configuration"]])
    last = None
    cwd = os.getcwd()
    os.chdir(REPO_ROOT)  # logged file paths are repository-relative
    scratch = tempfile.TemporaryDirectory(prefix="audit_replay_")
    try:
        for i, call in enumerate(record.get("tool_log", [])):
            args, out = call["args"], FILE_OUTPUT_ARGS.get(call["tool"])
            if out and isinstance(args, dict) and args.get(out):
                args = {**args, out: str(Path(scratch.name) / Path(str(args[out])).name)}
            res = runner.apply_tool_call(call["tool"], args)
            if tracker is not None:
                tracker.record(call["tool"], runner.project, res.ok)
            if mismatches is not None and "ok" in call and bool(call["ok"]) != res.ok:
                mismatches.append(f"call {i} {call['tool']}: logged {'ok' if call['ok'] else 'failed'}, replay "
                                  f"{'ok' if res.ok else 'failed: ' + (res.error.message if res.error else '')[:120]}")
            if call["tool"] == "run_design" and res.ok:
                last = res.data.get("governing_dcr")
    finally:
        os.chdir(cwd)
        scratch.cleanup()
    return runner.project, None if last is None else float(last)


def audit(path: Path, tol: float, cases: Optional[List[str]] = None) -> Path:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows, skipped = [], []
    for r in data["case_results"]:
        if cases and not any(r["case_id"].startswith(c) for c in cases):
            continue
        if r.get("design_task") == "none" or not r.get("final_design_verified") or not r.get("dcr_history"):
            continue
        if r.get("prompt_to_schema_fidelity_passed") is not True or r.get("final_dcr") is None:
            continue
        if not replayable(r):
            skipped.append(f"{r['case_id']} seed {r['seed_index']}")
            continue
        recorded, oracle = r["dcr_history"][-1], r["final_dcr"]
        checks, mismatches = DesignCheckTracker(), []
        project, replayed = replay(r, checks, mismatches)
        flags = []
        if mismatches or replayed is None or abs(replayed - recorded) > 1e-6 * max(1.0, abs(recorded)):
            flags.append("replay")
        if not checks.design_current(project):
            flags.append("stale")
        if abs(recorded - oracle) > tol:
            flags.append("oracle")
        rows.append((r["case_id"], r["seed_index"], recorded, replayed, oracle, r.get("governing_limit_state"), flags))
        print(f"{r['case_id']:38s} seed {r['seed_index']}  agent {recorded:.4f}  replay "
              f"{'-' if replayed is None else f'{replayed:.4f}'}  oracle {oracle:.4f}  {' '.join(flags) or 'ok'}")

    lines = [f"# Consistency audit of `{path.name}`", "",
             f"Runs audited: {len(rows)} (verified designs with PSFR passed); tolerance on the oracle DCR: {tol}.",
             f"Flagged: {sum(1 for row in rows if row[-1])}. Skipped (truncated arguments): {len(skipped)}.", "",
             "| Case | Seed | Agent DCR | Replayed DCR | Oracle DCR | Oracle governing check | Flags |",
             "|---|:---:|:---:|:---:|:---:|---|---|"]
    for cid, seed, rec, rep, ora, gov, flags in rows:
        lines.append(f"| {cid} | {seed} | {rec:.4f} | {'-' if rep is None else f'{rep:.4f}'} | {ora:.4f} | {gov} | "
                     f"{', '.join(flags) or 'ok'} |")
    if skipped:
        lines += ["", "Skipped: " + "; ".join(skipped)]
    out = path.parent / f"audit_{path.stem}_{datetime.now():%Y%m%d_%H%M%S}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n{sum(1 for row in rows if row[-1])} of {len(rows)} audited runs flagged -> {out}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("results_file")
    parser.add_argument("--tol", type=float, default=0.02, help="Allowed |agent DCR - oracle DCR|")
    parser.add_argument("--cases", default="", help="Comma-separated case ID prefixes (default: all)")
    args = parser.parse_args()
    audit(Path(args.results_file), args.tol, [c for c in args.cases.split(",") if c] or None)


if __name__ == "__main__":
    main()
