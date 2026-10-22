# Structural Engineering Benchmark Suite & Execution Harness

This directory contains the automated benchmarking harness, evaluation cases, test telemetry, and publication figure generators for the paper:
**"Autonomous Structural Engineering via Neuro-Symbolic Agentic Orchestration"** (*Automation in Construction* / *Advanced Engineering Informatics*).

---

## Directory Structure

```
research_paper/benchmarks/
├── benchmark_cases.json   # 24 standardized structural design challenges (JSON)
├── fixtures/              # Real architectural drawings (.PNG) and CAE models (.s2k, .e2k)
│   ├── exported_seismic_frame.s2k     # 3D multi-story seismic frame (SAP2000 fixture)
│   ├── exported_seismic_frame.e2k     # 3D multi-story seismic frame (ETABS fixture)
│   ├── sample_frame.s2k               # 2D portal frame CSI SAP2000 parity fixture
│   ├── sample_frame.e2k               # 2D portal frame CSI ETABS parity fixture
│   ├── frame.s2k                      # 3D 3-story frame CSI SAP2000 parity fixture
│   ├── floor_plan_3story_school.PNG   # 3-story school plan (3x3 bays, educational)
│   ├── hostel_block_plan_2story.PNG   # 2-story hostel block plan (7x2 bays, residential; reserved for extended suite)
│   └── mall_plan_4story.PNG           # 4-story commercial mall plan (4x3 bays, retail)
├── run_benchmarks.py      # Automated batch execution harness (Gemini & Ollama)
├── generate_human_baselines.py # Deterministic ACI 318 baseline generator & verifier
├── verify_cae_parity.py   # Parity verifier comparing against CSI SAP2000 & ETABS
├── analyze_results.py     # Results compiler, LaTeX/Markdown tables & plots
├── results/               # Structured JSON execution telemetry logs
└── plots/                 # Publication-grade figures (TCR/CCR bars, DCR trajectories)
```

---

## Benchmark Suite Catalog (24 Cases)

The 24 benchmark cases are organized into three 8-case groups centered on **Earthquake Resistance, Structural Dynamics, and Codified Design**:

| Group Identifier | Focus Regimes | Cases | Highlights |
|---|---|---|---|
| **`Group_A_2D`** | 2D Plane Frames | `A01`–`A08` | Single-bay portal, wide-span storage, multi-bay multi-story gravity, 2D modal eigenvalue, **ASCE 7 Response Spectrum Analysis (RSA)**, ground motion RSA, and closed-loop member reflection (DXF drawings to `research_paper/drawings/`). |
| **`Group_B_3D`** | 3D Space Frames | `B01`–`B08` | 2-story 3D residential gravity frame, commercial gravity, ASCE 7 Seismic ELF, 3D modal dynamics, **3D RSA (X-direction)**, **3D multi-directional RSA**, 3D seismic reflection, and bi-directional orthogonal seismic loading. |
| **`Group_C_Advanced`** | Dynamic & Multimodal | `C01`–`C08` | **1940 El Centro time-history**, **1994 Northridge time-history**, CSI SAP2000 `.s2k` round-trip, CSI ETABS `.e2k` round-trip, `struct_agent.vision` floor plan ingestion (school & mall), dynamic reflection, and autonomous CAD DXF production. |

---

## Quickstart Instructions

### 1. Environment Activation
```powershell
# In PowerShell:
conda activate structeng
```

### 2. Running Benchmarks with Google Gemini (or Frontier Model)
The runner automatically loads `GEMINI_API_KEY` from `struct_agent/.env`:
```powershell
# Run Group A (2D Plane Frames - 8 cases):
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --cases Group_A_2D

# Run Group B (3D Space Frames - 8 cases):
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --cases Group_B_3D

# Run Group C (Advanced Dynamic & Interop - 8 cases):
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --cases Group_C_Advanced

# Run all 24 cases:
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --cases all

# Run with random seeds repetition (e.g., 5 seeds):
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --cases Group_A_2D --seeds 5

# Run ablation study (reflection loop disabled):
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --config ablated --cases Group_A_2D --seeds 5

# Run deterministic classical heuristic baseline:
python "research_paper/benchmarks/run_benchmarks.py" --config heuristic --cases all --seeds 1
```

### 3. Running with Open-Weight Models via Ollama
Ensure Ollama is running (`ollama serve`):
```powershell
# 1. Local Qwen 3.5:
python "research_paper/benchmarks/run_benchmarks.py" --model qwen3.5:9b --cases Group_A_2D --seeds 5

# 2. Cloud Nemotron-3 Super:
python "research_paper/benchmarks/run_benchmarks.py" --model nemotron-3-super:cloud --cases Group_A_2D --seeds 5

# 3. Cloud Gemma 4:
python "research_paper/benchmarks/run_benchmarks.py" --model gemma4:31b-cloud --cases Group_A_2D --seeds 5
```



---

## Analyzing Results & Generating Figures

Once runs finish, summarize telemetry into publication tables and generate publication plots:

```powershell
python "research_paper/benchmarks/analyze_results.py"
```

Outputs generated (all saved with unique timestamps so no past results or figures are ever replaced):
- Telemetry table printed directly to stdout and saved to `results/summary_table_<TIMESTAMP>.md`
- Detailed per-case comparison table saved to `results/detailed_case_comparison_table_<TIMESTAMP>.md`
- Failure-mode breakdown taxonomy saved to `results/failure_mode_breakdown_<TIMESTAMP>.md`
- Paired Wilcoxon signed-rank significance tests printed to stdout
- `plots/fig_benchmark_comparison_<TIMESTAMP>.png`: Grouped bar chart comparing Task Completion Rate (TCR) and Code Compliance Rate (CCR)
- `plots/fig_prompt_schema_fidelity_<TIMESTAMP>.png`: Prompt-to-Schema Fidelity Rate (PSFR %) across configurations
- `plots/fig_dcr_convergence_<TIMESTAMP>.png`: Self-healing reflection optimization trajectory curves ($DCR$ vs iteration) *(only generated when $\ge 1$ run has a multi-iteration DCR history)*
- `plots/fig_material_economy_<TIMESTAMP>.png`: Structural concrete economy across models ($\eta_{\mathrm{vol}} = V_{\mathrm{agent}} / V_{\mathrm{base}}$)
- `plots/fig_hallucination_rate_<TIMESTAMP>.png`: Calculation Hallucination Rate (CHR %) across architectures
- `plots/fig_hallucination_error_breakdown_<TIMESTAMP>.png`: Relative calculation discrepancy breakdown by physical engineering regime
- `plots/fig_safety_economy_tradeoff_<TIMESTAMP>.png`: Structural safety (CCR) vs. material economy ($\eta_{\mathrm{vol}}$) Pareto trade-off
- `plots/fig_runtime_comparison_<TIMESTAMP>.png`: Computational turnaround runtime comparison across models and configurations

---

## Running the Benchmark Test Suite

To verify benchmark cases integrity, deterministic oracle verifiers, CAE numerical parity, schema fallbacks, and the analysis pipeline:

```powershell
pytest research_paper/tests -v
```

---

## Limitations & Scope

To ensure transparent peer review, the scope and boundary limitations of the benchmark suite are explicitly delineated:
1. **Structural Typology**: All 24 benchmark cases evaluate reinforced concrete (RC) moment-resisting frame typologies designed per ACI 318 and ASCE 7. The suite does not currently include structural steel frames, reinforced concrete shear walls, or post-tensioned/pre-stressed concrete elements.
2. **CAE Parity Scope**: Commercial finite element software round-trip parity is verified on CSI SAP2000 v24.0.0 and CSI ETABS v21.0.0 text exchange fixtures (`.s2k` and `.e2k`).
3. **Seismic Detailing Decoupling**: Capacity evaluations focus on strength-level demand-capacity ratios ($P-M_2-M_3$ interaction and one-way shear). Prescriptive seismic detailing provisions (e.g., strong-column/weak-beam ratios and joint shear confinement) are decoupled and handled downstream during production CAD detailing.
