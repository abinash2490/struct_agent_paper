# A Neuro-Symbolic Large Language Model Agent for the Analysis, Design, and Detailing of Reinforced Concrete Frames: Framework and Oracle-Based Benchmark

Benchmark, harness, oracle, scoring, and analysis code of the paper above (Abinash Mandal, University of Nevada,
Reno; submitted to *Automation in Construction*).

The paper presents an agent in which a large language model (LLM) plans the workflow of reinforced concrete
moment-frame design and deterministic tools perform every structural calculation: ASCE 7-22 loading, static and
dynamic analysis, and ACI 318-25 design and detailing, with failing members resized until every check passes. A
27-case benchmark evaluates four open-weight LLMs in four configurations (the full agent, the agent without the
resizing loop, direct prompting, and code generation) and a deterministic heuristic; a deterministic oracle checks
every delivered design and reported value on the case's own canonical model.

---

## Repository Contents

```text
research_paper/
├── README.md
├── benchmarks/
│   ├── README.md                       # Suite design, ground truth, metrics, harness options
│   ├── commands_to_run.md              # The commands of every run, audit, and analysis
│   ├── code_compliance_notes.md        # What the design tools do not implement, and their simplifications
│   ├── benchmark_cases.json            # The 27 cases: prompts, specifications, references, baselines
│   ├── case_schema.py                  # Schema of the cases, design space, difficulty rubric
│   ├── oracle_verifier.py              # Deterministic ground truth on each case's canonical model
│   ├── generate_reference_solutions.py # Frozen references and the minimum-volume baseline search
│   ├── run_benchmarks.py               # Harness: full_agent, ablated, direct_llm, code_gen, heuristic
│   ├── benchmark_utils.py              # Claim parsing, prompt-to-schema fidelity, concrete volume
│   ├── rescore_results.py              # Re-scoring of saved runs (no LLM calls)
│   ├── audit_results.py                # Consistency audit of every verified design
│   ├── analyze_results.py              # Summary tables and paired tests
│   ├── export_case_table.py            # Manuscript Table 3
│   ├── export_result_tables.py         # Manuscript Tables 7-12
│   ├── make_result_figures.py          # Manuscript Figures 2-5
│   ├── export_system_prompts.py        # Manuscript Supplementary Material S1
│   ├── verify_cae_parity.py            # Solver parity against CSI SAP2000 and ETABS
│   └── fixtures/                       # CSI models, plan drawings, ground-motion records
└── tests/                              # Suite consistency, oracle, scoring, and analysis-pipeline tests
```

The run records (`benchmarks/results/`: every tool call, final message, and score of the 459 runs) are archived on
Zenodo with a snapshot of the code used for the runs: [10.5281/zenodo.23939590](https://doi.org/10.5281/zenodo.23939590). The manuscript is not part of this
repository.

---

## Framework Packages

The agent and the engines are separate repositories at [github.com/learnstructure](https://github.com/learnstructure):

| Package | Role |
|---|---|
| [`struct_core`](https://github.com/learnstructure/struct_core) | Typed structural model, validation, units |
| [`struct_load`](https://github.com/learnstructure/struct_load) | ASCE 7-22 loads and load combinations |
| [`fem2d`](https://github.com/learnstructure/fem-2d), [`fem3d`](https://github.com/learnstructure/fem3d) | 2D and 3D frame finite element analysis |
| [`structdyn`](https://github.com/learnstructure/structdyn) | Modal, response spectrum, and response-history analysis |
| [`aci318`](https://github.com/learnstructure/aci318) | ACI 318-25 design and detailing |
| [`struct_draw`](https://github.com/learnstructure/struct_draw) | DXF drawings |
| [`struct_link`](https://github.com/learnstructure/struct_link) | SAP2000 and ETABS model exchange |
| [`struct_agent`](https://github.com/learnstructure/struct_agent) | LLM agent runner and tools |

Clone them next to this repository (one parent folder holding `research_paper/` and the packages), and install them
in one environment:

```powershell
conda activate structeng
pip install -e struct_core/ -e struct_load/ -e fem2d/ -e fem3d/ -e structdyn/ -e aci318/ -e struct_draw/ -e struct_link/ -e struct_agent/
```

---

## Reproducing the Results

Commands run from the parent folder. Re-scoring, auditing, and the tables and figures need no LLM calls; they read
the run records from `research_paper/benchmarks/results/` (from the Zenodo archive):

```powershell
python "research_paper/benchmarks/rescore_results.py" research_paper/benchmarks/results/<results file>.json --replay
python "research_paper/benchmarks/audit_results.py" research_paper/benchmarks/results/<results file>.json
python "research_paper/benchmarks/analyze_results.py"
```

New runs need an Ollama server (local for `qwen3.5:9b`, Ollama Cloud for the other three models). The paper's runs
used one run per case and configuration (seed 42), at temperature 0.2 for the agents and 0.0 for the single-shot
baselines; `benchmarks/commands_to_run.md` gives every command. A repeated run is likely, but not certain, to
reproduce the original, because a served model can change and not every provider guarantees deterministic sampling.

The minimum-volume baselines and frozen references are regenerated only after a change to the cases or the solvers:

```powershell
python "research_paper/benchmarks/generate_reference_solutions.py" --write
```

## Tests

```powershell
pytest research_paper/tests -q
```

The tests check that every specified value is stated in its prompt, every fixture exists, every baseline satisfies
the design space and is reproduced by the oracle, and the scoring and analysis pipeline behave as documented.
