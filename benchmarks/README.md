# Structural Engineering Benchmark Suite & Execution Harness

Benchmark, harness, oracle, and analysis tools for the paper
**"A Neuro-Symbolic Large Language Model Agent for the Analysis, Design, and Detailing of Reinforced Concrete Frames: Framework and Oracle-Based Benchmark"** (submitted to *Automation in Construction*).

---

## Directory Structure

```
research_paper/benchmarks/
├── benchmark_cases.json            # 27 cases: prompts, specs, deliverables, scoring rules, frozen references, baselines
├── case_schema.py                  # Pydantic schema for the cases (single source of truth) + design space + difficulty rubric
├── oracle_verifier.py              # Deterministic ground truth: builds each case's canonical model from its spec
├── generate_reference_solutions.py # Freezes reference solutions and runs the minimum-volume baseline search
├── run_benchmarks.py               # Harness: full_agent, ablated, direct_llm, code_gen, heuristic
├── benchmark_utils.py              # Concrete volume, claim parsing (unit-aware), prompt-to-schema fidelity
├── rescore_results.py              # Re-scores saved runs after a scoring change (no LLM calls; --replay for PSFR)
├── audit_results.py                # Consistency audit: replays each verified design and compares it with the oracle
├── analyze_results.py              # Summary tables, paired tests (exact McNemar, exact Wilcoxon), diagnostic plots
├── export_case_table.py            # Manuscript Table 3 (case matrix)
├── export_result_tables.py         # Manuscript Tables 7-12
├── make_result_figures.py          # Manuscript Figures 2-5
├── export_system_prompts.py        # Manuscript Supplementary Material S1 (system prompts)
├── verify_cae_parity.py            # Solver parity against CSI SAP2000 / ETABS
├── commands_to_run.md              # The commands of every run, audit, and analysis
├── code_compliance_notes.md        # What the design tools do not implement, and their simplifications
├── fixtures/
│   ├── exported_seismic_frame.s2k / .e2k   # 3D RC frame verified in SAP2000 and ETABS (struct_link/examples)
│   ├── floor_plan_3story_school.PNG        # school plan, partial grid (no columns at A1, D1)
│   ├── hostel_block_plan_2story.PNG        # hostel plan, partial grid (no column at C1)
│   ├── mall_plan_4story.PNG                # mall plan, dimensions in feet-inches
│   └── ground_motions/
│       ├── RSN6_IMPVALL.I_I-ELC180.AT2      # 1940 Imperial Valley, El Centro Array #9, comp. 180 (PEER NGA)
│       ├── RSN753_LOMAP_CLS000.AT2          # 1989 Loma Prieta, Corralitos, comp. 000 (PEER NGA)
│       └── ElCentro1940_S00E_Chopra.csv     # El Centro S00E (Chopra), columns time [s], acceleration [g]
├── results/                        # Run records (not in the repository; archived on Zenodo)
└── plots/                          # Diagnostic plots of analyze_results.py (not in the repository)
```

---

## Suite Design (27 cases)

Every case states one fully specified structural problem. The `spec` block of each case is the
machine-readable version of its prompt; the oracle, the baseline search, the harness, and the
consistency tests read the problem only from there.

**Archetype families.** Most cases reuse a few buildings so that a failure can be attributed to the
analysis regime rather than to geometry:

| Family | Structure | Cases |
|---|---|---|
| P1/P2 | 2D single-bay portal frames | A01, A07, D02 |
| F2 | 2D frame, bays 5.0/6.0/4.0 m, stories 4.0/3.5/3.5 m | A02–A06, A08 |
| F3 | 3D frame, X bays 5.0/6.0/4.5 m, Y bays 6.0/4.0 m, stories 4.0/3.5/3.5 m (irregular plan) | B01–B08 |
| F8 | F3 plan with eight stories (4.0 m ground story, seven of 3.5 m) | B09 |
| FX | external fixtures: CSI models and architectural plans | C01–C05 |

| Group | Cases | Coverage |
|---|---|---|
| `A_2D` | A01–A08 | gravity design + DXF, modal, ELF (IMF, SDC C), RSA (ASCE 7 spectrum), linear response history (CSV record), resizing under gravity and under RSA |
| `B_3D` | B01–B09 | gravity analysis/design with two-way floors, modal (torsional coupling), bi-directional ELF with 100%-30%, bi-directional RSA (three and eight stories), RSA from a recorded spectrum, response history (AT2 record), resizing under ELF |
| `C_Multimodal` | C01–C06 | SAP2000 import → verify → convert to ETABS, ETABS import → ACI check → export, three floor-plan cases (partial grids, imperial drawing), pinned-base 3D seismic design with DXF and bar schedule |
| `D_Robustness` | D01–D04 | US customary units, infeasible section cap (must be reported, not hidden), missing story heights (assumption or question expected), contradictory geometry (must be flagged) |

**Common basis.** f'c = 27.6 MPa, fy = 414 MPa, 2400 kg/m³ concrete (C02: the ETABS model's f'c = 30 MPa, with fy
stated in the prompt); every design or check case states a net allowable soil bearing pressure of 150 kPa (D01: 3 ksf)
for the isolated footings, which `run_design` sizes and designs but which are not scored (`spec.foundation`; in the
seismic cases the footings of perimeter columns fail under the ASD uplift combination, see
`code_compliance_notes.md`); floor dead load 5.1 kPa (slab + finishes) plus
self-weight; ASCE 7-22 Table 4.3-1 live loads; seismic mass = dead load only (§12.7.2); RC special moment frames
(R = 8) at SDS ≥ 0.75 g and intermediate moment frames (R = 5) at SDC C; seismic combinations with ρ = 1.0 and
Ev = 0.2·SDS·D; RSA combined with gravity through the same LRFD combinations (sign-less spectral response).

**Design space** (stated in every design prompt and enforced by the oracle): one square column section and one
beam section (b ≤ h) for the whole frame, dimensions in 0.05 m (2 in) steps, columns ≥ 0.30 m, beams ≥ 0.25 m wide
(ACI 318-25 §18.7.2.1, §18.6.2.1) and ≥ ℓ/18.5 deep (Table 9.3.1.1).

**Difficulty** is computed, not assigned: dimension + regime + input modality + task (+1 for drawings, +2 for a
robustness probe); Easy ≤ 3, Medium = 4, Hard ≥ 5.

---

## Ground Truth

* **Oracle** (`oracle_verifier.py`): builds the case's canonical model from `spec` with the given sections and runs
  the same deterministic engines the agent uses. Every configuration is judged on this model, never on its own.
* **Reference solutions** (`reference_solution`): frozen metrics for prescribed-section cases, CSI SAP2000/ETABS
  values for the fixture cases, the trial-section DCR of the resizing cases, and the metrics of the baseline design
  for design cases.
* **Minimum-volume baseline** (`baseline_design`): exact optimum of concrete volume over the stated design space,
  found by evaluating candidates in ascending analytic volume (parallel batches). D02 is proven infeasible.

```powershell
python "research_paper/benchmarks/generate_reference_solutions.py" --write          # all cases (~15 min, 10 workers)
python "research_paper/benchmarks/generate_reference_solutions.py" --cases A02_Frame2D_Gravity_Design
```

---

## Metrics

| Metric | Definition |
|---|---|
| TCR | mandatory tools succeeded, a model exists, and every requested file exists at its path and is valid (DXF entities; exported CAE model matches the fixture) |
| CCR | oracle governing DCR ≤ 1.0 on the canonical model, no design-space violation, and, for tool-using agents, a final `run_design` check on an analysis of the delivered model (an analysis run before a later change of sections or loads does not count; see `DesignCheckTracker`); over design cases excluding the D02–D04 probes |
| CHR | share of claimed metrics (among those the prompt requests) off by more than 10 % from the oracle |
| Claim completeness | claimed / requested metrics |
| PSFR | the configuration's model reproduces the spec: grid coordinates, story heights, column count, supports, gravity cases (including the partition weight) with dead/live totals within 2 % of the oracle model's (partition totals too where the case uses a seismic weight), no lateral loads or seismic basis in gravity-only cases, seismic/record parameters (S1 where Eq. 12.8-7 applies, S1 ≥ 0.6 g), ELF seismic load cases and combination inputs (E_v, 100–30 rule), the final model's load combinations in static design cases, the materials of the frame sections (concrete f'c and longitudinal and transverse fy within 1 %, unit weight within 2.5 %, so that the conventional 24 kN/m³ for 2,400 kg/m³ passes), and for design cases the cracked-section, second-order analysis basis, and the final model's design checks: their analysis (static designs: the envelope of all combinations of a static analysis; RSA designs: the spectrum envelope in the specified directions) and their allowable bearing pressure (within 1 %). R and Ie count as the tools derive them when not passed (ELF R from the system, Ie from the Risk Category). Tool parameters are read from successful calls only |
| Probe behavior | D02 reports infeasibility, D03 states an assumption or asks, D04 flags the contradiction |
| N_iter | design checks until the first compliant design in resizing cases |
| η_vol | concrete volume / minimum-volume baseline volume (compliant designs only) |

---

## Running

The paper's results come from one run per case and configuration (seed 42) of four models: `qwen3.5:9b` (local
Ollama), `minimax-m3.1-flash:cloud`, `gemma4:31b-cloud`, and `deepseek-v4.1-flash:cloud` (Ollama Cloud). Agent runs
need `--temperature 0.2`: the harness defaults to 0.2 only when `--seeds` is above 1.

```powershell
conda activate structeng

# Agents and ablation
python "research_paper/benchmarks/run_benchmarks.py" --model gemma4:31b-cloud --config full_agent --cases all --seeds 1 --temperature 0.2
python "research_paper/benchmarks/run_benchmarks.py" --model gemma4:31b-cloud --config ablated --cases all --seeds 1 --temperature 0.2

# One group or selected cases
python "research_paper/benchmarks/run_benchmarks.py" --model qwen3.5:9b --cases B_3D --seeds 1 --temperature 0.2 --timeout 5400
python "research_paper/benchmarks/run_benchmarks.py" --model qwen3.5:9b --cases A05,C03 --seeds 1 --temperature 0.2 --timeout 5400

# Single-shot baselines (plan images and CAE file text are given to them too)
python "research_paper/benchmarks/run_benchmarks.py" --model gemma4:31b-cloud --config direct_llm --cases all --seeds 1
python "research_paper/benchmarks/run_benchmarks.py" --model gemma4:31b-cloud --config code_gen --cases all --seeds 1

# Deterministic heuristic
python "research_paper/benchmarks/run_benchmarks.py" --config heuristic --cases all

# Analysis
python "research_paper/benchmarks/analyze_results.py"
```

See `commands_to_run.md` for the full experiment matrix.

After a change to the scoring (oracle, claim parser, probe rules, fidelity checks), saved agent runs can be re-scored without new LLM calls. With `--replay`, PSFR is recomputed by replaying each run's logged tool calls, which rebuilds the agent's model exactly. The original file is kept as `.bak`. Afterwards, run the consistency audit (`audit_results.py`, see `commands_to_run.md`):

```powershell
python "research_paper/benchmarks/rescore_results.py" research_paper/benchmarks/results/results_<model>_<config>_<timestamp>.json --replay
```

Agent records also hold:
- `tool_log`: the arguments and scalar results of every tool call;
- `final_message`: the full final message;
- `turn_limit_reached`: whether the run used up `--max-turns`. When it does, the model gets one tool-free turn to report its results.
- `llm_calls`: prompt and completion tokens and finish reason of every LLM response; `max_prompt_tokens`, `truncated_responses` (finish reason `length`), `prompt_truncations` (a prompt shorter than the previous one: the server dropped its start), and `final_response_truncated`. A failed run that the context window ended or degraded has failure mode `context_limit`, and one ended by an LLM server error (crash, refused connection) `provider_error`. Both are setup failures, not model failures: re-run them with `--update-file <results file> --resume`, which runs only missing and setup-failed case/seed pairs. When the local server stops answering, the harness stops the campaign instead of recording every further run as a failure; results are written after every run. A response cut off while generating without end is the model's failure, not the setup's: failure mode `runaway_generation` (`output_cap_hits`, `final_response_capped`), not re-run. That is a cut at `--max-output-tokens` (default 131072, thinking included; minimax-m3.1-flash answered single-shot cases after 43k-100k tokens), or a cut by the context window after 32k or more generated tokens (qwen3.5:9b's 64k window ends its runaways first); a shorter cut is the window's (`context_limit`). `--timeout` (default 1800 s per LLM request) is only a backstop for a stalled server, so it must exceed the time a runaway takes (128k tokens: about 20 min at 110 tok/s; for qwen3.5:9b on a local GPU at about 15 tok/s, pass `--timeout 5400`).
- Files: each agent run (and each code_gen script) works in a fresh temporary workspace holding a copy of `fixtures/`, so the prompts' repository-relative paths resolve there and concurrent campaigns cannot overwrite or score each other's deliverables. The deliverables and any other files the agent wrote are kept in `results_<...>_files/<case>_seed<seed>/` (`output_dir`, `undeclared_outputs`); `overwritten_files` lists fixtures the agent exported over (in its own copy only).
- `repeated_calls`: tool calls that repeated an earlier call with the same arguments and the same result. The runner runs them as usual, but adds a notice to the tool result saying the call changed nothing.

---

## Tests

```powershell
pytest research_paper/tests -q                       # suite consistency, oracle, scoring, analysis pipeline
$env:BENCHMARK_SLOW = "1"; pytest research_paper/tests -q   # also re-solves the time-history references
```

The consistency tests check that every spec value appears in its prompt, every requested metric is asked for,
all fixtures exist, every baseline satisfies the design space and is reproduced by the oracle, smaller candidates
fail (optimality spot checks), and frozen references reproduce.

---

## Scope

1. RC moment frames only (ACI 318-25, ASCE 7-22); no steel, walls, or prestressing.
2. One column section and one beam section per frame: the benchmark's design space, which keeps the minimum-volume
   optimum exact (the tools accept any number of sections). Design cases are checked on cracked-section analyses with ACI 318-25 §6.6.4
   second-order effects. The checked limit states are member strength, Chapter 15 joint shear, the Chapter 18 checks
   of the stated frame system (IMF or SMF: capacity-design shear, strong-column/weak-beam, confinement, joints), and
   ASCE 7-22 story drift and stability. Column bars are designed (1 %–6 % for SMF, 1 %–8 % otherwise) for axial-flexural
   strength and, in SMF, strong-column/weak-beam. The remaining gaps are listed in
   `code_compliance_notes.md`.
3. Response history cases are linear elastic analyses with one record each (not a code design procedure).
4. Fixture parity: CSI SAP2000 / ETABS text exchange of the `exported_seismic_frame` model.
