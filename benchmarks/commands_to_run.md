# Benchmark Execution Commands Matrix (Multi-Model & Baselines)

This document contains the complete execution command catalog to reproduce all experiments for the research paper:  
**"Autonomous Structural Engineering via Neuro-Symbolic Agentic Orchestration"** (*Automation in Construction* / *Advanced Engineering Informatics*).

---

## Experimental Setup Overview

### The Evaluated LLM Backbones:
1. **`gemini-3.8-flash`** — Frontier Cloud Multimodal VLM via Google Gemini API (`GEMINI_API_KEY`)
2. **`qwen3.5:9b`** — Local Open-Weight Multimodal VLM via Ollama (`http://localhost:11434/v1`)
3. **`nemotron-3-super:cloud`** — NVIDIA Math/Engineering-Tuned Reasoning Model via Cloud Ollama Host
4. **`gemma4:31b-cloud`** — Open-Weight High-Capacity Frontier Reasoning Model via Cloud Host

### The 5 Configurations / Baselines:
* **Baseline 0 (`heuristic`)**: Deterministic classical engineering rules of thumb ($h_c=b_c=0.05H$, $b_b=L/14, h_b=L/12$) with DCR scaling ($\sqrt{\text{DCR}}$); establishes the non-LLM engineering floor.
* **Proposed Framework (`full_agent`)**: Full neuro-symbolic agent with symbolic tools (`fem2d`/`fem3d`/`structdyn`/`aci318`/`struct_draw`) and closed-loop self-healing reflection.
* **Baseline 3 (`ablated`)**: Agent equipped with tools, but reflection loop (`modify_project`) is removed and `allow_model_recreation=False` is enforced.
* **Baseline 1 (`direct_llm`)**: Zero-shot direct prompting without access to symbolic tools (measures baseline calculation hallucination rate $\text{CHR}$).
* **Baseline 2 (`code_gen`)**: Prompted to generate standalone Python scripts from scratch without `struct_agent` tools.

> **Sampling Temperature & Seed Protocol**: For single-seed baseline runs (`direct_llm`, `code_gen`, `heuristic`), temperature defaults to `0.0`. For multi-seed statistical significance evaluations (`--seeds 5` for `full_agent` and `ablated`), temperature automatically defaults to `0.2` across pseudo-random seeds 42, 43, 44, 45, 46 to generate authentic stochastic exploration and valid Wilcoxon paired test distributions. You can also override explicitly with `--temperature <val>`.

---

## Prerequisites

Before running, activate the conda environment:
```powershell
conda activate structeng
```

For Ollama models, ensure the Ollama service is active:
```powershell
ollama serve
```

---

## 0. Deterministic Heuristic Baseline (Non-LLM Floor)

```powershell
# [RUN 00] - Classical Engineering Heuristic (Deterministic, 1 Seed)
python "research_paper/benchmarks/run_benchmarks.py" --config heuristic --cases all --seeds 1
```

---

## 1. Model 1: `gemini-3.8-flash` (Cloud Frontier API)

> Note: The runner automatically loads `GEMINI_API_KEY` from `struct_agent/.env`.

```powershell
# [RUN 01] - Proposed Framework (Full Agent with Reflection, 5 Seeds)
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --config full_agent --cases all --seeds 5

# [RUN 02] - Baseline 3: Ablated Agent (Without Reflection Loop, 5 Seeds)
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --config ablated --cases all --seeds 5

# [RUN 03] - Baseline 1: Direct Zero-Shot LLM Prompting (1 Seed)
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --config direct_llm --cases all --seeds 1

# [RUN 04] - Baseline 2: Code-Generation LLM (1 Seed)
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --config code_gen --cases all --seeds 1
```

---

## 2. Model 2: `qwen3.5:9b` (Local Workstation via Ollama)

```powershell
# [RUN 05] - Proposed Framework (Full Agent with Reflection, 5 Seeds)
python "research_paper/benchmarks/run_benchmarks.py" --model qwen3.5:9b --config full_agent --cases all --seeds 5

# [RUN 06] - Baseline 3: Ablated Agent (Without Reflection Loop, 5 Seeds)
python "research_paper/benchmarks/run_benchmarks.py" --model qwen3.5:9b --config ablated --cases all --seeds 5

# [RUN 07] - Baseline 1: Direct Zero-Shot LLM Prompting (1 Seed)
python "research_paper/benchmarks/run_benchmarks.py" --model qwen3.5:9b --config direct_llm --cases all --seeds 1

# [RUN 08] - Baseline 2: Code-Generation LLM (1 Seed)
python "research_paper/benchmarks/run_benchmarks.py" --model qwen3.5:9b --config code_gen --cases all --seeds 1
```

---

## 3. Model 3: `nemotron-3-super:cloud` (Cloud Ollama Host)

> Note: If hosted on a remote server/endpoint, append `--api-base http://<HOST_IP>:11434/v1`.

```powershell
# [RUN 09] - Proposed Framework (Full Agent with Reflection, 5 Seeds)
python "research_paper/benchmarks/run_benchmarks.py" --model nemotron-3-super:cloud --config full_agent --cases all --seeds 5

# [RUN 10] - Baseline 3: Ablated Agent (Without Reflection Loop, 5 Seeds)
python "research_paper/benchmarks/run_benchmarks.py" --model nemotron-3-super:cloud --config ablated --cases all --seeds 5

# [RUN 11] - Baseline 1: Direct Zero-Shot LLM Prompting (1 Seed)
python "research_paper/benchmarks/run_benchmarks.py" --model nemotron-3-super:cloud --config direct_llm --cases all --seeds 1

# [RUN 12] - Baseline 2: Code-Generation LLM (1 Seed)
python "research_paper/benchmarks/run_benchmarks.py" --model nemotron-3-super:cloud --config code_gen --cases all --seeds 1
```

---

## 4. Model 4: `gemma4:31b-cloud` (Cloud Open-Weight Host)

> Note: If hosted on a remote server/endpoint, append `--api-base http://<HOST_IP>:11434/v1`.

```powershell
# [RUN 13] - Proposed Framework (Full Agent with Reflection, 5 Seeds)
python "research_paper/benchmarks/run_benchmarks.py" --model gemma4:31b-cloud --config full_agent --cases all --seeds 5

# [RUN 14] - Baseline 3: Ablated Agent (Without Reflection Loop, 5 Seeds)
python "research_paper/benchmarks/run_benchmarks.py" --model gemma4:31b-cloud --config ablated --cases all --seeds 5

# [RUN 15] - Baseline 1: Direct Zero-Shot LLM Prompting (1 Seed)
python "research_paper/benchmarks/run_benchmarks.py" --model gemma4:31b-cloud --config direct_llm --cases all --seeds 1

# [RUN 16] - Baseline 2: Code-Generation LLM (1 Seed)
python "research_paper/benchmarks/run_benchmarks.py" --model gemma4:31b-cloud --config code_gen --cases all --seeds 1
```

---

## Post-Run: Results Analysis, Statistical Significance & Figure Generation

Once benchmark runs finish (or at any intermediate point), execute the analysis script to aggregate all JSON logs in `results/`, conduct paired Wilcoxon signed-rank tests, compile markdown comparison tables, and generate publication-grade figures:

```powershell
python "research_paper/benchmarks/analyze_results.py"
```

### Outputs Generated:
1. **Markdown Summary Table**: Printed to console and saved as `research_paper/benchmarks/results/summary_table_<TIMESTAMP>.md`
2. **Failure-Mode Breakdown Table**: Saved as `research_paper/benchmarks/results/failure_mode_breakdown_<TIMESTAMP>.md`
3. **Statistical Significance Report**: Paired Wilcoxon signed-rank test output printed to stdout
4. **Benchmark Comparison Bar Chart**: Saved as `research_paper/benchmarks/plots/fig_benchmark_comparison_<TIMESTAMP>.png`
5. **Prompt-to-Schema Fidelity Bar Chart**: Saved as `research_paper/benchmarks/plots/fig_prompt_schema_fidelity_<TIMESTAMP>.png`
6. **DCR Self-Healing Trajectory Curves**: Saved as `research_paper/benchmarks/plots/fig_dcr_convergence_<TIMESTAMP>.png`
7. **Material Economy Bar Chart**: Saved as `research_paper/benchmarks/plots/fig_material_economy_<TIMESTAMP>.png`
8. **CHR vs. Claim Completeness Paired Bar Chart**: Saved as `research_paper/benchmarks/plots/fig_chr_vs_completeness_<TIMESTAMP>.png`

---

## Re-running a Single Specific Case & In-Place Update

To re-run a specific case (e.g. after debugging a tool or connection) and update an existing timestamped results file:

```powershell
# 1. List existing results to find the timestamped file you wish to update:
ls research_paper/benchmarks/results/

# 2. Re-run the individual case and update the file in-place:
python "research_paper/benchmarks/run_benchmarks.py" `
  --model gemini-3.8-flash `
  --config full_agent `
  --cases C03 `
  --update-file "research_paper/benchmarks/results/results_gemini-3.8-flash_full_agent_<TIMESTAMP>.json"
```
