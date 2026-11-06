"""
Build the four files of the Zenodo deposit that the paper cites.

Usage
-----
    python research_paper/benchmarks/make_zenodo_archive.py --tag v1.0-paper
writes, into research_paper/zenodo_upload/:

* ``README.md``: what the deposit contains, how to use it, and the sources of the ground-motion records.
* ``benchmark_cases.md``: the 27 benchmark cases in readable form (task, prompt, requested values, reference values),
  generated from ``benchmark_cases.json``, which must be unchanged since ``<tag>``.
* ``struct_agent_benchmark_results.zip``: the results file of every model and configuration that the analysis
  reads (``results/results_*.json``), each run's output folder (``*_files/``: drawings, CAE exports, scripts), the
  last consistency audit of each results file, and a SHA-256 manifest.
* ``struct_agent_code_<tag>.zip``: the source of every repository at ``<tag>`` (``git archive``, so only committed
  files), one folder per repository, with the conda environment file.

Every repository must have the tag; the script stops and names those that do not. Pilot runs, results superseded
by re-runs, ``.bak`` copies from re-scoring, and the generated summary tables are left out.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
RESULTS = REPO_ROOT / "research_paper" / "benchmarks" / "results"
OUT = REPO_ROOT / "research_paper" / "zenodo_upload"
REPOSITORIES = ["research_paper", "struct_core", "struct_load", "fem2d", "fem3d", "structdyn", "aci318",
                "struct_draw", "struct_link", "struct_agent"]

TITLE = ("Benchmark cases, results, and source code for 'A Neuro-Symbolic Large Language Model Agent for the "
         "Analysis, Design, and Detailing of Reinforced Concrete Frames'")
PAPER = ("A Neuro-Symbolic Large Language Model Agent for the Analysis, Design, and Detailing of Reinforced Concrete "
         "Frames: Framework and Oracle-Based Benchmark")

DEPOSIT_README = """# <title>

Data and code of the paper "<paper>" (A. Mandal). DOI of this record: 10.5281/zenodo.23939590. The framework
packages are developed at https://github.com/learnstructure.

## Files

- `benchmark_cases.md`: the 27 benchmark cases (2D frames, 3D frames, drawing and CAE pipelines, robustness
  probes), each with its task, the prompt given to every configuration, the requested values, and the reference
  values of the oracle or the minimum-volume baseline design.
- `struct_agent_code_<tag>.zip`: the source of the nine framework packages and of `research_paper` (benchmark,
  oracle, scoring, statistics, table, and figure scripts) at the git tag `<tag>`, and the conda environment file
  `environment.yml`. The machine-readable cases are `research_paper/benchmarks/benchmark_cases.json` (prompt,
  specification, deliverables, evaluation settings, and reference solution of each case); the CAE models, plan
  drawings, and ground-motion records the prompts refer to are in `research_paper/benchmarks/fixtures/`.
- `struct_agent_benchmark_results.zip`: the run records of the 459 runs (4 models x 4 configurations x 27 cases,
  and the deterministic heuristic):
  - `results/results_<model>_<configuration>_<timestamp>.json`: one file per model and configuration, with the
    summary metrics and, per case, the oracle verdict and scores, the delivered sections, the claimed and oracle
    values, and, for the agents, every tool call with its arguments and scalar result (`tool_log`), the
    design-check history, the token counts of every LLM response (`llm_calls`), and the full final message;
  - `results/results_<...>_files/<case>_seed<seed>/`: the files each run wrote (DXF drawings, SAP2000/ETABS
    exports, generated scripts);
  - `results/audit_results_<...>.md`: the last consistency audit of each agent results file;
  - `MANIFEST.sha256`: SHA-256 of every file.

## Use

Unzip the code, then unzip the results into `research_paper/benchmarks/` (so that the run records land in
`research_paper/benchmarks/results/`), and run from the folder that holds `research_paper/` and the packages:

    python research_paper/benchmarks/analyze_results.py
    python research_paper/benchmarks/rescore_results.py research_paper/benchmarks/results/<file>.json --replay
    python research_paper/benchmarks/audit_results.py research_paper/benchmarks/results/<file>.json

None of these calls an LLM. `research_paper/benchmarks/commands_to_run.md` gives the commands of the runs.

## Ground-motion records

Two records in `research_paper/benchmarks/fixtures/ground_motions/` are from the PEER NGA-West2 database:
RSN 6 (1940 Imperial Valley, El Centro Array #9, component 180) and RSN 753 (1989 Loma Prieta, Corralitos,
component 000). Users of these records should cite:

Ancheta, T. D., Darragh, R. B., Stewart, J. P., Seyhan, E., Silva, W. J., Chiou, B. S. J., Wooddell, K. E.,
Graves, R. W., Kottke, A. R., Boore, D. M., Kishida, T., & Donahue, J. L. (2013). PEER NGA-West2 Database. PEER
Report 2013-03, Pacific Earthquake Engineering Research Center, University of California, Berkeley, CA.

The records remain subject to the terms of use of the PEER database (https://ngawest2.berkeley.edu). The file
`ElCentro1940_S00E_Chopra.csv` is the S00E component of the 1940 Imperial Valley (El Centro) record as tabulated by
Chopra, A. K. (2017), Dynamics of Structures: Theory and Applications to Earthquake Engineering (5th ed.), Pearson,
Appendix 6.

## License

Run records, case descriptions, and documentation: CC BY 4.0. Source code: MIT (the `LICENSE` file of each
repository).
"""

METRICS = {"total_weight": "total dead load W", "max_base_reaction": "maximum support reaction",
           "base_shear": "base shear V_b", "fundamental_period": "fundamental period T_1", "period_t2": "period T_2",
           "period_t3": "period T_3", "modal_mass_ratio": "cumulative modal mass ratio",
           "peak_roof_displacement": "peak roof displacement", "governing_dcr": "governing DCR"}
BEHAVIOR = {"report_infeasible": "report that no compliant design exists within the section cap",
            "declare_assumption": "declare an assumption for the missing input or ask for it",
            "flag_contradiction": "flag the contradiction between the bay widths and the total length"}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def results_archive(tag: str) -> Path:
    files = sorted(RESULTS.glob("results_*.json"))
    members: list[Path] = []
    for f in files:
        members.append(f)
        run_dir = RESULTS / f"{f.stem}_files"
        if run_dir.is_dir():
            members += sorted(p for p in run_dir.rglob("*") if p.is_file())
        # audit_results_<results stem without 'results_'>_<audit timestamp>.md: keep the last
        audits = sorted(RESULTS.glob(f"audit_{f.stem}_*.md"),
                        key=lambda p: re.findall(r"_(\d{8}_\d{6})\.md$", p.name)[0])
        if audits:
            members.append(audits[-1])
    out = OUT / "struct_agent_benchmark_results.zip"
    manifest = [f"{_sha256(p)}  {p.relative_to(RESULTS.parent).as_posix()}" for p in members]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in members:
            z.write(p, p.relative_to(RESULTS.parent).as_posix())
        z.writestr("MANIFEST.sha256", "\n".join(manifest) + "\n")
    print(f"wrote {out}: {len(files)} results files, {len(members)} files")
    return out


def code_archive(tag: str) -> Path:
    missing = [r for r in REPOSITORIES if tag not in _git(REPO_ROOT / r, "tag", "--list", tag).split()]
    if missing:
        sys.exit(f"tag {tag!r} missing in: {', '.join(missing)} (commit, then: git -C <repo> tag {tag})")
    out = OUT / f"struct_agent_code_{tag}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z, tempfile.TemporaryDirectory() as tmp:
        for repo in REPOSITORIES:
            part = Path(tmp) / f"{repo}.zip"
            _git(REPO_ROOT / repo, "archive", "--format=zip", f"--prefix={repo}/", "-o", str(part), tag)
            commit = _git(REPO_ROOT / repo, "rev-list", "-n", "1", tag).strip()
            with zipfile.ZipFile(part) as src:
                for info in src.infolist():
                    if not info.is_dir():
                        z.writestr(info.filename, src.read(info))
            print(f"  {repo}: {tag} = {commit[:12]}")
        env = REPO_ROOT / "environment.yml"
        if env.exists():
            z.write(env, "environment.yml")
    print(f"wrote {out}")
    return out


def _plain(text: str) -> str:
    """Table 3 cells without HTML subscripts (S<sub>DS</sub> -> S_DS)."""
    return re.sub(r"<sub>([^<]*)</sub>", r"_\1", text)


def cases_markdown(tag: str) -> Path:
    case_file = "benchmarks/benchmark_cases.json"
    changed = subprocess.run(["git", "-C", str(REPO_ROOT / "research_paper"), "diff", "--quiet", tag, "--", case_file])
    if changed.returncode != 0:
        sys.exit(f"{case_file} differs from {tag}; benchmark_cases.md must describe the archived cases")
    from research_paper.benchmarks.case_schema import load_cases
    from research_paper.benchmarks.export_case_table import TITLES, _geometry, _loading, _reference, _task

    cases = load_cases()
    lines = [f"# Benchmark cases ({len(cases)})", "",
             "The cases of the benchmark, in the form given to every configuration. The machine-readable source, with "
             "the full specification from which the oracle builds each case's canonical model, is "
             f"`research_paper/benchmarks/benchmark_cases.json` in `struct_agent_code_{tag}.zip`; the files the "
             "prompts refer to (`research_paper/benchmarks/fixtures/...`) are in the same archive. Values are in the "
             "units of each case (kN and m; kip and ft for D01). The reference values are the oracle's for the stated "
             "sections; for a design case, the baseline is the compliant design of least concrete volume on the "
             "section grid.", "",
             "| Case | Task | Difficulty | Geometry or input | Loading and analysis | Baseline or reference values |",
             "|---|:---:|:---:|---|---|---|"]
    for c in cases:
        cid = c.id.split("_")[0]
        lines.append(f"| {cid} | {_task(c)} | {c.difficulty.label} ({c.difficulty.score}) | "
                     f"{_plain(_geometry(c))} | {_plain(_loading(c))} | {_plain(_reference(c))} |")
    for c in cases:
        cid = c.id.split("_")[0]
        ev = c.evaluation
        lines += ["", f"## {cid}", "", f"**{TITLES.get(cid, c.name)}**", "",
                  f"- Task: {_task(c)}; difficulty {c.difficulty.label} ({c.difficulty.score})",
                  "- Requested values: " + ", ".join(METRICS.get(m, m) for m in ev.required_metrics)]
        if c.deliverables.files:
            lines.append("- Requested files: " + ", ".join(f"`{Path(f.path).name}`" for f in c.deliverables.files))
        if ev.expected_behavior:
            lines.append(f"- Expected behavior: {BEHAVIOR.get(ev.expected_behavior, ev.expected_behavior)}")
        lines.append(f"- Baseline or reference values: {_plain(_reference(c))}")
        lines += ["", "Prompt:", ""] + [f"> {ln}" if ln else ">" for ln in c.prompt.strip().splitlines()]
    out = OUT / "benchmark_cases.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}: {len(cases)} cases")
    return out


def deposit_readme(tag: str) -> Path:
    out = OUT / "README.md"
    text = DEPOSIT_README.replace("<title>", TITLE).replace("<paper>", PAPER).replace("<tag>", tag)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tag", required=True, help="git tag of the paper's code in every repository")
    parser.add_argument("--results-only", action="store_true", help="build only the results archive")
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    deposit_readme(args.tag)
    cases_markdown(args.tag)
    results_archive(args.tag)
    if not args.results_only:
        code_archive(args.tag)


if __name__ == "__main__":
    main()
