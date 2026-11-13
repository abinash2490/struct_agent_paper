# Benchmark Commands

The commands that produced the results of the paper **"Explicit engineering knowledge in large language model agents for reinforced concrete frame design: a neuro-symbolic architecture and oracle-based evaluation"**, and the commands that
score, audit, and analyze them. Run them from the repository root (the folder that holds `research_paper/` and the
packages).

---

## Setup

### Models

| Model | Host | Notes |
|---|---|---|
| `gemma4:31b-cloud` | Ollama Cloud | 31B; reasons only when `reasoning_effort` is sent (the harness always sends it) |
| `minimax-m3.1-flash:cloud` | Ollama Cloud | 428B total; long reasoning: single-shot answers took 43k–130k tokens |
| `deepseek-v4.1-flash:cloud` | Ollama Cloud | 763B total |
| `mistral-large-4:cloud` | Ollama Cloud | 1.05T total (~52B active) |

All four are reasoning models and receive `reasoning_effort="high"` (`--reasoning-effort`, default `high`).

### Configurations

* `heuristic`: no LLM. Square columns b = h = H/20, beams b = 0.30 m and h = max(L/12, ℓ/18.5), within the
  prompt's minimums and limits, scaled by √DCR after each oracle check that fails (up to 6 checks).
* `full_agent`: the agent with all tools and the resizing loop.
* `ablated`: the agent without the resizing loop: `modify_project` is not offered, the system prompt has a report
  stage instead of the resizing stage (`allow_resizing=False`), and `allow_model_recreation=False` blocks model
  re-creation and `preliminary_sizing` after a design check.
* `direct_llm`: one call, answer as JSON, no tools.
* `code_gen`: one call, a standalone Python script (numpy/scipy) that prints the JSON answer. The script runs in a fresh workspace for at most 10 min (`run_benchmarks.SCRIPT_TIME_LIMIT`; 120 s before 2026-11-12).

### Seed and temperature

The paper uses one run per case and configuration, seed 42.

* **All LLM runs use temperature 0.2.** The harness defaults to 0.2 for all LLM configurations (`full_agent`, `ablated`, `direct_llm`, `code_gen`), and 0.0 for the deterministic heuristic.
* `--seeds N` runs seeds 42 … 41 + N. A second seed is added to an existing file with
  `--seeds 2 --temperature 0.2 --update-file <file> --resume` (the seeds already in the file are skipped).

### Environment and server

```powershell
conda activate structeng
```

For Ollama, the context window must hold at least 65,536 tokens: the agent's first request (system prompt and tool
schemas) is about 12k tokens, and Ollama's OpenAI-compatible endpoint silently cuts prompts beyond the window. Quit
the Ollama tray app first, then:

```powershell
$env:OLLAMA_CONTEXT_LENGTH = "65536"
$env:OLLAMA_FLASH_ATTENTION = "1"      # smaller KV cache, so more layers stay on the GPU
$env:OLLAMA_KV_CACHE_TYPE = "q8_0"
ollama serve
```

`run_benchmarks.py` checks the loaded model's window before an Ollama run and stops below `--min-context` (default
65536). A run that the window still cuts, or that the server ends with an error, is a setup failure
(`context_limit`, `provider_error`): re-run it with `--update-file <file> --resume`, which runs only missing and
setup-failed cases. A response cut at `--max-output-tokens` (default 131072, reasoning included), or by the window
after 32k or more tokens, is the model's failure (`runaway_generation`) and is not re-run. `--timeout` (default
1800 s per request) must exceed the time a runaway takes. Each run works in its own temporary workspace, so
campaigns of different models can run at the same time.

---

## Runs

```powershell
$R = "research_paper/benchmarks/run_benchmarks.py"

# Deterministic heuristic (no LLM)
python $R --config heuristic --cases all

# Each model: the two agent configurations, then the two single-shot baselines
foreach ($m in "gemma4:31b-cloud", "minimax-m3.1-flash:cloud", "deepseek-v4.1-flash:cloud", "mistral-large-4:cloud") {
    python $R --model $m --config full_agent --cases all --seeds 1 --temperature 0.2
    python $R --model $m --config ablated    --cases all --seeds 1 --temperature 0.2
    python $R --model $m --config direct_llm --cases all --seeds 1
    python $R --model $m --config code_gen   --cases all --seeds 1
}
```

`--cases` takes `all`, a group (`A_2D`, `B_3D`, `C_Multimodal`, `D_Robustness`), or case IDs or prefixes
(`A05,C03`). The paper's campaigns ran the cases in three chunks (A01–B02, B03–C03, C04–D04), the later chunks
with `--update-file <file> --resume`; the result is the same file as one `--cases all` run. A run stopped by a usage
limit of the Ollama plan is continued the same way.

To re-run one case and replace its record in an existing file:

```powershell
python $R --model gemma4:31b-cloud --config full_agent --cases C03 --seeds 1 --temperature 0.2 `
  --update-file "research_paper/benchmarks/results/results_gemma4_31b-cloud_full_agent_<TIMESTAMP>.json"
```

---

## Consistency Audit (after every agent run)

Replays each verified, fidelity-passing design from its tool log (no LLM calls) and flags runs whose final design check disagrees with the oracle (`oracle`), does not replay (`replay`), or used an analysis of an earlier state of the model (`stale`). A flag points to a harness or tool bug, not to an agent mistake. Resolve every flag before reporting. Results produced before a scoring change are re-scored first (`rescore_results.py <file> --replay`, which also recomputes PSFR and the verification of the final design check):

```powershell
python "research_paper/benchmarks/rescore_results.py" research_paper/benchmarks/results/results_<model>_<config>_<timestamp>.json --replay
python "research_paper/benchmarks/audit_results.py" research_paper/benchmarks/results/results_<model>_<config>_<timestamp>.json
```

## Analysis, Tables, and Figures

`analyze_results.py` aggregates the results files, runs the paired tests (exact McNemar for compliance, exact Wilcoxon signed-rank for the DCR and runtime), prints the summary and failure-mode tables, and writes diagnostic plots to `research_paper/benchmarks/plots/`:

```powershell
python "research_paper/benchmarks/analyze_results.py"
```

The manuscript's tables, figures, and Supplementary Material S1 are written by four scripts:

```powershell
python "research_paper/benchmarks/export_case_table.py"      # Table 3
python "research_paper/benchmarks/export_result_tables.py"   # Tables 7-12
python "research_paper/benchmarks/make_result_figures.py"    # Figures 2-5 (PNG and PDF)
python "research_paper/benchmarks/export_system_prompts.py"  # Supplementary Material S1 (system prompts)
```

They write into `research_paper/manuscript/`, which is not part of this repository.

## Zenodo Archive

The two files of the Zenodo deposit (the run records, and the code of every repository at one git tag) are built by:

```powershell
python "research_paper/benchmarks/make_zenodo_archive.py" --tag v1.0-paper
```

It writes `research_paper/zenodo_upload/struct_agent_benchmark_results.zip` and
`research_paper/zenodo_upload/struct_agent_code_v1.0-paper.zip`, and stops if a repository lacks the tag.
