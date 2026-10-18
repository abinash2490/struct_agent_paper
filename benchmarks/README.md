# Structural Engineering Benchmark Suite & Execution Harness

This directory contains the automated benchmarking harness, evaluation cases, test telemetry, and publication figure generators for the paper:
**"Autonomous Structural Engineering via Neuro-Symbolic Agentic Orchestration"** (*Automation in Construction* / *Advanced Engineering Informatics*).

---

## Directory Structure

```
research paper/benchmarks/
├── benchmark_cases.json   # 24 standardized structural design challenges (JSON)
├── run_benchmarks.py      # Automated batch execution harness (Gemini & Ollama)
├── analyze_results.py     # Results compiler, LaTeX/Markdown tables & plots
├── results/               # Structured JSON execution telemetry logs
└── plots/                 # Publication-grade figures (TCR/CCR bars, DCR trajectories)
```

---

## Benchmark Suite Catalog (24 Cases)

The 24 benchmark cases are organized into three 8-case groups centered on **Earthquake Resistance, Structural Dynamics, and Codified Design**:

| Group Identifier | Focus Regimes | Cases | Highlights |
|---|---|---|---|
| **`Group_A_2D`** | 2D Plane Frames | `A01`–`A08` | Single-bay portal, wide-span storage, multi-bay multi-story gravity, 2D modal eigenvalue, **ASCE 7 Response Spectrum Analysis (RSA)**, ground motion RSA, and closed-loop member reflection. |
| **`Group_B_3D`** | 3D Space Frames | `B01`–`B08` | 3D regular office, commercial gravity, ASCE 7 Seismic ELF, 3D modal dynamics, **3D RSA (X-direction)**, **3D multi-directional RSA**, 3D seismic reflection, and torsional irregularity. |
| **`Group_C_Advanced`** | Dynamic & Multimodal | `C01`–`C08` | **1940 El Centro time-history**, **1994 Northridge time-history**, CSI SAP2000 `.s2k` round-trip, CSI ETABS `.e2k` round-trip, `struct_agent.vision` floor plan ingestion, dynamic reflection, and autonomous CAD DXF production. |

---

## Quickstart Instructions

### 1. Environment Activation
```powershell
# In PowerShell:
conda activate structeng
```

### 2. Running Benchmarks with Google Gemini 3.8 Flash
The runner automatically loads `GEMINI_API_KEY` from `struct_agent/.env`:
```powershell
# Run Group A (2D Plane Frames - 8 cases):
python "research paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --cases Group_A_2D

# Run Group B (3D Space Frames - 8 cases):
python "research paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --cases Group_B_3D

# Run Group C (Advanced Dynamic & Interop - 8 cases):
python "research paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --cases Group_C_Advanced

# Run all 24 cases:
python "research paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --cases all

# Run a single specific case:
python "research paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --cases A06_2D_Response_Spectrum_ASCE7

# Run ablation study (reflection loop disabled):
python "research paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --config ablated --cases Group_A_2D
```

### 3. Running with Open-Weight Models via Ollama
Ensure Ollama is running (`ollama serve`):
```powershell
# 1. Local Qwen 3.5 9B:
python "research paper/benchmarks/run_benchmarks.py" --model qwen3.5:9b --cases Group_A_2D

# 2. Cloud GPT-OSS 120B:
python "research paper/benchmarks/run_benchmarks.py" --model gpt-oss:120b-cloud --cases Group_A_2D

# 3. Cloud Nemotron 3 Ultra:
python "research paper/benchmarks/run_benchmarks.py" --model nemotron-3-ultra:cloud --cases Group_A_2D
```

---

## Analyzing Results & Generating Figures

Once runs finish, summarize telemetry into publication tables and generate publication plots:

```powershell
python "research paper/benchmarks/analyze_results.py"
```

Outputs generated (all saved with unique timestamps so no past results or figures are ever replaced):
- Telemetry table printed directly to stdout and saved to `results/summary_table_<TIMESTAMP>.md`
- `plots/fig_benchmark_comparison_<TIMESTAMP>.png`: Grouped bar chart comparing Task Completion Rate (TCR) and Code Compliance Rate (CCR)
- `plots/fig_dcr_convergence_<TIMESTAMP>.png`: Self-healing reflection optimization trajectory curves ($DCR$ vs iteration)
