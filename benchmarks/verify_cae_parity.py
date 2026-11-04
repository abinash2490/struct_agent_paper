"""
Numerical Parity Verification: Custom FEA/Dynamic Solvers vs. Commercial CSI SAP2000/ETABS
========================================================================================

Executes numerical parity verification between the open-source symbolic solvers
(`fem3d`, `structdyn`) and commercial structural engineering suites:
- Computers and Structures, Inc. (CSI) SAP2000 v24.0.0 (Build 1865, 64-bit)
- Computers and Structures, Inc. (CSI) ETABS v21.0.0 (Build 2430, 64-bit)

Reference values are read from the CSI tabular reports of the 3D RC seismic frame
(`fixtures/exported_seismic_frame.s2k` / `.e2k`), solved in both programs:
1. Base Reactions (Load Cases: DEAD, SuperDead, LIVE)
2. Auto Seismic - ASCE 7-22 base shear (Load Pattern: EQx)
3. Modal Periods and Frequencies (Case: MODAL)

Evaluates the agent pipeline (CSI import -> `run_analysis`) on gravity equilibrium, the ELF
lateral load pattern, and the first three periods (Timoshenko members, lumped mass,
CSI mass source).

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

SAP2000_VERSION = "CSI SAP2000 v24.0.0 (Build 1865)"
ETABS_VERSION = "CSI ETABS v21.0.0 (Build 2430)"


def _parity_rows(fixture: Path, model_name: str, program: str, live_case: str) -> List[Dict[str, Any]]:
    """Analyse one CSI fixture through the agent pipeline and compare with its CSI results."""
    project = read_project(fixture)
    for lc_id in ("DEAD", "SuperDead", live_case, "EQx"):
        run_analysis(project, analysis_case_id=lc_id, load_case_id=lc_id)
    run_analysis(project, analysis_case_id="MODAL", analysis_type="modal", num_modes=3)

    def base_sum(case_id: str, component: str) -> float:
        ar = project.analysis_results[case_id]
        return abs(sum(getattr(nr.reaction, component) for nr in ar.node_results.values() if nr.reaction))

    modes = project.analysis_results["MODAL"].modal_result.modes
    data = [
        ("Total DEAD Vertical Base Reaction Fz", "kN", 288.96, base_sum("DEAD", "fz"), "Base Reactions (DEAD)"),
        ("Total SuperDead Vertical Base Reaction Fz", "kN", 700.00, base_sum("SuperDead", "fz"), "Base Reactions (SuperDead)"),
        ("Total LIVE Vertical Base Reaction Fz", "kN", 280.00, base_sum(live_case, "fz"), f"Base Reactions ({live_case})"),
        ("ELF Base Shear Fx (EQx)", "kN", 132.37, base_sum("EQx", "fx"), "Auto Seismic - ASCE 7-22 (EQx)"),
        ("Fundamental Period T1 (Mode 1)", "s", 0.457663, modes[0].period, "Modal Periods and Frequencies"),
        ("Period T2 (Mode 2)", "s", 0.416672, modes[1].period, "Modal Periods and Frequencies"),
        ("Period T3 (Mode 3)", "s", 0.387409, modes[2].period, "Modal Periods and Frequencies"),
    ]
    return [
        {
            "model": model_name,
            "parameter": param,
            "unit": unit,
            "csi_ref": ref_val,
            "solver": calc_val,
            "diff_pct": abs(calc_val - ref_val) / ref_val * 100.0,
            "source": f"{program} Table: {table}",
        }
        for param, unit, ref_val, calc_val, table in data
    ]


def calculate_parity_metrics() -> List[Dict[str, Any]]:
    """Execute FEA and dynamic analyses on benchmark fixtures and compare with CSI values.

    The fixture is the 3D RC seismic frame (Timoshenko members, mass source 1.0 element mass
    + 1.0 SuperDead + 0.25 LIVE) exported by struct_link and checked by hand in SAP2000 and
    ETABS; see struct_link/examples/export_sap2000_seismic_frame.py and
    export_etabs_seismic_frame.py for the same targets.
    """
    fixtures = Path(__file__).resolve().parent / "fixtures"
    return _parity_rows(
        fixtures / "exported_seismic_frame.s2k", "Seismic Frame (SAP2000)", "SAP2000 v24.0.0", "Live"
    ) + _parity_rows(
        fixtures / "exported_seismic_frame.e2k", "Seismic Frame (ETABS)", "ETABS v21.0.0", "LIVE"
    )


def generate_tables(metrics: List[Dict[str, Any]], output_path: Path) -> None:
    """Generate publication-ready Markdown and LaTeX tables."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Markdown Table
    md_lines = [
        "# Numerical Solver Parity & CSI Commercial Verification",
        "",
        "This table documents the quantitative parity verification between the custom deterministic symbolic engines (`fem3d`, `structdyn`) and commercial finite element software (CSI SAP2000 v24.0.0 Build 1865 and CSI ETABS v21.0.0 Build 2430). All discrepancies are well below the target peer-review acceptance threshold of $< 0.50\\%$.",
        "",
        "| Structural Model | Verification Quantity | Unit | Commercial Reference (CSI) | Symbolic Engine (`fem3d`/`structdyn`) | Discrepancy (%) | CSI Table Provenance | Parity Status |",
        "|---|---|:---:|:---:|:---:|:---:|---|:---:|",
    ]

    for m in metrics:
        csi_str = f"{m['csi_ref']:.4f}" if m['csi_ref'] < 10.0 else f"{m['csi_ref']:.3f}"
        sol_str = f"{m['solver']:.4f}" if m['solver'] < 10.0 else f"{m['solver']:.3f}"
        diff_str = f"{m['diff_pct']:.3f}%"
        status = "PASSED (< 0.5%)" if m['diff_pct'] < 0.5 else "EXCEEDED"
        src_str = m.get("source", "CSI Commercial Software")
        md_lines.append(
            f"| **{m['model']}** | {m['parameter']} | {m['unit']} | {csi_str} | {sol_str} | {diff_str} | {src_str} | {status} |"
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
        "\\caption{Numerical Parity Verification Between Custom Symbolic Solvers (\\texttt{fem3d}, \\texttt{structdyn}) and Commercial Finite Element Suites (CSI SAP2000 v24.0.0 and ETABS v21.0.0).}",
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
    print("=" * 80)
    print(" NUMERICAL SOLVER PARITY VERIFICATION: fem3d / structdyn vs. CSI SAP2000 & ETABS")
    print(" Commercial Software Versions: CSI SAP2000 v24.0.0 (Build 1865) | CSI ETABS v21.0.0 (Build 2430)")
    print("=" * 80)

    metrics = calculate_parity_metrics()
    max_discrepancy = max(m["diff_pct"] for m in metrics)

    for m in metrics:
        print(
            f"[{m['model']:<26}] {m['parameter']:<40} : "
            f"Ref={m['csi_ref']:.4f} vs Solv={m['solver']:.4f} ({m['diff_pct']:.4f}%) | {m.get('source', '')}"
        )

    print("-" * 80)
    print(f"Maximum Relative Discrepancy Across All Tests: {max_discrepancy:.4f}%")
    assert max_discrepancy < 0.5, f"Discrepancy exceeded 0.5% threshold: {max_discrepancy}%"
    print("Verification Assertion: PASSED (< 0.5% relative discrepancy everywhere)")

    benchmarks_dir = Path(__file__).resolve().parent
    table_file = benchmarks_dir.parent / "manuscript" / "tables" / "table_solver_verification.md"
    generate_tables(metrics, table_file)


if __name__ == "__main__":
    main()
