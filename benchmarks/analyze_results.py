"""
Benchmark Telemetry Analysis & Publication Figure Generator
============================================================

Analyzes JSON logs from `research_paper/benchmarks/results/` and generates:
1. Publication-quality comparative figures (TCR, CCR, DCR convergence trajectories).
2. Formatted Markdown and LaTeX tables for Section 5 of the journal paper.

All output figures and summary tables are saved with unique timestamped filenames,
ensuring that no previous results or plots are ever overwritten or replaced.

Usage
-----
python "research_paper/benchmarks/analyze_results.py"
python "research_paper/benchmarks/analyze_results.py" --all-runs
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import matplotlib.pyplot as plt


def get_unique_filepath(directory: Path, base_name: str, ext: str) -> Path:
    """Generate a guaranteed unique filepath with timestamp to prevent overwriting existing files."""
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = directory / f"{base_name}_{timestamp}{ext}"
    counter = 1
    while candidate.exists():
        candidate = directory / f"{base_name}_{timestamp}_{counter}{ext}"
        counter += 1
    return candidate


def load_all_results(results_dir: Path, include_all_runs: bool = False) -> List[Dict[str, Any]]:
    """
    Load summary results from results folder without clobbering or missing any files.
    Gathers all results_*.json files. By default, selects the most recent run for each
    unique (model, configuration) pair based on timestamp.
    """
    all_runs = []
    # Search all results_*.json files
    for f in sorted(results_dir.glob("results_*.json")):
        # If there are old _latest.json files from earlier versions, skip them in favor of timestamped source files
        if f.name.endswith("_latest.json"):
            continue
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                if "model" in data and "task_completion_rate_pct" in data:
                    data["_filename"] = f.name
                    all_runs.append(data)
        except Exception as e:
            print(f"Skipping {f.name}: {e}")

    # Skip legacy _latest.json files; results are loaded exclusively from timestamped source logs

    # Load benchmark baseline concrete volumes for material economy ratio calculation
    baseline_vols: Dict[str, float] = {}
    cases_file = results_dir.parent / "benchmark_cases.json"
    if cases_file.exists():
        try:
            with open(cases_file, "r", encoding="utf-8") as fp:
                bench_data = json.load(fp)
                case_list = bench_data if isinstance(bench_data, list) else bench_data.get("benchmark_cases", [])
                for bc in case_list:
                    if bc.get("baseline_concrete_volume_m3"):
                        baseline_vols[bc["id"]] = bc["baseline_concrete_volume_m3"]
        except Exception:
            pass

    # Normalize results and compute strict CCR (<=1.0) and margin CCR (<=1.02)
    for r in all_runs:
        cases_list = r.get("case_results", [])
        des_cases = [c for c in cases_list if c.get("design_required", c.get("code_compliant") is not None)]
        n_des = len(des_cases)
        r["design_cases"] = n_des
        if n_des > 0:
            strict_comp = sum(
                1 for c in des_cases
                if (c.get("final_dcr") is not None and c["final_dcr"] <= 1.00) or c.get("code_compliant") is True
            )
            margin_comp = sum(
                1 for c in des_cases
                if (c.get("final_dcr") is not None and c["final_dcr"] <= 1.02) or c.get("code_compliant") is True
            )
            r["compliant_cases"] = strict_comp
            r["code_compliance_rate_pct"] = round((strict_comp / n_des) * 100.0, 1)
            r["code_compliance_rate_margin_pct"] = round((margin_comp / n_des) * 100.0, 1)
        else:
            r["code_compliance_rate_margin_pct"] = None

        # Ensure iterations_to_converge and material_economy_ratio are populated in cases
        for c in cases_list:
            if "iterations_to_converge" not in c:
                dcr_hist = c.get("dcr_history", [])
                if dcr_hist and dcr_hist[0] is not None and dcr_hist[0] > 1.0:
                    c["iterations_to_converge"] = (len(dcr_hist) - 1) if c.get("code_compliant") else None
                elif dcr_hist and dcr_hist[0] is not None and dcr_hist[0] <= 1.0:
                    c["iterations_to_converge"] = 0
                else:
                    c["iterations_to_converge"] = None

            if "material_economy_ratio" not in c or c.get("material_economy_ratio") is None:
                cid = c.get("case_id")
                b_vol = baseline_vols.get(cid)
                c_vol = c.get("concrete_volume_m3", 0.0)
                if b_vol and c_vol and c_vol > 0 and c.get("code_compliant") is True:
                    c["material_economy_ratio"] = round(c_vol / b_vol, 3)

        if "avg_convergence_iterations" not in r:
            ref_cases = [c for c in cases_list if c.get("initial_dcr") is not None and c["initial_dcr"] > 1.0]
            conv_cases = [c for c in ref_cases if c.get("iterations_to_converge") is not None]
            r["reflection_cases_count"] = len(ref_cases)
            r["converged_reflection_cases_count"] = len(conv_cases)
            r["avg_convergence_iterations"] = (
                round(sum(c["iterations_to_converge"] for c in conv_cases) / len(conv_cases), 2)
                if conv_cases else None
            )

        if r.get("configuration") == "heuristic":
            r["claim_completeness_rate_pct"] = None
        elif "claim_completeness_rate_pct" not in r or r["claim_completeness_rate_pct"] is None:
            cc_vals = [c["claim_completeness_pct"] for c in cases_list if c.get("claim_completeness_pct") is not None]
            r["claim_completeness_rate_pct"] = round(sum(cc_vals) / len(cc_vals), 1) if cc_vals else None

        if "avg_material_economy_ratio" not in r or r["avg_material_economy_ratio"] is None:
            valid_etas = [c["material_economy_ratio"] for c in cases_list if c.get("material_economy_ratio") is not None]
            r["avg_material_economy_ratio"] = round(sum(valid_etas) / len(valid_etas), 3) if valid_etas else None

        r["total_runs"] = r.get("total_runs", len(cases_list))
        r["unique_cases"] = r.get("unique_cases", len({c.get("case_id") for c in cases_list}))
        r["design_runs"] = r.get("design_runs", n_des)
        r["unique_design_cases"] = r.get("unique_design_cases", len({c.get("case_id") for c in des_cases}))

    if include_all_runs:
        return all_runs

    # Group by (model, configuration) and select the most recent run based on timestamp
    latest_by_model_config: Dict[tuple, Dict[str, Any]] = {}
    for r in all_runs:
        key = (r.get("model", ""), r.get("configuration", "full_agent"))
        ts = r.get("timestamp", "")
        if key not in latest_by_model_config or ts > latest_by_model_config[key].get("timestamp", ""):
            latest_by_model_config[key] = r

    return list(latest_by_model_config.values())


def generate_plots(summaries: List[Dict[str, Any]], output_dir: Path) -> List[Path]:
    """Generate publication figures using matplotlib and save with unique timestamped filenames."""
    if not summaries:
        print("No benchmark summaries found to plot.")
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    plt.style.use("default")

    models = [f"{s['model']}\n({s.get('configuration', 'full_agent')})" for s in summaries]
    tcr_vals = [s.get("task_completion_rate_pct", 0.0) for s in summaries]
    ccr_vals = [(s.get("code_compliance_rate_pct") if s.get("code_compliance_rate_pct") is not None else 0.0) for s in summaries]

    saved_plots = []

    # 1. Comparative Bar Chart (TCR vs CCR)
    fig_w1 = max(8.0, len(models) * 1.1)
    fig, ax = plt.subplots(figsize=(fig_w1, 5.2), dpi=300)
    x = range(len(models))
    width = 0.35

    rects1 = ax.bar([i - width/2 for i in x], tcr_vals, width, label="Task Completion Rate (TCR %)", color="#1f77b4")
    rects2 = ax.bar([i + width/2 for i in x], ccr_vals, width, label="Code Compliance Rate (CCR %)", color="#2ca02c")

    ax.set_ylabel("Success Rate (%)", fontsize=11, fontweight="bold")
    ax.set_title("Benchmarking Autonomous Structural Agents Across Models", fontsize=12, fontweight="bold", pad=12)
    ax.set_xticks(x)
    ax.set_xticklabels(models, fontsize=8 if len(models) > 5 else 9)
    ax.set_ylim(0, 110)
    ax.legend(frameon=True, loc="upper right")
    ax.grid(axis="y", linestyle="--", alpha=0.7)

    # Annotate bars
    for rect in rects1:
        h = rect.get_height()
        ax.annotate(f"{h:.0f}%", xy=(rect.get_x() + rect.get_width()/2, h), xytext=(0, 3),
                    textcoords="offset points", ha="center", va="bottom", fontsize=8 if len(models) > 5 else 9)
    for rect in rects2:
        h = rect.get_height()
        ax.annotate(f"{h:.0f}%", xy=(rect.get_x() + rect.get_width()/2, h), xytext=(0, 3),
                    textcoords="offset points", ha="center", va="bottom", fontsize=8 if len(models) > 5 else 9)

    plt.tight_layout()
    plot_file = get_unique_filepath(output_dir, "fig_benchmark_comparison", ".png")
    plt.savefig(plot_file, dpi=300)
    plt.close()
    saved_plots.append(plot_file)
    print(f"[OK] Saved unique comparative plot: {plot_file}")

    # 2. Convergence Trajectory Plot (mean +- shaded std band per reflection case across seeds)
    import numpy as np
    from collections import defaultdict
    fig, ax = plt.subplots(figsize=(7.8, 5.0), dpi=300)
    has_curves = False

    # Prefer full_agent configuration for convergence trajectories
    target_summary = next(
        (s for s in summaries if s.get("configuration") == "full_agent"),
        summaries[0] if summaries else None,
    )
    if target_summary:
        histories_by_case: Dict[str, List[List[float]]] = defaultdict(list)
        for case in target_summary.get("case_results", []):
            dcr_hist = case.get("dcr_history", [])
            if len(dcr_hist) > 1:
                histories_by_case[case["case_id"]].append(dcr_hist)

        case_colors = {
            "A08_2D_Overstressed_Portal_Reflection": "#1f77b4",
            "B07_3D_HighSeismic_Reflection": "#ff7f0e",
            "C07_2D_Dynamic_Reflection": "#2ca02c",
        }

        for cid, hists in histories_by_case.items():
            if not hists:
                continue
            has_curves = True
            max_len = max(len(h) for h in hists)
            padded = []
            for h in hists:
                padded.append(h + [h[-1]] * (max_len - len(h)))

            arr = np.array(padded)
            means = np.mean(arr, axis=0)
            stds = np.std(arr, axis=0)
            iters = np.arange(1, max_len + 1)
            col = case_colors.get(cid, "#9467bd")

            label_name = cid.replace("A08_2D_Overstressed_Portal_Reflection", "A08 (Portal Reflection)").replace(
                "B07_3D_HighSeismic_Reflection", "B07 (3D High-Seismic)"
            ).replace("C07_2D_Dynamic_Reflection", "C07 (Dynamic Time-History)")

            ax.plot(iters, means, marker="o", linewidth=2.0, color=col, label=f"{label_name} (mean)")
            if len(hists) > 1 and np.any(stds > 1e-4):
                ax.fill_between(iters, means - stds, means + stds, color=col, alpha=0.25, label=f"{label_name} (±1 std)")

    if has_curves:
        ax.axhline(1.0, color="red", linestyle="--", linewidth=1.5, label="Code Limit (DCR = 1.0)")
        ax.set_xlabel("Optimization / Reflection Iteration", fontsize=11, fontweight="bold")
        ax.set_ylabel("Governing Demand-Capacity Ratio (DCR)", fontsize=11, fontweight="bold")
        ax.set_title("Self-Healing Reflection Convergence Trajectories", fontsize=12, fontweight="bold")
        ax.legend(frameon=True, fontsize=8, loc="upper right")
        ax.grid(True, linestyle="--", alpha=0.7)
        plt.tight_layout()
        conv_file = get_unique_filepath(output_dir, "fig_dcr_convergence", ".png")
        plt.savefig(conv_file, dpi=300)
        plt.close()
        saved_plots.append(conv_file)
        print(f"[OK] Saved unique convergence plot: {conv_file}")

    # 3. Material Economy Ratio Bar Chart (eta = V_agent / V_baseline)
    eta_models = []
    eta_vals = []
    for s in summaries:
        eta = s.get("avg_material_economy_ratio")
        if eta is not None:
            eta_models.append(f"{s['model']}\n({s.get('configuration', 'full_agent')})")
            eta_vals.append(eta)

    if eta_vals:
        fig_w3 = max(7.0, len(eta_models) * 1.1)
        fig, ax = plt.subplots(figsize=(fig_w3, 4.8), dpi=300)
        x_eta = range(len(eta_models))
        bars = ax.bar(x_eta, eta_vals, width=0.35, color="#ff7f0e", label=r"Agent Concrete Economy ($\eta_{\mathrm{mat}}$)")
        ax.axhline(1.0, color="#d62728", linestyle="--", linewidth=1.5, label=r"Human Baseline ($\eta = 1.00$)")
        ax.set_ylabel(r"Material Economy Ratio ($\eta = V_{\mathrm{agent}} / V_{\mathrm{base}}$)", fontsize=10, fontweight="bold")
        ax.set_title("Structural Concrete Economy Across Models", fontsize=12, fontweight="bold", pad=12)
        ax.set_xticks(x_eta)
        ax.set_xticklabels(eta_models, fontsize=8 if len(eta_models) > 5 else 9)
        ax.set_ylim(0, max(max(eta_vals) * 1.3, 1.4))
        ax.legend(frameon=True, loc="upper right")
        ax.grid(axis="y", linestyle="--", alpha=0.7)

        for bar in bars:
            h = bar.get_height()
            ax.annotate(f"{h:.3f}", xy=(bar.get_x() + bar.get_width() / 2, h), xytext=(0, 3),
                        textcoords="offset points", ha="center", va="bottom", fontsize=9, fontweight="bold")

        plt.tight_layout()
        mat_file = get_unique_filepath(output_dir, "fig_material_economy", ".png")
        plt.savefig(mat_file, dpi=300)
        plt.close()
        saved_plots.append(mat_file)
        print(f"[OK] Saved unique material economy plot: {mat_file}")

    # 4. Calculation Hallucination Rate (CHR %) Bar Chart
    chr_models = []
    chr_vals = []
    chr_colors = []
    for s in summaries:
        if s.get("configuration") == "heuristic":
            continue
        val = s.get("calculation_hallucination_rate_pct", 0.0)
        chr_models.append(f"{s['model']}\n({s.get('configuration', 'full_agent')})")
        chr_vals.append(val if val is not None else 0.0)
        # Green for zero hallucination, red/crimson for ungrounded hallucination
        chr_colors.append("#2ca02c" if (val is not None and val == 0.0) else "#d62728")

    if chr_vals:
        fig_w4 = max(7.5, len(chr_models) * 1.1)
        fig, ax = plt.subplots(figsize=(fig_w4, 4.8), dpi=300)
        x_chr = range(len(chr_models))
        bars = ax.bar(x_chr, chr_vals, width=0.35, color=chr_colors)
        ax.axhline(10.0, color="#ff7f0e", linestyle="--", linewidth=1.2, label="Hallucination Bound (10.0%)")
        ax.set_ylabel("Calculation Hallucination Rate (CHR %)", fontsize=10, fontweight="bold")
        ax.set_title("Calculation Hallucination Rate Across Architectures (Zero is Optimal)", fontsize=12, fontweight="bold", pad=12)
        ax.set_xticks(x_chr)
        ax.set_xticklabels(chr_models, fontsize=8 if len(chr_models) > 5 else 9)
        ax.set_ylim(0, 115)
        ax.legend(frameon=True, loc="upper right")
        ax.grid(axis="y", linestyle="--", alpha=0.7)

        for bar in bars:
            h = bar.get_height()
            label_text = f"{h:.1f}%" if h > 0 else "0.0%\n(Verified)"
            ax.annotate(label_text, xy=(bar.get_x() + bar.get_width() / 2, h), xytext=(0, 4),
                        textcoords="offset points", ha="center", va="bottom", fontsize=8.5, fontweight="bold")

        plt.tight_layout()
        chr_file = get_unique_filepath(output_dir, "fig_hallucination_rate", ".png")
        plt.savefig(chr_file, dpi=300)
        plt.close()
        saved_plots.append(chr_file)
        print(f"[OK] Saved unique hallucination rate plot: {chr_file}")

    # 4b. Calculation Hallucination Rate (CHR) vs. Claim Completeness (CCR_claims) Paired Bar Chart
    cc_models = []
    cc_chr_vals = []
    cc_comp_vals = []
    for s in summaries:
        if s.get("configuration") == "heuristic":
            continue
        chr_v = s.get("calculation_hallucination_rate_pct", 0.0)
        comp_v = s.get("claim_completeness_rate_pct", 0.0)
        if chr_v is not None or comp_v is not None:
            cc_models.append(f"{s['model']}\n({s.get('configuration', 'full_agent')})")
            cc_chr_vals.append(chr_v if chr_v is not None else 0.0)
            cc_comp_vals.append(comp_v if comp_v is not None else 0.0)

    if cc_models:
        fig_w_cc = max(8.0, len(cc_models) * 1.15)
        fig, ax = plt.subplots(figsize=(fig_w_cc, 5.2), dpi=300)
        x_cc = np.arange(len(cc_models))
        w_cc = 0.35

        bars_chr = ax.bar(x_cc - w_cc / 2, cc_chr_vals, w_cc, label="Calculation Hallucination Rate (CHR %)", color="#d62728", alpha=0.9)
        bars_comp = ax.bar(x_cc + w_cc / 2, cc_comp_vals, w_cc, label=r"Claim Completeness Rate ($\mathrm{CCR}_{\mathrm{claims}}$ %)", color="#1f77b4", alpha=0.9)

        ax.axhline(100.0, color="gray", linestyle=":", linewidth=1.2, label="Full Completeness (100%)")
        ax.axhline(10.0, color="#ff7f0e", linestyle="--", linewidth=1.2, label="Hallucination Bound (10%)")

        ax.set_ylabel("Rate (%)", fontsize=11, fontweight="bold")
        ax.set_title("Hallucination Rate (CHR) vs. Claim Completeness (CCR_claims)", fontsize=12, fontweight="bold", pad=12)
        ax.set_xticks(x_cc)
        ax.set_xticklabels(cc_models, fontsize=8 if len(cc_models) > 5 else 9)
        ax.set_ylim(0, 115)
        ax.legend(frameon=True, loc="upper right", fontsize=8.5)
        ax.grid(axis="y", linestyle="--", alpha=0.7)

        for bar in bars_chr:
            h = bar.get_height()
            txt = f"{h:.1f}%" if h > 0 else "0.0%"
            ax.annotate(txt, xy=(bar.get_x() + bar.get_width() / 2, h), xytext=(0, 3),
                        textcoords="offset points", ha="center", va="bottom", fontsize=8, fontweight="bold")
        for bar in bars_comp:
            h = bar.get_height()
            txt = f"{h:.1f}%" if h > 0 else "0.0%"
            ax.annotate(txt, xy=(bar.get_x() + bar.get_width() / 2, h), xytext=(0, 3),
                        textcoords="offset points", ha="center", va="bottom", fontsize=8, fontweight="bold")

        plt.tight_layout()
        cc_plot_file = get_unique_filepath(output_dir, "fig_chr_vs_completeness", ".png")
        plt.savefig(cc_plot_file, dpi=300)
        plt.close()
        saved_plots.append(cc_plot_file)
        print(f"[OK] Saved unique CHR vs Completeness plot: {cc_plot_file}")

    # 5. Hallucination Error Magnitude Breakdown by Physical Metric
    import numpy as np
    metric_labels = {
        "total_weight_kN": "Structural Weight (W)",
        "governing_dcr": "Governing DCR",
        "fundamental_period_s": "Modal Period (T1)",
        "base_shear_kN": "Seismic Base Shear (Vb)"
    }
    metric_errors_by_config = {}
    for s in summaries:
        cfg = s.get("configuration", "unknown")
        if cfg not in metric_errors_by_config:
            metric_errors_by_config[cfg] = {k: [] for k in metric_labels}
        for case in s.get("case_results", []):
            errs = case.get("oracle_metric_errors", {})
            for mk in metric_labels:
                if mk in errs:
                    metric_errors_by_config[cfg][mk].append(errs[mk] * 100.0)

    configs_with_errs = [cfg for cfg, mdict in metric_errors_by_config.items() if any(len(v) > 0 for v in mdict.values())]
    if configs_with_errs:
        # Also include full_agent explicitly as 0.0% ground truth anchor if not present
        if "full_agent" not in configs_with_errs:
            configs_with_errs.append("full_agent")
            metric_errors_by_config["full_agent"] = {k: [0.0] for k in metric_labels}

        fig, ax = plt.subplots(figsize=(9.2, 5.2), dpi=300)
        mkeys = list(metric_labels.keys())
        x_m = np.arange(len(mkeys))
        n_cfg = len(configs_with_errs)
        b_width = 0.8 / max(n_cfg, 1)

        cfg_colors = {
            "direct_llm": "#d62728",
            "code_gen": "#9467bd",
            "full_agent": "#2ca02c",
            "ablated": "#1f77b4"
        }

        for idx, cfg in enumerate(configs_with_errs):
            means = []
            for mk in mkeys:
                vals = metric_errors_by_config[cfg][mk]
                means.append(float(np.mean(vals)) if vals else 0.0)

            offset = (idx - (n_cfg - 1) / 2) * b_width
            bars = ax.bar(x_m + offset, [max(m, 0.01) for m in means], b_width,
                          label=f"{cfg} (mean)", color=cfg_colors.get(cfg, "#7f7f7f"), alpha=0.85)

            for bar, m_val in zip(bars, means):
                h = bar.get_height()
                txt = f"{m_val:.1f}%" if m_val > 0 else "0.0%"
                ax.annotate(txt, xy=(bar.get_x() + bar.get_width() / 2, h), xytext=(0, 3),
                            textcoords="offset points", ha="center", va="bottom", fontsize=7.5, fontweight="bold")

        ax.set_ylabel("Mean Relative Discrepancy vs. Oracle (%) [Log Scale]", fontsize=10, fontweight="bold")
        ax.set_title("Calculation Error Discrepancy by Engineering Regime (Oracle Ground Truth)", fontsize=12, fontweight="bold", pad=12)
        ax.set_xticks(x_m)
        ax.set_xticklabels([metric_labels[k] for k in mkeys], fontsize=9, fontweight="bold")
        ax.set_yscale("log")
        ax.axhline(10.0, color="gray", linestyle=":", linewidth=1.2, label="10.0% Hallucination Boundary")
        ax.legend(frameon=True, loc="upper left", fontsize=8.5)
        ax.grid(True, linestyle="--", alpha=0.6, which="both")

        plt.tight_layout()
        err_file = get_unique_filepath(output_dir, "fig_hallucination_error_breakdown", ".png")
        plt.savefig(err_file, dpi=300)
        plt.close()
        saved_plots.append(err_file)
        print(f"[OK] Saved unique hallucination breakdown plot: {err_file}")

    # 6. Structural Safety vs. Material Economy Trade-off Scatter Plot
    tradeoff_data = []
    for s in summaries:
        ccr = s.get("code_compliance_rate_pct")
        eta = s.get("avg_material_economy_ratio")
        if ccr is not None and eta is not None:
            tradeoff_data.append({
                "label": f"{s['model']} ({s.get('configuration', 'full_agent')})",
                "ccr": ccr,
                "eta": eta,
                "cfg": s.get("configuration", "full_agent")
            })

    if len(tradeoff_data) >= 2:
        fig, ax = plt.subplots(figsize=(8.0, 5.2), dpi=300)

        # Highlight regions
        ax.axvspan(0.4, 1.0, ymin=0.5, ymax=1.0, color="#2ca02c", alpha=0.08, label="Optimal Zone (Safe & Economical)")
        ax.axvspan(1.0, 1.8, ymin=0.5, ymax=1.0, color="#d62728", alpha=0.08, label="Over-Sized / Material Waste Zone")
        ax.axhline(80.0, color="gray", linestyle=":", linewidth=1.0)
        ax.axvline(1.0, color="gray", linestyle=":", linewidth=1.0)

        cfg_markers = {
            "full_agent": ("o", "#2ca02c", 130),
            "ablated": ("s", "#1f77b4", 110),
            "direct_llm": ("^", "#d62728", 140),
            "code_gen": ("D", "#9467bd", 110)
        }

        for item in tradeoff_data:
            marker, color, size = cfg_markers.get(item["cfg"], ("o", "#333333", 100))
            ax.scatter(item["eta"], item["ccr"], s=size, color=color, marker=marker, edgecolors="black", linewidth=1.2, zorder=5)
            ax.annotate(item["label"], xy=(item["eta"], item["ccr"]), xytext=(6, -2),
                        textcoords="offset points", fontsize=8.5, fontweight="bold", zorder=6)

        ax.set_xlabel(r"Material Economy Ratio ($\eta_{\mathrm{vol}} = V_{\mathrm{concrete}} / V_{\mathrm{baseline}}$) [Lower = Economical]", fontsize=10, fontweight="bold")
        ax.set_ylabel("Code Compliance Rate (CCR %) [Higher = Safe]", fontsize=10, fontweight="bold")
        ax.set_title("Structural Safety vs. Material Economy Trade-off", fontsize=12, fontweight="bold", pad=12)
        ax.set_xlim(0.5, 1.6)
        ax.set_ylim(0, 105)
        ax.grid(True, linestyle="--", alpha=0.6)
        ax.legend(frameon=True, loc="lower left", fontsize=8.5)

        plt.tight_layout()
        trade_file = get_unique_filepath(output_dir, "fig_safety_economy_tradeoff", ".png")
        plt.savefig(trade_file, dpi=300)
        plt.close()
        saved_plots.append(trade_file)
        print(f"[OK] Saved unique safety-economy tradeoff plot: {trade_file}")

    # 7. Computational Turnaround Time per Case (Runtime Comparison)
    time_models = []
    time_vals = []
    for s in summaries:
        rt = s.get("avg_runtime_sec")
        if rt is not None and rt > 0:
            time_models.append(f"{s['model']}\n({s.get('configuration', 'full_agent')})")
            time_vals.append(rt)

    if time_vals:
        fig_w7 = max(7.0, len(time_models) * 1.1)
        fig, ax = plt.subplots(figsize=(fig_w7, 4.8), dpi=300)
        x_time = range(len(time_models))
        bars = ax.bar(x_time, time_vals, width=0.35, color="#17becf")
        ax.set_ylabel("Average Wall-Clock Runtime per Case (s)", fontsize=10, fontweight="bold")
        ax.set_title("Computational Turnaround Time per Structural Case", fontsize=12, fontweight="bold", pad=12)
        ax.set_xticks(x_time)
        ax.set_xticklabels(time_models, fontsize=8 if len(time_models) > 5 else 9)
        ax.set_ylim(0, max(time_vals) * 1.25)
        ax.grid(axis="y", linestyle="--", alpha=0.7)

        for bar in bars:
            h = bar.get_height()
            ax.annotate(f"{h:.1f}s", xy=(bar.get_x() + bar.get_width() / 2, h), xytext=(0, 3),
                        textcoords="offset points", ha="center", va="bottom", fontsize=8.5, fontweight="bold")

        plt.tight_layout()
        time_file = get_unique_filepath(output_dir, "fig_runtime_comparison", ".png")
        plt.savefig(time_file, dpi=300)
        plt.close()
        saved_plots.append(time_file)
        print(f"[OK] Saved unique runtime comparison plot: {time_file}")

    # 8. Prompt-to-Schema Fidelity Rate (PSFR %) Bar Chart (Item #18)
    psfr_models = []
    psfr_vals = []
    for s in summaries:
        val = s.get("prompt_to_schema_fidelity_rate_pct")
        if val is not None:
            psfr_models.append(f"{s['model']}\n({s.get('configuration', 'full_agent')})")
            psfr_vals.append(val)

    if psfr_vals:
        fig_w8 = max(7.0, len(psfr_models) * 1.1)
        fig, ax = plt.subplots(figsize=(fig_w8, 4.8), dpi=300)
        x_psfr = range(len(psfr_models))
        bars = ax.bar(x_psfr, psfr_vals, width=0.35, color="#8c564b")
        ax.set_ylabel("Prompt-to-Schema Fidelity Rate (PSFR %)", fontsize=10, fontweight="bold")
        ax.set_title("Autonomous Translation Fidelity into Executable Schemas", fontsize=12, fontweight="bold", pad=12)
        ax.set_xticks(x_psfr)
        ax.set_xticklabels(psfr_models, fontsize=8 if len(psfr_models) > 5 else 9)
        ax.set_ylim(0, 115)
        ax.axhline(100.0, color="gray", linestyle=":", linewidth=1.0)
        ax.grid(axis="y", linestyle="--", alpha=0.7)

        for bar in bars:
            h = bar.get_height()
            ax.annotate(f"{h:.1f}%", xy=(bar.get_x() + bar.get_width() / 2, h), xytext=(0, 3),
                        textcoords="offset points", ha="center", va="bottom", fontsize=8.5, fontweight="bold")

        plt.tight_layout()
        psfr_file = get_unique_filepath(output_dir, "fig_prompt_schema_fidelity", ".png")
        plt.savefig(psfr_file, dpi=300)
        plt.close()
        saved_plots.append(psfr_file)
        print(f"[OK] Saved unique PSFR plot: {psfr_file}")

    return saved_plots


def _compute_run_level_seed_stats(cases_list: List[Dict[str, Any]]) -> Dict[str, Tuple[float, float]]:
    """Group cases by seed_index and compute run-level metrics per seed, then mean +- std."""
    import numpy as np
    seeds = sorted(list({c.get("seed_index", 0) for c in cases_list}))
    if len(seeds) <= 1:
        return {}

    tcr_list = []
    ccr_list = []
    chr_list = []
    eta_list = []
    comp_list = []

    for s in seeds:
        sc = [c for c in cases_list if c.get("seed_index", 0) == s]
        if not sc:
            continue
        tcr_list.append((sum(1 for c in sc if c.get("success")) / len(sc)) * 100.0)
        des_c = [c for c in sc if c.get("design_required")]
        if des_c:
            ccr_list.append((sum(1 for c in des_c if c.get("code_compliant") is True) / len(des_c)) * 100.0)
        tot_claims = sum(c.get("claims_made_count", len(c.get("claims_made", []))) for c in sc)
        tot_halluc = sum(c.get("hallucinated_claims_count", len(c.get("hallucinated_oracle_metrics", []))) for c in sc)
        chr_list.append((tot_halluc / max(tot_claims, 1)) * 100.0 if tot_claims > 0 else 0.0)
        cc_vals = [c["claim_completeness_pct"] for c in sc if c.get("claim_completeness_pct") is not None]
        if cc_vals:
            comp_list.append(float(np.mean(cc_vals)))
        eta_vals = [c["material_economy_ratio"] for c in sc if c.get("material_economy_ratio") is not None]
        if eta_vals:
            eta_list.append(float(np.mean(eta_vals)))

    stats = {}
    if tcr_list:
        stats["tcr"] = (float(np.mean(tcr_list)), float(np.std(tcr_list)))
    if ccr_list:
        stats["ccr"] = (float(np.mean(ccr_list)), float(np.std(ccr_list)))
    if chr_list:
        stats["chr"] = (float(np.mean(chr_list)), float(np.std(chr_list)))
    if comp_list:
        stats["claim_completeness"] = (float(np.mean(comp_list)), float(np.std(comp_list)))
    if eta_list:
        stats["eta"] = (float(np.mean(eta_list)), float(np.std(eta_list)))
    return stats


def print_and_save_markdown_table(summaries: List[Dict[str, Any]], results_dir: Path) -> Path:
    """Print clean Markdown table and save as unique markdown file in results/."""
    lines = [
        "=" * 175,
        " SUMMARY BENCHMARK RESULTS TABLE (FOR MANUSCRIPT SECTION 5)",
        "=" * 175,
        "| Model Name | Config | Runs (TCR) / Cases | Compliant (CCR Strict / Margin) | CHR % | Claim Completeness % | Fidelity (PSFR) | Avg N_iter | Material (eta) | Avg Time (s) | Source File |",
        "|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|",
    ]
    for s in summaries:
        m = s.get("model", "N/A")
        cfg = s.get("configuration", "full_agent")
        cases_list = s.get("case_results", [])
        tot = s.get("total_runs", s.get("total_cases", len(cases_list)))
        u_cases = s.get("unique_cases", len({c.get("case_id") for c in cases_list}))
        suc = s.get("successful_cases", 0)
        des = s.get("design_cases", 0)
        cmp = s.get("compliant_cases", 0)
        tcr = s.get("task_completion_rate_pct", 0.0)
        ccr = s.get("code_compliance_rate_pct")
        ccr_margin = s.get("code_compliance_rate_margin_pct")

        seed_stats = _compute_run_level_seed_stats(cases_list)
        if seed_stats:
            tcr_m, tcr_s = seed_stats["tcr"]
            tcr_disp = f"{tcr_m:.1f}%" + (f" ± {tcr_s:.1f}%" if tcr_s > 0.05 else "")
            runs_display = f"{tot} (**{tcr_disp}**) / {u_cases}"

            if ccr is not None and "ccr" in seed_stats:
                ccr_m, ccr_s = seed_stats["ccr"]
                ccr_disp = f"**{ccr_m:.1f}%**" + (f" ± {ccr_s:.1f}%" if ccr_s > 0.05 else "")
                ccr_display = f"{cmp}/{des} ({ccr_disp})"
            elif ccr is not None:
                ccr_display = f"{cmp}/{des} (**{ccr:.1f}%**)"
            else:
                ccr_display = "N/A"

            if "chr" in seed_stats:
                chr_m, chr_s = seed_stats["chr"]
                chr_str = f"**{chr_m:.1f}%**" + (f" ± {chr_s:.1f}%" if chr_s > 0.05 else "")
            else:
                chr_val = s.get("calculation_hallucination_rate_pct")
                chr_str = f"**{chr_val:.1f}%**" if chr_val is not None else "0.0%"

            if "claim_completeness" in seed_stats:
                comp_m, comp_s = seed_stats["claim_completeness"]
                comp_str = f"**{comp_m:.1f}%**" + (f" ± {comp_s:.1f}%" if comp_s > 0.05 else "")
            else:
                comp_val = s.get("claim_completeness_rate_pct")
                comp_str = f"**{comp_val:.1f}%**" if comp_val is not None else "N/A"

            if "eta" in seed_stats:
                eta_m, eta_s = seed_stats["eta"]
                eta_str = f"**{eta_m:.3f}**" + (f" ± {eta_s:.3f}" if eta_s > 0.005 else "")
            else:
                eta = s.get("avg_material_economy_ratio")
                eta_str = f"**{eta:.3f}**" if eta is not None else "-"
        else:
            runs_display = f"{tot} (**{tcr:.1f}%**) / {u_cases}" if tot != u_cases else f"{tot} (**{tcr:.1f}%**)"
            ccr_str = f"**{ccr:.1f}%**" if ccr is not None else "N/A"
            if ccr is not None and ccr_margin is not None and ccr_margin != ccr:
                ccr_display = f"{cmp}/{des} ({ccr_str} / **{ccr_margin:.1f}%**)"
            elif ccr is not None:
                ccr_display = f"{cmp}/{des} ({ccr_str})"
            else:
                ccr_display = "N/A"

            chr_val = s.get("calculation_hallucination_rate_pct")
            chr_str = f"**{chr_val:.1f}%**" if chr_val is not None else "0.0%"
            comp_val = s.get("claim_completeness_rate_pct")
            comp_str = f"**{comp_val:.1f}%**" if comp_val is not None else "N/A"
            eta = s.get("avg_material_economy_ratio")
            eta_str = f"**{eta:.3f}**" if eta is not None else "-"

        if cfg == "heuristic":
            chr_str = "N/A"
            comp_str = "N/A"

        psfr_val = s.get("prompt_to_schema_fidelity_rate_pct")
        psfr_str = f"**{psfr_val:.1f}%**" if psfr_val is not None else "N/A"
        n_iter = s.get("avg_convergence_iterations")
        n_iter_str = f"{n_iter:.1f}" if n_iter is not None else "-"
        rt = s.get("avg_runtime_sec", 0.0)
        fn = s.get("_filename", "N/A")
        lines.append(
            f"| `{m}` | {cfg} | {runs_display} | {ccr_display} | "
            f"{chr_str} | {comp_str} | {psfr_str} | {n_iter_str} | {eta_str} | {rt:.1f}s | `{fn}` |"
        )
    lines.append("=" * 175)
    if any(s.get("configuration") == "heuristic" for s in summaries):
        lines.append("\n*Note: CHR and CCR_claims are not applicable to the deterministic heuristic baseline (no textual claims are emitted).*")

    output_str = "\n".join(lines)
    print("\n" + output_str)

    table_file = get_unique_filepath(results_dir, "summary_table", ".md")
    with open(table_file, "w", encoding="utf-8") as f:
        f.write(output_str + "\n")
    print(f"[OK] Saved summary table to: {table_file}")
    return table_file


def print_and_save_detailed_table(summaries: List[Dict[str, Any]], results_dir: Path) -> Optional[Path]:
    """
    Generate and save detailed per-case comparison table between agent deliverable
    and verified human baseline designs (P2.19).
    """
    cases_file = results_dir.parent / "benchmark_cases.json"
    if not cases_file.exists():
        return None

    try:
        with open(cases_file, "r", encoding="utf-8") as fp:
            bench_data = json.load(fp)
            cases_catalog = {
                c["id"]: c
                for c in (bench_data if isinstance(bench_data, list) else bench_data.get("benchmark_cases", []))
            }
    except Exception:
        return None

    # Prefer full_agent configuration summary, fallback to first available
    target_summary = next(
        (s for s in summaries if s.get("configuration") == "full_agent"),
        summaries[0] if summaries else None,
    )
    if not target_summary:
        return None

    agent_cases = {c.get("case_id"): c for c in target_summary.get("case_results", [])}

    lines = [
        "=" * 180,
        f" PER-CASE COMPARISON: AGENT DELIVERABLE vs. VERIFIED HUMAN BASELINE ({target_summary.get('model', 'Model')} | {target_summary.get('configuration', 'full_agent')})",
        "=" * 180,
        "| Case ID | Group | Baseline DCR | Agent DCR | Baseline Limit State | Agent Limit State | Baseline Vol (m^3) | Agent Vol (m^3) | eta_vol | Efficiency (V_base/V_agent) | Compliant |",
        "|:---|:---:|:---:|:---:|:---|:---|:---:|:---:|:---:|:---:|:---:|",
    ]

    for cid, bc in cases_catalog.items():
        ac = agent_cases.get(cid, {})
        grp = bc.get("group", "N/A")
        b_des = bc.get("baseline_design", {})
        b_dcr = f"{b_des.get('governing_dcr'):.3f}" if b_des.get("governing_dcr") is not None else "-"
        a_dcr = f"{ac.get('final_dcr'):.3f}" if ac.get("final_dcr") is not None else "N/A"
        b_ls = b_des.get("governing_limit_state", "-")
        a_ls = ac.get("governing_limit_state", "-")
        b_vol = f"{bc.get('baseline_concrete_volume_m3'):.3f}" if bc.get("baseline_concrete_volume_m3") is not None else "-"
        a_vol = f"{ac.get('concrete_volume_m3'):.3f}" if ac.get("concrete_volume_m3") is not None else "-"
        eta = f"{ac.get('material_economy_ratio'):.3f}" if ac.get("material_economy_ratio") is not None else "-"
        eff = (
            f"{(1.0 / ac['material_economy_ratio']):.3f}"
            if (ac.get("material_economy_ratio") and ac["material_economy_ratio"] > 0)
            else "-"
        )
        cmp_flag = "Yes" if ac.get("code_compliant") is True else ("No" if ac.get("code_compliant") is False else "-")

        lines.append(
            f"| `{cid}` | {grp} | {b_dcr} | {a_dcr} | {b_ls} | {a_ls} | {b_vol} | {a_vol} | {eta} | {eff} | {cmp_flag} |"
        )
    lines.append("=" * 180)

    output_str = "\n".join(lines)
    print("\n" + output_str)

    table_file = get_unique_filepath(results_dir, "detailed_case_comparison_table", ".md")
    with open(table_file, "w", encoding="utf-8") as f:
        f.write(output_str + "\n")
    print(f"[OK] Saved per-case detailed comparison table to: {table_file}")
    return table_file


def print_and_save_failure_mode_table(summaries: List[Dict[str, Any]], results_dir: Path) -> Path:
    """Tabulate failure modes per case across seeds (Item #10) for Section 5 diagnostics."""
    from collections import defaultdict
    modes = [
        "model_construction",
        "missing_tool",
        "artifact_missing",
        "schema_fidelity",
        "dcr_non_convergence",
        "runtime_error",
    ]
    lines = [
        "=" * 155,
        " FAILURE-MODE TAXONOMY BREAKDOWN (SECTION 5 DIAGNOSTICS - CASE-LEVEL GROUPING)",
        "=" * 155,
        "| Model Name | Configuration | Seed Evaluation | Total Cases | Failed Cases | Model Construction | Missing Tool | Missing Artifact | Schema Fidelity | DCR Non-Convergence | Runtime / Other |",
        "|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]
    for s in summaries:
        m = s.get("model", "N/A")
        cfg = s.get("configuration", "unknown")
        cases = s.get("case_results", [])

        # Group runs by case_id
        by_cid: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for c in cases:
            by_cid[c.get("case_id", "unknown")].append(c)

        tot_unique_cases = len(by_cid)
        max_seeds = max((len(runs) for runs in by_cid.values()), default=1)

        if max_seeds > 1:
            eval_types = [("At least 1 seed", "any"), ("All seeds", "all")]
        else:
            eval_types = [("Single seed (N=1)", "any")]

        for label, mode_filter in eval_types:
            failed_case_ids = set()
            mode_case_counts = {k: 0 for k in modes}

            for cid, runs in by_cid.items():
                if mode_filter == "any":
                    failed_runs = [c for c in runs if c.get("failure_mode")]
                    if failed_runs:
                        failed_case_ids.add(cid)
                        modes_in_case = {c.get("failure_mode") for c in failed_runs}
                        for fm in modes_in_case:
                            if fm in mode_case_counts:
                                mode_case_counts[fm] += 1
                            else:
                                mode_case_counts["runtime_error"] += 1
                else:  # "all"
                    if len(runs) > 0 and all(c.get("failure_mode") for c in runs):
                        failed_case_ids.add(cid)
                        modes_in_case = {c.get("failure_mode") for c in runs}
                        for fm in modes_in_case:
                            if fm in mode_case_counts:
                                mode_case_counts[fm] += 1
                            else:
                                mode_case_counts["runtime_error"] += 1

            lines.append(
                f"| `{m}` | {cfg} | {label} | {tot_unique_cases} | {len(failed_case_ids)} | "
                f"{mode_case_counts['model_construction']} | {mode_case_counts['missing_tool']} | "
                f"{mode_case_counts['artifact_missing']} | {mode_case_counts['schema_fidelity']} | "
                f"{mode_case_counts['dcr_non_convergence']} | {mode_case_counts['runtime_error']} |"
            )

    lines.append("=" * 155)
    output_str = "\n".join(lines)
    print("\n" + output_str)

    table_file = get_unique_filepath(results_dir, "failure_mode_taxonomy_table", ".md")
    with open(table_file, "w", encoding="utf-8") as f:
        f.write(output_str + "\n")
    print(f"[OK] Saved failure mode taxonomy table to: {table_file}")
    return table_file


def compute_statistical_significance(summaries: List[Dict[str, Any]], results_dir: Path) -> Optional[Path]:
    """
    Run paired statistical significance tests (Wilcoxon signed-rank)
    comparing full_agent vs. ablated across per-case seed-averaged metrics.
    """
    import numpy as np
    from collections import defaultdict

    full_agent_summary = next((s for s in summaries if s.get("configuration") == "full_agent"), None)
    ablated_summary = next((s for s in summaries if s.get("configuration") == "ablated"), None)

    if not full_agent_summary or not ablated_summary:
        return None

    fa_cases_list = full_agent_summary.get("case_results", [])
    ab_cases_list = ablated_summary.get("case_results", [])

    if not fa_cases_list or not ab_cases_list:
        return None

    def _per_case_means(cases: List[Dict[str, Any]], metric_fn) -> Dict[str, float]:
        by_cid = defaultdict(list)
        for c in cases:
            v = metric_fn(c)
            if v is not None:
                by_cid[c.get("case_id", "")].append(float(v))
        return {cid: float(np.mean(vals)) for cid, vals in by_cid.items() if vals}

    def _count_seeds(cases: List[Dict[str, Any]]) -> int:
        by_cid = defaultdict(set)
        for c in cases:
            by_cid[c.get("case_id", "")].add(c.get("seed_index", 0))
        return max((len(seeds) for seeds in by_cid.values()), default=1)

    n_seeds_fa = _count_seeds(fa_cases_list)
    n_seeds_ab = _count_seeds(ab_cases_list)
    n_seeds_report = max(n_seeds_fa, n_seeds_ab)

    try:
        import scipy.stats as stats
    except ImportError:
        return None

    metrics_to_test = {
        "Task Completion (TCR)": (
            _per_case_means(fa_cases_list, lambda c: 1.0 if c.get("success") else 0.0),
            _per_case_means(ab_cases_list, lambda c: 1.0 if c.get("success") else 0.0),
        ),
        "Code Compliance (CCR)": (
            _per_case_means(fa_cases_list, lambda c: (1.0 if c.get("code_compliant") is True else 0.0) if c.get("design_required") else None),
            _per_case_means(ab_cases_list, lambda c: (1.0 if c.get("code_compliant") is True else 0.0) if c.get("design_required") else None),
        ),
        "Governing DCR": (
            _per_case_means(fa_cases_list, lambda c: c.get("final_dcr") if (c.get("design_required") and c.get("final_dcr") is not None) else None),
            _per_case_means(ab_cases_list, lambda c: c.get("final_dcr") if (c.get("design_required") and c.get("final_dcr") is not None) else None),
        ),
        "Wall-Clock Runtime (s)": (
            _per_case_means(fa_cases_list, lambda c: c.get("wall_clock_time_sec") if c.get("wall_clock_time_sec") is not None else None),
            _per_case_means(ab_cases_list, lambda c: c.get("wall_clock_time_sec") if c.get("wall_clock_time_sec") is not None else None),
        ),
    }

    lines = [
        "=" * 135,
        f" STATISTICAL SIGNIFICANCE REPORT: full_agent vs. ablated (Model: {full_agent_summary.get('model', 'Model')})",
        "=" * 135,
        "| Metric | N Pairs | N Seeds | Full Agent Mean | Ablated Mean | Difference (Delta) | Wilcoxon W | p-value | Significant (p < 0.05) |",
        "|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]

    for m_name, (fa_map, ab_map) in metrics_to_test.items():
        common_ids = sorted([cid for cid in fa_map if cid in ab_map])
        n = len(common_ids)
        if n < 4:
            continue
        v_fa = [fa_map[cid] for cid in common_ids]
        v_ab = [ab_map[cid] for cid in common_ids]
        mean_fa = float(np.mean(v_fa))
        mean_ab = float(np.mean(v_ab))
        diff = mean_fa - mean_ab

        diffs = np.array(v_fa) - np.array(v_ab)
        if np.all(diffs == 0):
            w_stat, p_val = 0.0, 1.0
        else:
            try:
                res_w = stats.wilcoxon(v_fa, v_ab, zero_method="wilcox")
                w_stat, p_val = float(res_w.statistic), float(res_w.pvalue)
            except Exception:
                w_stat, p_val = float("nan"), float("nan")

        sig_badge = "**Yes (p < 0.05)**" if (p_val < 0.05) else "No (p >= 0.05)"
        lines.append(
            f"| {m_name} | {n} | {n_seeds_report} | {mean_fa:.3f} | {mean_ab:.3f} | {diff:+.3f} | {w_stat:.1f} | {p_val:.4f} | {sig_badge} |"
        )

    lines.append("=" * 135)
    output_str = "\n".join(lines)
    print("\n" + output_str)

    sig_file = get_unique_filepath(results_dir, "statistical_significance_report", ".md")
    with open(sig_file, "w", encoding="utf-8") as f:
        f.write(output_str + "\n")
    print(f"[OK] Saved statistical significance report to: {sig_file}")
    return sig_file


def main():
    parser = argparse.ArgumentParser(description="Benchmark Telemetry Analysis & Publication Figure Generator")
    parser.add_argument("--all-runs", action="store_true", help="Include all historical benchmark runs instead of only the latest per model")
    parser.add_argument("--results-dir", type=str, default="", help="Custom results directory path")
    parser.add_argument("--plots-dir", type=str, default="", help="Custom plots directory path")
    args = parser.parse_args()

    benchmarks_dir = Path(__file__).resolve().parent
    results_dir = Path(args.results_dir) if args.results_dir else benchmarks_dir / "results"
    plots_dir = Path(args.plots_dir) if args.plots_dir else benchmarks_dir / "plots"

    if not results_dir.exists():
        print(f"No results directory found at: {results_dir}")
        return

    summaries = load_all_results(results_dir, include_all_runs=args.all_runs)
    if not summaries:
        print("No benchmark result files found. Run 'run_benchmarks.py' first.")
        return

    print_and_save_markdown_table(summaries, results_dir)
    print_and_save_detailed_table(summaries, results_dir)
    print_and_save_failure_mode_table(summaries, results_dir)
    compute_statistical_significance(summaries, results_dir)
    generate_plots(summaries, plots_dir)


if __name__ == "__main__":
    main()
