"""
Export the system prompts of the four LLM configurations (manuscript Supplementary Material S1), verbatim as the
code builds them.

Usage
-----
    python research_paper/benchmarks/export_system_prompts.py
writes research_paper/manuscript/supplementary/S1_system_prompts.md. The single-shot prompts depend on the case
(their JSON keys are the case's sections and metrics); they are shown for B08, the case of Appendix A.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research_paper.benchmarks import run_benchmarks  # noqa: E402
from research_paper.benchmarks.case_schema import load_cases  # noqa: E402
from struct_agent.llm.prompts import (  # noqa: E402
    IMPORT_MATERIALS, NO_REFLECTION_STAGE, REFLECTION_STAGE, build_system_prompt)

OUTPUT = REPO_ROOT / "research_paper" / "manuscript" / "supplementary" / "S1_system_prompts.md"
FENCE = "````"  # the code-generation prompt itself contains a ``` fence


def ablated_instruction() -> str:
    """The restriction `run_agent` appends to the system prompt of the ablated agent."""
    src = inspect.getsource(run_benchmarks.run_agent)
    start = src.index('custom = ("') + len('custom = (')
    return eval(" ".join(src[start:src.index(")", start)].split()))  # its two adjacent string literals


def block(text: str) -> str:
    return f"{FENCE}text\n{text.rstrip()}\n{FENCE}"


def main() -> None:
    full = build_system_prompt(allow_resizing=True)
    ablated = build_system_prompt(allow_resizing=False)
    # The ablated prompt differs from the full one only by these two substitutions, as S1.2 states
    assert ablated == full.replace(REFLECTION_STAGE, NO_REFLECTION_STAGE).replace(IMPORT_MATERIALS, "")
    b08 = next(c for c in load_cases() if c.id.startswith("B08"))
    direct = run_benchmarks.single_shot_messages(b08, "direct_llm")[0]["content"]
    code = run_benchmarks.single_shot_messages(b08, "code_gen")[0]["content"]

    out = f"""# Supplementary Material S1. System Prompts

This file reproduces the system prompts of the four LLM configurations verbatim, as the code builds them (`struct_agent/struct_agent/llm/prompts.py` and `research_paper/benchmarks/run_benchmarks.py`). The case prompt follows the system prompt as the user message; Appendix A gives the case prompt of B08.

## S1.1. Full agent (`full_agent`)

The system prompt is the same for every case and model.

{block(full)}

## S1.2. Agent without resizing (`ablated`)

The system prompt of S1.1 with two changes: Stage 6 is replaced by a report stage, and the import rule that sets the concrete strength of an imported model through `modify_project` is left out, because the ablated agent has no `modify_project` tool. The runner then appends the restriction below to the system prompt.

Stage 6 of S1.1:

{block(REFLECTION_STAGE)}

is replaced by:

{block(NO_REFLECTION_STAGE)}

and the system prompt ends with:

{block("### ADDITIONAL USER INSTRUCTIONS:" + chr(10) + ablated_instruction())}

## S1.3. Direct prompting (`direct_llm`)

The system prompt asks for a JSON answer whose keys depend on the case: the four section dimensions of a design case and the metrics the case requests, each in the case's units. For case B08:

{block(direct)}

## S1.4. Code generation (`code_gen`)

As in S1.3, with a request for a Python script that prints the JSON answer. For case B08:

{block(code)}
"""
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(out, encoding="utf-8")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
