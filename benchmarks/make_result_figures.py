"""
Result figures of manuscript Section 5 (Figures 5.1-5.3) from the final results files.

Usage
-----
    python research_paper/benchmarks/make_result_figures.py
writes research_paper/manuscript/figures/fig_ccr_chr.png, fig_oracle_dcr.png and fig_plan_bays.png (300 dpi, with
PDF copies). Every value comes from the latest results file of each model and configuration, loaded as
``analyze_results.py`` loads them; the plan bays come from the plan drafts logged in the agent runs.
"""

from __future__ import annotations

import sys
from itertools import accumulate
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research_paper.benchmarks.analyze_results import load_all_results  # noqa: E402
from research_paper.benchmarks.case_schema import cases_by_id  # noqa: E402
from struct_core import conversion_factor  # noqa: E402

RESULTS = REPO_ROOT / "research_paper" / "benchmarks" / "results"
FIGURES = REPO_ROOT / "research_paper" / "manuscript" / "figures"

MODELS = ["qwen3.5:9b", "minimax-m3.1-flash:cloud", "gemma4:31b-cloud", "deepseek-v4.1-flash:cloud"]
SHORT = {"qwen3.5:9b": "qwen3.5:9b", "minimax-m3.1-flash:cloud": "minimax-m3.1-flash",
         "gemma4:31b-cloud": "gemma4:31b", "deepseek-v4.1-flash:cloud": "deepseek-v4.1-flash"}
CONFIGS = ["full_agent", "ablated", "direct_llm", "code_gen"]
LABEL = {"full_agent": "Full agent", "ablated": "Agent without resizing", "direct_llm": "Direct prompting",
         "code_gen": "Code generation"}
# Categorical slots 1-3 of the reference palette (validated all-pairs, light mode); code generation, which
# delivered few results, is a neutral gray. Every configuration also has its own marker (secondary encoding).
COLOR = {"full_agent": "#2a78d6", "ablated": "#eb6834", "direct_llm": "#1baf7a", "code_gen": "#6b6a66"}
MARKER = {"full_agent": "o", "ablated": "s", "direct_llm": "^", "code_gen": "D"}
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e1", "#ffffff"
MISMATCH, MATCH, TRUTH = "#eb6834", "#2a78d6", "#8d8c88"

plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"], "font.size": 8,
    "axes.edgecolor": INK_2, "axes.labelcolor": INK, "axes.linewidth": 0.6, "xtick.color": INK_2,
    "ytick.color": INK_2, "xtick.major.width": 0.6, "ytick.major.width": 0.6, "axes.titlesize": 8.5,
    "axes.titleweight": "bold", "legend.fontsize": 7.5, "legend.frameon": False, "figure.dpi": 300,
    "savefig.dpi": 300, "savefig.bbox": "tight", "savefig.facecolor": SURFACE,
})


def _runs() -> Dict[Tuple[str, str], dict]:
    return {(s["model"], s["configuration"]): s for s in load_all_results(RESULTS)}


def _save(fig, name: str) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(FIGURES / f"{name}.{ext}")
    plt.close(fig)
    print(f"wrote {FIGURES / name}.png/.pdf")


def _style(ax) -> None:
    ax.grid(True, color=GRID, linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


# ----------------------------------------------------------------------------------------------------------------
# Figure 2: code compliance against the share of wrong reported values
# ----------------------------------------------------------------------------------------------------------------
LABEL_OFFSET = {  # (dx, dy, ha) in points for the model label of each point, placed by hand against overlaps
    ("deepseek-v4.1-flash:cloud", "full_agent"): (-3, 9, "left"), ("gemma4:31b-cloud", "full_agent"): (6, 0, "left"),
    ("minimax-m3.1-flash:cloud", "full_agent"): (-3, 9, "left"), ("qwen3.5:9b", "full_agent"): (6, 0, "left"),
    ("deepseek-v4.1-flash:cloud", "ablated"): (-3, -9, "left"), ("minimax-m3.1-flash:cloud", "ablated"): (-3, -9, "left"),
    ("gemma4:31b-cloud", "ablated"): (6, 0, "left"), ("qwen3.5:9b", "ablated"): (6, 0, "left"),
    ("deepseek-v4.1-flash:cloud", "direct_llm"): (6, 0, "left"), ("minimax-m3.1-flash:cloud", "direct_llm"): (0, 9, "center"),
    ("gemma4:31b-cloud", "direct_llm"): (6, 0, "left"), ("qwen3.5:9b", "direct_llm"): (0, 9, "right"),
    ("deepseek-v4.1-flash:cloud", "code_gen"): (6, 0, "left"), ("gemma4:31b-cloud", "code_gen"): (0, -10, "center"),
}


def figure_ccr_chr(runs) -> None:
    fig, ax = plt.subplots(figsize=(6.3, 3.9))
    _style(ax)
    for model in MODELS:
        for cfg in CONFIGS:
            s = runs.get((model, cfg))
            if s is None:
                continue
            claims = sum(r.get("claims_made_count", 0) for r in s["case_results"])
            if claims == 0:
                continue  # no reported value to score (minimax and qwen code generation)
            chr_, ccr = s["calculation_hallucination_rate_pct"], s["code_compliance_rate_pct"]
            hollow = cfg == "code_gen"
            ax.scatter(chr_, ccr, s=46, marker=MARKER[cfg], zorder=3,
                       facecolor=SURFACE if hollow else COLOR[cfg], edgecolor=COLOR[cfg] if hollow else SURFACE,
                       linewidth=1.4 if hollow else 1.0)
            dx, dy, ha = LABEL_OFFSET.get((model, cfg), (6, 0, "left"))
            ax.annotate(SHORT[model], (chr_, ccr), xytext=(dx, dy), textcoords="offset points", fontsize=6.5,
                        color=INK_2, ha=ha, va="center")
    ax.set_xlim(-2, 66)
    ax.set_ylim(-4, 110)
    ax.set_xlabel("Wrong reported values, CHR (%)")
    ax.set_ylabel("Compliant designs, CCR (%)")
    handles = [Line2D([], [], linestyle="", marker=MARKER[c], markersize=6,
                      markerfacecolor=SURFACE if c == "code_gen" else COLOR[c],
                      markeredgecolor=COLOR[c] if c == "code_gen" else SURFACE, label=LABEL[c]) for c in CONFIGS]
    ax.legend(handles=handles, loc="center right", bbox_to_anchor=(0.98, 0.42), handletextpad=0.4)
    _save(fig, "fig_ccr_chr")


# ----------------------------------------------------------------------------------------------------------------
# Figure 3: the oracle's governing DCR of every delivered design
# ----------------------------------------------------------------------------------------------------------------
DCR_TOP = 2.8  # designs above it are drawn at the top edge with their value


def _swarm(values: List[float], step: float = 0.052, gap: float = 0.045) -> List[float]:
    """Horizontal offsets of a one-dimensional beeswarm: each point takes the offset nearest the center line that
    keeps it at least ``gap`` (in DCR) from the points already placed there."""
    placed: List[Tuple[float, float]] = []
    offsets = []
    for v in values:
        y = min(v, DCR_TOP)
        k = 0
        while True:
            for off in ((0.0,) if k == 0 else (k * step, -k * step)):
                if all(abs(off - o) > step / 2 or abs(y - p) >= gap for o, p in placed):
                    placed.append((off, y))
                    offsets.append(off)
                    break
            else:
                k += 1
                continue
            break
    return offsets


def figure_oracle_dcr(runs) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(6.3, 5.0), sharey=True, sharex=True)
    offsets = {c: i for i, c in enumerate(CONFIGS)}
    for ax, model in zip(axes.flat, MODELS):
        _style(ax)
        ax.axhline(1.0, color=INK, linewidth=0.8, linestyle=(0, (4, 2)), zorder=2)
        for cfg in CONFIGS:
            s = runs.get((model, cfg))
            records = [r for r in s["case_results"] if r.get("design_required")] if s else []
            dcrs = sorted(r["final_dcr"] for r in records if r.get("final_dcr") is not None)
            x0 = offsets[cfg]
            hollow = cfg == "code_gen"
            for d, off in zip(dcrs, _swarm(dcrs)):
                ax.scatter(x0 + off, min(d, DCR_TOP), s=11, marker=MARKER[cfg], zorder=3,
                           facecolor=SURFACE if hollow else COLOR[cfg],
                           edgecolor=COLOR[cfg] if hollow else SURFACE, linewidth=0.8 if hollow else 0.4,
                           clip_on=False)
                if d > DCR_TOP:
                    ax.annotate(f"{d:.1f}", (x0 + off, DCR_TOP), xytext=(5, 0), textcoords="offset points",
                                fontsize=6, color=INK_2, va="center")
            ax.text(x0, 0.51, f"{len(dcrs)}/{len(records)}", ha="center", va="bottom", fontsize=6.5, color=INK_2)
        ax.set_ylim(0.5, DCR_TOP)
        ticks = [0.6, 0.8, 1.0, 1.2, 1.6, 2.0, 2.4, 2.8]
        ax.set_yticks(ticks)
        ax.set_yticklabels([f"{t:.1f}" for t in ticks])
        ax.set_xticks(range(len(CONFIGS)))
        ax.set_xticklabels(["Full\nagent", "Without\nresizing", "Direct\nprompting", "Code\ngeneration"], fontsize=7)
        ax.set_xlim(-0.6, len(CONFIGS) - 0.4)
        ax.set_title(SHORT[model], loc="left", color=INK)
    for ax in axes[:, 0]:
        ax.set_ylabel("Governing DCR (oracle)")
    fig.subplots_adjust(hspace=0.25, wspace=0.08)
    _save(fig, "fig_oracle_dcr")


# ----------------------------------------------------------------------------------------------------------------
# Figure 4: bay widths read from the plan drawings
# ----------------------------------------------------------------------------------------------------------------
def _plan_runs(runs) -> Dict[str, Dict[str, object]]:
    cases = cases_by_id()
    out: Dict[str, Dict[str, object]] = {}
    for cid in ("C03", "C04", "C05"):
        case = next(c for k, c in cases.items() if k.startswith(cid))
        g, s = case.spec.geometry, conversion_factor(case.spec.units, "kN, m", "length")
        out[cid] = {"truth": ([w * s for w in g.bay_widths_x], [w * s for w in g.bay_widths_y]), "runs": []}
        for model in MODELS:
            for cfg in ("full_agent", "ablated"):
                rec = next((r for r in runs.get((model, cfg), {}).get("case_results", [])
                            if r["case_id"].startswith(cid)), None)
                drafts = [t for t in (rec or {}).get("tool_log", [])
                          if t["tool"] == "create_model_from_plan_draft" and t.get("ok")]
                label = f"{SHORT[model]}, {'full' if cfg == 'full_agent' else 'without resizing'}"
                if not drafts:
                    out[cid]["runs"].append((label, None))
                    continue
                a = drafts[-1]["args"]
                k = conversion_factor(a.get("units") or "kN, m", "kN, m", "length")
                bays = []
                for axis in ("x_grids", "y_grids"):
                    coords = sorted(float(v["coordinate"]) * k for v in a[axis])
                    bays.append([b - a_ for a_, b in zip(coords, coords[1:])])
                out[cid]["runs"].append((label, tuple(bays)))
    return out


def _oriented(bays: List[float], truth: List[float]) -> List[float]:
    """The run's bays in the drawing's direction (a mirrored plan is the same structure)."""
    def misses(seq):
        return sum(1 for i, b in enumerate(seq) if i >= len(truth) or abs(b - truth[i]) > 0.05) + abs(len(seq) - len(truth))
    return bays if misses(bays) <= misses(bays[::-1]) else bays[::-1]


def figure_plan_bays(runs) -> None:
    plans = _plan_runs(runs)
    names = {"C03": "C03 school", "C04": "C04 hostel", "C05": "C05 mall (feet and inches)"}
    heights = [1 + sum(1 for _, b in plans[c]["runs"] if b is not None) for c in plans]
    fig, axes = plt.subplots(3, 2, figsize=(6.3, 7.2), gridspec_kw={"height_ratios": heights, "width_ratios": [2.4, 1]})
    for row, cid in enumerate(plans):
        truth_xy = plans[cid]["truth"]
        rows = [("Drawing", truth_xy)] + [(lab, b) for lab, b in plans[cid]["runs"] if b is not None]
        for col, axis in enumerate(("X", "Y")):
            ax = axes[row, col]
            truth = truth_xy[col]
            for i, (lab, bays) in enumerate(rows):
                y = len(rows) - 1 - i
                seq = truth if i == 0 else _oriented(bays[col], truth)
                left = 0.0
                for j, w in enumerate(seq):
                    # the j-th bay against the drawing's j-th bay (a bay beyond the drawing's last is extra)
                    ok = j < len(truth) and abs(w - truth[j]) <= 0.05
                    face = TRUTH if i == 0 else (MATCH if ok else MISMATCH)
                    ax.barh(y, w, left=left, height=0.62, color=face, edgecolor=SURFACE, linewidth=1.0, zorder=3)
                    if w >= 1.3:
                        ax.text(left + w / 2, y, f"{w:.2f}".rstrip("0").rstrip("."), ha="center", va="center",
                                fontsize=5.6, color=SURFACE, zorder=4)
                    left += w
            ax.set_yticks(range(len(rows)))
            ax.set_yticklabels([lab for lab, _ in rows][::-1] if col == 0 else [], fontsize=6.5)
            ax.tick_params(axis="y", length=0)
            ax.set_xlim(0, max(sum(truth), max(sum(_oriented(b[col], truth)) for _, b in rows[1:])) * 1.02)
            ax.grid(True, axis="x", color=GRID, linewidth=0.5, zorder=0)
            ax.set_axisbelow(True)
            for side in ("top", "right", "left"):
                ax.spines[side].set_visible(False)
            ax.set_title(f"{names[cid]}, {axis} bays" if col == 0 else f"{axis} bays", loc="left", color=INK)
            if row == 2:
                ax.set_xlabel("Distance along the grid (m)")
    handles = [Patch(color=TRUTH, label="Drawing"), Patch(color=MATCH, label="Read correctly (±0.05 m)"),
               Patch(color=MISMATCH, label="Misread, merged, or extra bay")]
    fig.legend(handles=handles, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.02))
    fig.subplots_adjust(hspace=0.55, wspace=0.08)
    _save(fig, "fig_plan_bays")


# ----------------------------------------------------------------------------------------------------------------
# Figure 5: governing DCR at each design check of the full agents on the resizing cases
# ----------------------------------------------------------------------------------------------------------------
RESIZING = {"A07": ("#2a78d6", "o"), "A08": ("#eb6834", "s"), "B08": ("#1baf7a", "^")}


def figure_convergence(runs) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(6.3, 4.6), sharey=True)
    for ax, model in zip(axes.flat, MODELS):
        _style(ax)
        ax.axhline(1.0, color=INK, linewidth=0.8, linestyle=(0, (4, 2)), zorder=2)
        records = {r["case_id"][:3]: r for r in runs[(model, "full_agent")]["case_results"]}
        longest = 1
        for cid, (color, marker) in RESIZING.items():
            history = records[cid].get("dcr_history") or []
            longest = max(longest, len(history))
            checks = range(1, len(history) + 1)
            ax.plot(checks, history, color=color, linewidth=1.6, zorder=3)
            ax.scatter(checks, history, s=22, marker=marker, facecolor=color, edgecolor=SURFACE, linewidth=0.8,
                       zorder=4)
        ax.set_xticks(range(1, longest + 1))
        ax.set_xlim(0.7, longest + 0.3)
        ax.set_ylim(0.8, 2.7)
        ax.set_title(SHORT[model], loc="left", color=INK)
    for ax in axes[1, :]:
        ax.set_xlabel("Design check (run_design call)")
    for ax in axes[:, 0]:
        ax.set_ylabel("Governing DCR")
    handles = [Line2D([], [], color=c, marker=m, markersize=5, markeredgecolor=SURFACE, linewidth=1.6, label=cid)
               for cid, (c, m) in RESIZING.items()]
    fig.legend(handles=handles, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.03))
    fig.subplots_adjust(hspace=0.4, wspace=0.08)
    _save(fig, "fig_dcr_convergence")


def main() -> None:
    runs = _runs()
    figure_ccr_chr(runs)
    figure_oracle_dcr(runs)
    figure_plan_bays(runs)
    figure_convergence(runs)


if __name__ == "__main__":
    main()
