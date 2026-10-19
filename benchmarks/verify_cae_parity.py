"""
Numerical Parity Verification: Custom FEA/Dynamic Solvers vs. Commercial CSI SAP2000/ETABS
========================================================================================

Executes numerical parity verification between the open-source symbolic solvers
(`fem3d`, `structdyn`) and commercial structural engineering suites (CSI SAP2000 v24,
CSI ETABS v21).

Evaluates:
1. Nodal displacements and rotations (axial, flexural, shear deformation).
2. Global base reactions and static equilibrium.
3. Fundamental dynamic vibration periods (T1, T2, T3) via generalized eigenvalue solver.
4. Internal member forces.

Outputs a verified Markdown and LaTeX table to `manuscript/tables/table_solver_verification.md`
proving relative discrepancies < 0.5% across all cases.

Usage
-----
python "research_paper/benchmarks/verify_cae_parity.py"
"""

import math
from pathlib import Path
from typing import Any, Dict, List

from struct_link import read_project
from struct_agent.tools.analysis import run_analysis


def calculate_parity_metrics() -> List[Dict[str, Any]]:
    """Execute FEA and dynamic analyses on benchmark fixtures and compare with CSI values."""
    benchmarks_dir = Path(__file__).resolve().parent
    repo_root = benchmarks_dir.parents[1]

    sap_fixture = repo_root / "struct_link" / "tests" / "fixtures" / "sample_frame.s2k"
    etabs_fixture = repo_root / "struct_link" / "tests" / "fixtures" / "sample_frame.e2k"
    sap_3d_frame = repo_root / "struct_link" / "references" / "sap2000" / "frame.s2k"

    rows = []

    # -------------------------------------------------------------------------
    # Benchmark 1: sample_frame.s2k (CSI SAP2000 2D Portal Frame with Shear Deformation)
    # -------------------------------------------------------------------------
    proj_sap = read_project(sap_fixture)
    run_analysis(proj_sap, analysis_case_id="DEAD", load_case_id="DEAD")
    run_analysis(proj_sap, analysis_case_id="MODAL", analysis_type="modal", num_modes=3)

    ar_dead_sap = proj_sap.analysis_results["DEAD"]
    tot_reac_z_sap = sum(
        nr.reaction.fz for nr in ar_dead_sap.node_results.values() if nr.reaction
    )
    col_reac_x_sap = abs(ar_dead_sap.node_results["1"].reaction.fx)
    col_reac_my_sap = abs(ar_dead_sap.node_results["1"].reaction.my)
    node3_uz_sap = abs(ar_dead_sap.node_results["3"].displacement.uz)
    node3_ux_sap = abs(ar_dead_sap.node_results["3"].displacement.ux)

    ar_modal_sap = proj_sap.analysis_results["MODAL"]
    modes_sap = ar_modal_sap.modal_result.modes

    # Reference CSI SAP2000 values
    benchmarks_data_sap = [
        ("Portal Frame (SAP2000)", "Total Base Shear / Vertical Reaction Fz", "kN", 140.000, tot_reac_z_sap),
        ("Portal Frame (SAP2000)", "Column Base Shear Fx (Joint 1)", "kN", 12.928, col_reac_x_sap),
        ("Portal Frame (SAP2000)", "Column Base Moment My (Joint 1)", "kN*m", 12.826, col_reac_my_sap),
        ("Portal Frame (SAP2000)", "Joint 3 Vertical Deflection Uz", "mm", 0.0525, node3_uz_sap * 1e3),
        ("Portal Frame (SAP2000)", "Joint 3 Lateral Sway Deflection Ux", "mm", 0.0086, node3_ux_sap * 1e3),
        ("Portal Frame (SAP2000)", "Fundamental Period T1 (Mode 1)", "s", 0.0931, modes_sap[0].period),
        ("Portal Frame (SAP2000)", "Fundamental Period T2 (Mode 2)", "s", 0.0558, modes_sap[1].period),
        ("Portal Frame (SAP2000)", "Fundamental Period T3 (Mode 3)", "s", 0.0504, modes_sap[2].period),
    ]

    for model_name, param, unit, ref_val, calc_val in benchmarks_data_sap:
        rel_diff = abs(calc_val - ref_val) / ref_val * 100.0
        rows.append({
            "model": model_name,
            "parameter": param,
            "unit": unit,
            "csi_ref": ref_val,
            "solver": calc_val,
            "diff_pct": rel_diff,
        })

    # -------------------------------------------------------------------------
    # Benchmark 2: sample_frame.e2k (CSI ETABS 2D Portal Frame)
    # -------------------------------------------------------------------------
    proj_etabs = read_project(etabs_fixture)
    run_analysis(proj_etabs, analysis_case_id="DEAD", load_case_id="DEAD")
    ar_dead_etabs = proj_etabs.analysis_results["DEAD"]

    tot_reac_z_etabs = sum(
        nr.reaction.fz for nr in ar_dead_etabs.node_results.values() if nr.reaction
    )
    col_axial_reac_etabs = abs(ar_dead_etabs.node_results["1"].reaction.fz)
    node3_uz_etabs = abs(ar_dead_etabs.node_results["3"].displacement.uz)

    benchmarks_data_etabs = [
        ("Portal Frame (ETABS)", "Total Vertical Base Reaction Fz", "kN", 60.000, tot_reac_z_etabs),
        ("Portal Frame (ETABS)", "Column Axial Reaction (Joint 1)", "kN", 30.000, col_axial_reac_etabs),
        ("Portal Frame (ETABS)", "Joint 3 Axial Column Shortening Uz", "mm", 0.0173, node3_uz_etabs * 1e3),
    ]

    for model_name, param, unit, ref_val, calc_val in benchmarks_data_etabs:
        rel_diff = abs(calc_val - ref_val) / ref_val * 100.0
        rows.append({
            "model": model_name,
            "parameter": param,
            "unit": unit,
            "csi_ref": ref_val,
            "solver": calc_val,
            "diff_pct": rel_diff,
        })

    # -------------------------------------------------------------------------
    # Benchmark 3: frame.s2k (CSI SAP2000 3D 3-Story Space Frame Benchmark)
    # -------------------------------------------------------------------------
    proj_3d = read_project(sap_3d_frame)
    run_analysis(proj_3d, analysis_case_id="DEAD", load_case_id="DEAD")
    run_analysis(proj_3d, analysis_case_id="LIVE", load_case_id="Live")
    run_analysis(proj_3d, analysis_case_id="MODAL", analysis_type="modal", num_modes=3)

    ar_dead_3d = proj_3d.analysis_results["DEAD"]
    ar_live_3d = proj_3d.analysis_results["LIVE"]
    ar_modal_3d = proj_3d.analysis_results["MODAL"]

    tot_dead_fz = sum(nr.reaction.fz for nr in ar_dead_3d.node_results.values() if nr.reaction)
    tot_live_fz = sum(nr.reaction.fz for nr in ar_live_3d.node_results.values() if nr.reaction)
    max_dead_uz = abs(min(nr.displacement.uz for nr in ar_dead_3d.node_results.values()))
    max_live_uz = abs(min(nr.displacement.uz for nr in ar_live_3d.node_results.values()))

    modes_3d = ar_modal_3d.modal_result.modes

    benchmarks_data_3d = [
        ("3D 3-Story Frame (SAP2000)", "Total DEAD Vertical Base Reaction Fz", "kip", 809.338, tot_dead_fz),
        ("3D 3-Story Frame (SAP2000)", "Total LIVE Vertical Base Reaction Fz", "kip", 670.965, tot_live_fz),
        ("3D 3-Story Frame (SAP2000)", "Max DEAD Vertical Deflection Uz", "in", 0.0169, max_dead_uz),
        ("3D 3-Story Frame (SAP2000)", "Max LIVE Vertical Deflection Uz", "in", 0.0150, max_live_uz),
        ("3D 3-Story Frame (SAP2000)", "Fundamental Period T1 (Mode 1)", "s", 0.4337, modes_3d[0].period),
        ("3D 3-Story Frame (SAP2000)", "Fundamental Period T2 (Mode 2)", "s", 0.4164, modes_3d[1].period),
        ("3D 3-Story Frame (SAP2000)", "Fundamental Period T3 (Mode 3)", "s", 0.3961, modes_3d[2].period),
    ]

    for model_name, param, unit, ref_val, calc_val in benchmarks_data_3d:
        rel_diff = abs(calc_val - ref_val) / ref_val * 100.0
        rows.append({
            "model": model_name,
            "parameter": param,
            "unit": unit,
            "csi_ref": ref_val,
            "solver": calc_val,
            "diff_pct": rel_diff,
        })

    return rows


def generate_tables(metrics: List[Dict[str, Any]], output_path: Path) -> None:
    """Generate publication-ready Markdown and LaTeX tables."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Markdown Table
    md_lines = [
        "# Numerical Solver Parity & CSI Commercial Verification",
        "",
        "This table documents the quantitative parity verification between the custom deterministic symbolic engines (`fem3d`, `structdyn`) and commercial finite element software (CSI SAP2000 v24 and CSI ETABS v21). All discrepancies are well below the target peer-review acceptance threshold of $< 0.50\\%$.",
        "",
        "| Structural Model | Verification Quantity | Unit | Commercial Reference (CSI) | Symbolic Engine (`fem3d`/`structdyn`) | Discrepancy (%) | Parity Status |",
        "|---|---|:---:|:---:|:---:|:---:|:---:|",
    ]

    for m in metrics:
        csi_str = f"{m['csi_ref']:.4f}" if m['csi_ref'] < 10.0 else f"{m['csi_ref']:.3f}"
        sol_str = f"{m['solver']:.4f}" if m['solver'] < 10.0 else f"{m['solver']:.3f}"
        diff_str = f"{m['diff_pct']:.3f}%"
        status = "PASSED (< 0.5%)" if m['diff_pct'] < 0.5 else "EXCEEDED"
        md_lines.append(
            f"| **{m['model']}** | {m['parameter']} | {m['unit']} | {csi_str} | {sol_str} | {diff_str} | {status} |"
        )

    # LaTeX Table
    md_lines.extend([
        "",
        "---",
        "",
        "## Formatted LaTeX Table (`table_solver_verification.tex`)",
        "",
        "```latex",
        "\\begin{table*}[t]",
        "\\centering",
        "\\caption{Numerical Parity Verification Between Custom Symbolic Solvers (\\texttt{fem3d}, \\texttt{structdyn}) and Commercial Finite Element Suites (CSI SAP2000 and ETABS).}",
        "\\label{tab:solver_verification}",
        "\\small",
        "\\begin{tabular}{llcccc}",
        "\\hline",
        "\\textbf{Benchmark Structure} & \\textbf{Physical / Dynamic Parameter} & \\textbf{Unit} & \\textbf{CSI Reference} & \\textbf{Symbolic Solvers} & \\textbf{Discrepancy (\\%)} \\\\",
        "\\hline",
    ])

    current_model = ""
    for m in metrics:
        model_display = m["model"] if m["model"] != current_model else ""
        current_model = m["model"]
        csi_str = f"{m['csi_ref']:.4f}" if m['csi_ref'] < 10.0 else f"{m['csi_ref']:.3f}"
        sol_str = f"{m['solver']:.4f}" if m['solver'] < 10.0 else f"{m['solver']:.3f}"
        diff_str = f"{m['diff_pct']:.3f}\\%"
        param_clean = m['parameter'].replace('&', '\\&').replace('_', '\\_')
        md_lines.append(
            f"{model_display} & {param_clean} & {m['unit']} & {csi_str} & {sol_str} & {diff_str} \\\\"
        )

    md_lines.extend([
        "\\hline",
        "\\end{tabular}",
        "\\end{table*}",
        "```",
        "",
    ])

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"[OK] Verification table generated: {output_path}")


def main():
    print("=" * 75)
    print(" NUMERICAL SOLVER PARITY VERIFICATION: fem3d / structdyn vs. CSI SAP2000 & ETABS")
    print("=" * 75)

    metrics = calculate_parity_metrics()
    max_discrepancy = max(m["diff_pct"] for m in metrics)

    for m in metrics:
        print(
            f"[{m['model']:<26}] {m['parameter']:<40} : "
            f"Ref={m['csi_ref']:.4f} vs Solv={m['solver']:.4f} ({m['diff_pct']:.4f}%)"
        )

    print("-" * 75)
    print(f"Maximum Relative Discrepancy Across All Tests: {max_discrepancy:.4f}%")
    assert max_discrepancy < 0.5, f"Discrepancy exceeded 0.5% threshold: {max_discrepancy}%"
    print("Verification Assertion: PASSED (< 0.5% relative discrepancy everywhere)")

    benchmarks_dir = Path(__file__).resolve().parent
    table_file = benchmarks_dir.parent / "manuscript" / "tables" / "table_solver_verification.md"
    generate_tables(metrics, table_file)


if __name__ == "__main__":
    main()
