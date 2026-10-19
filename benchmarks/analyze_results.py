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
from typing import Any, Dict, List
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

    # Fallback to _latest files only if no timestamped files were found
    if not all_runs:
        for f in results_dir.glob("*_latest.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    if "model" in data and "task_completion_rate_pct" in data:
                        data["_filename"] = f.name
                        all_runs.append(data)
            except Exception as e:
                pass

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

    # Normalize legacy results if design_cases, convergence iterations, or material economy were not stored
    for r in all_runs:
        cases_list = r.get("case_results", [])
        if "design_cases" not in r:
            des = sum(1 for c in cases_list if c.get("design_required", c.get("code_compliant") is not None))
            r["design_cases"] = des
            if des > 0:
                r["code_compliance_rate_pct"] = round((r.get("compliant_cases", 0) / des) * 100, 1)

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

        if "avg_material_economy_ratio" not in r or r["avg_material_economy_ratio"] is None:
            valid_etas = [c["material_economy_ratio"] for c in cases_list if c.get("material_economy_ratio") is not None]
            r["avg_material_economy_ratio"] = round(sum(valid_etas) / len(valid_etas), 3) if valid_etas else None

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
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")

    models = [f"{s['model']}\n({s.get('configuration', 'full')})" for s in summaries]
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

    # 2. Convergence Trajectory Plot (for cases with DCR history)
    fig, ax = plt.subplots(figsize=(7.5, 4.8), dpi=300)
    has_curves = False
    for s in summaries:
        for case in s.get("case_results", []):
            dcr_hist = case.get("dcr_history", [])
            if len(dcr_hist) > 1:
                has_curves = True
                iters = range(1, len(dcr_hist) + 1)
                ax.plot(iters, dcr_hist, marker="o", label=f"{s['model']}: {case['case_id']}")

    if has_curves:
        ax.axhline(1.0, color="red", linestyle="--", linewidth=1.5, label="Code Limit (DCR = 1.0)")
        ax.set_xlabel("Optimization / Reflection Iteration", fontsize=11, fontweight="bold")
        ax.set_ylabel("Governing Demand-Capacity Ratio (DCR)", fontsize=11, fontweight="bold")
        ax.set_title("Self-Healing Reflection Convergence Trajectories", fontsize=12, fontweight="bold")
        ax.legend(frameon=True, fontsize=8, ncol=2)
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
            eta_models.append(f"{s['model']}\n({s.get('configuration', 'full')})")
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

    return saved_plots


def print_and_save_markdown_table(summaries: List[Dict[str, Any]], results_dir: Path) -> Path:
    """Print clean Markdown table and save as unique markdown file in results/."""
    lines = [
        "=" * 130,
        " SUMMARY BENCHMARK RESULTS TABLE (FOR MANUSCRIPT SECTION 5)",
        "=" * 130,
        "| Model Name | Config | Total Cases | Completed (TCR) | Design Cases | Compliant (CCR) | Avg N_iter | Material (eta) | Avg Time (s) | Source File |",
        "|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|",
    ]
    for s in summaries:
        m = s.get("model", "N/A")
        cfg = s.get("configuration", "full")
        tot = s.get("total_cases", 0)
        suc = s.get("successful_cases", 0)
        des = s.get("design_cases", 0)
        cmp = s.get("compliant_cases", 0)
        tcr = s.get("task_completion_rate_pct", 0.0)
        ccr = s.get("code_compliance_rate_pct")
        ccr_str = f"**{ccr:.1f}%**" if ccr is not None else "N/A"
        n_iter = s.get("avg_convergence_iterations")
        n_iter_str = f"{n_iter:.1f}" if n_iter is not None else "-"
        eta = s.get("avg_material_economy_ratio")
        eta_str = f"**{eta:.3f}**" if eta is not None else "-"
        rt = s.get("avg_runtime_sec", 0.0)
        fn = s.get("_filename", "N/A")
        lines.append(f"| `{m}` | {cfg} | {tot} | {suc} (**{tcr:.1f}%**) | {des} | {cmp} ({ccr_str}) | {n_iter_str} | {eta_str} | {rt:.1f}s | `{fn}` |")
    lines.append("=" * 130)

    output_str = "\n".join(lines)
    print("\n" + output_str)

    table_file = get_unique_filepath(results_dir, "summary_table", ".md")
    with open(table_file, "w", encoding="utf-8") as f:
        f.write(output_str + "\n")
    print(f"[OK] Saved summary table to: {table_file}")
    return table_file


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
    generate_plots(summaries, plots_dir)


if __name__ == "__main__":
    main()
