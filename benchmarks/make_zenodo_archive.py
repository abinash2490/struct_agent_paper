"""
Build the two files of the Zenodo deposit that the paper cites.

Usage
-----
    python research_paper/benchmarks/make_zenodo_archive.py --tag v1.0-paper
writes, into research_paper/zenodo_upload/:

* ``struct_agent_benchmark_results.zip``: the results file of every model and configuration that the analysis
  reads (``results/results_*.json``), each run's output folder (``*_files/``: drawings, CAE exports, scripts), the
  last consistency audit of each results file, the dataset README, and a SHA-256 manifest.
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
RESULTS = REPO_ROOT / "research_paper" / "benchmarks" / "results"
OUT = REPO_ROOT / "research_paper" / "zenodo_upload"
REPOSITORIES = ["research_paper", "struct_core", "struct_load", "fem2d", "fem3d", "structdyn", "aci318",
                "struct_draw", "struct_link", "struct_agent"]

DATASET_README = """# Benchmark results: neuro-symbolic LLM agent for reinforced concrete frames

Run records of the paper "A Neuro-Symbolic Large Language Model Agent for the Analysis, Design, and Detailing of
Reinforced Concrete Frames: Framework and Oracle-Based Benchmark" (A. Mandal), DOI 10.5281/zenodo.23939590. The code is in the
companion file struct_agent_code_<tag>.zip of this record and at https://github.com/learnstructure.

## Contents

- `results/results_<model>_<configuration>_<timestamp>.json`: one file per model and configuration (4 models x 4
  configurations, and the deterministic heuristic; 459 runs). Each file holds the summary metrics and, per case,
  the oracle verdict and scores, the delivered sections, the claimed and oracle values, and, for the agents, every
  tool call with its arguments and scalar result (`tool_log`), the design-check history, the token counts of every
  LLM response (`llm_calls`), and the full final message.
- `results/results_<...>_files/<case>_seed<seed>/`: the files each run wrote (DXF drawings, SAP2000/ETABS exports,
  generated scripts).
- `results/audit_results_<...>.md`: the last consistency audit of each agent results file.
- `MANIFEST.sha256`: SHA-256 of every file.

## Use

Unzip into `research_paper/benchmarks/` of the code (so that the files land in `research_paper/benchmarks/results/`),
then, from the folder that holds `research_paper/` and the packages:

    python research_paper/benchmarks/analyze_results.py
    python research_paper/benchmarks/rescore_results.py research_paper/benchmarks/results/<file>.json --replay
    python research_paper/benchmarks/audit_results.py research_paper/benchmarks/results/<file>.json

None of these calls an LLM. `research_paper/benchmarks/commands_to_run.md` gives the commands of the runs.

License: CC BY 4.0.
"""


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
        z.writestr("README.md", DATASET_README.replace("<tag>", tag))
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tag", required=True, help="git tag of the paper's code in every repository")
    parser.add_argument("--results-only", action="store_true", help="build only the results archive")
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    results_archive(args.tag)
    if not args.results_only:
        code_archive(args.tag)


if __name__ == "__main__":
    main()
