# Experimental Benchmarking Plan & Evaluation Protocol

**Paper Title**: *A Neuro-Symbolic Agentic Framework for Autonomous Structural Modeling, Code-Compliant Design, and Detailing from Multimodal Inputs*  
**Target Venue**: *Automation in Construction* / *Advanced Engineering Informatics*  
**Companion Blueprint**: `research_paper/paper_idea.md`  

---

## 1. Experimental Objectives

The experimental campaign is designed to rigorously test Hypotheses H1–H3 across five core dimensions:
1. **Numerical Parity & Solver Trust**: Verifying that the deterministic symbolic solvers (`fem2d`, `fem3d`, `structdyn`, `aci318`) match commercial CSI SAP2000/ETABS and analytical benchmarks within $<0.5\%$.
2. **Determinism & Hallucination Elimination (H1)**: Confirming a $0.0\%$ Calculation Hallucination Rate ($\text{CHR}$ over claims made) with high claim completeness ($\text{CCR}_{\text{claims}}$) compared to direct zero-shot LLM prompting and raw script generation.
3. **Self-Healing Convergence (H2)**: Measuring the ability of the closed-loop reflection mechanism to autonomously resize initially failing or overstressed structural members ($\text{DCR}_0 > 1.0 \rightarrow \text{DCR}_{\text{final}} \le 1.0$) under static, Response Spectrum, and earthquake time-history loading.
4. **Multi-Model Generalization (H3)**: Evaluating robustness across frontier closed-source APIs (`gemini-3.8-flash`) and local/cloud open-weight models (`qwen3.5:9b`, `nemotron-3-super:cloud`, `gemma4:31b-cloud`).
5. **Design Quality & Material Economy (H2)**: Comparing the agent's converged concrete volumes ($V_{\text{concrete}}^{\text{agent}}$) and turnaround times against verified ACI 318-compliant human baseline designs ($V_{\text{concrete}}^{\text{baseline}}$).

---

## 2. Standardized 24-Case Benchmark Suite (`benchmark_cases.json`)

The benchmark suite consists of **24 structural engineering problems** divided into three progressive groups (16 cases requiring full ACI 318 code compliance verification and 8 cases evaluating pure modal dynamics, 3D kinematics, vision compilation, or CAE round-trip interoperability):

### Group A: 2D Plane Frames (8 Cases) — Gravity, Modal Dynamics & Response Spectrum
* **A01 (`A01_Portal_Frame_Office`)**: Single-Bay RC Portal Frame ($L=6.0\text{ m}, H=3.5\text{ m}$) under ASCE 7 office gravity loads ($w_{\text{trib}}=4.0\text{ m}$), fixed base, ACI 318 design, and production DXF drawing generation saved to `research_paper/drawings/A01_portal_frame.dxf` ($V_{\text{base}} = 1.757\text{ m}^3, \text{DCR}_{\text{base}} = 0.846$).
* **A02 (`A02_Portal_Frame_Storage`)**: Wide-Span Portal Frame ($L=8.0\text{ m}, H=4.0\text{ m}$) under heavy industrial storage gravity loads ($w_{\text{trib}}=4.5\text{ m}$) and ACI 318 checks ($V_{\text{base}} = 3.820\text{ m}^3, \text{DCR}_{\text{base}} = 0.864$).
* **A03 (`A03_2Bay_2Story_Office`)**: 2-Bay 2-Story RC Moment Frame ($L=5.0\text{ m}, H=3.2\text{ m}$) under office gravity loads ($w_{\text{trib}}=5.0\text{ m}$) and ACI 318 verification ($V_{\text{base}} = 5.772\text{ m}^3, \text{DCR}_{\text{base}} = 0.599$).
* **A04 (`A04_2Bay_3Story_Residential`)**: 2-Bay 3-Story Frame ($L=6.0\text{ m}, H=3.0\text{ m}$) under residential gravity loads ($w_{\text{trib}}=4.5\text{ m}$) and ACI 318 design ($V_{\text{base}} = 9.720\text{ m}^3, \text{DCR}_{\text{base}} = 0.677$).
* **A05 (`A05_2D_Modal_Dynamics`)**: 2-Bay 3-Story Frame ($L=6.0\text{ m}, H=3.5\text{ m}$) eigenvalue modal analysis extracting fundamental periods ($T_1, T_2, T_3$) and mode shapes via `structdyn`.
* **A06 (`A06_2D_Response_Spectrum_ASCE7`)**: 2-Bay 3-Story Frame ($L=6.0\text{ m}, H=3.5\text{ m}$) Response Spectrum Analysis (RSA) using ASCE 7 design spectrum ($S_{DS}=1.0g, S_{D1}=0.6g$), CQC modal combination, gravity enveloping, and ACI 318 checks ($V_{\text{base}} = 13.309\text{ m}^3, \text{DCR}_{\text{base}} = 0.880$).
* **A07 (`A07_2D_RSA_Ground_Motion`)**: 3-Bay 4-Story Frame ($L=5.5\text{ m}, H=3.5\text{ m}$) Response Spectrum Analysis computed from the 1994 Northridge ground motion record with CQC combination and ACI 318 checks ($V_{\text{base}} = 26.705\text{ m}^3, \text{DCR}_{\text{base}} = 0.880$).
* **A08 (`A08_2D_Overstressed_Portal_Reflection`)**: Self-Healing Reflection benchmark on a 1-bay 1-story frame ($L=7.0\text{ m}, H=3.5\text{ m}$) deliberately initialized with undersized members ($0.30\times0.30\text{ m}$ columns, $0.30\times0.45\text{ m}$ beams; initial $\text{DCR}_0 = 3.952 > 1.0$) under heavy storage loads ($w_{\text{trib}}=6.0\text{ m}$), testing autonomous resizing via `modify_project` until $\text{DCR} \le 1.0$ followed by DXF CAD generation saved to `research_paper/drawings/A08_portal_frame.dxf` ($V_{\text{base}} = 3.710\text{ m}^3, \text{DCR}_{\text{base}} = 0.797$).

### Group B: 3D Space Frames (8 Cases) — 3D Biaxial Gravity, Seismic ELF & 3D RSA
* **B01 (`B01_3D_2x2_2Story_Gravity`)**: 3D Space Frame (2x2, 2-Story Gravity): $2 \times 2$ bays at $6.0\text{ m}$, 2 stories at $3.5\text{ m}$, under residential floor gravity loads, LRFD combinations, and 3D direct stiffness analysis.
* **B02 (`B02_3D_3x2_3Story_Gravity`)**: 3D Space Frame ($3 \times 2$ bays at $5.0\text{ m} \times 6.0\text{ m}$, 3 stories at $3.2\text{ m}$) under office gravity loads with 3D biaxial column checks ($V_{\text{base}} = 65.178\text{ m}^3, \text{DCR}_{\text{base}} = 0.846$).
* **B03 (`B03_3D_2x2_Seismic_ELF`)**: 3D Space Frame ($2 \times 2$ bays at $6.0\text{ m}$, 3 stories at $3.5\text{ m}$) under ASCE 7 Seismic Equivalent Lateral Force (ELF) ($S_{DS} = 1.2g, S_{D1} = 0.5g$, $R=5.0$) and 3D Bresler P-M2-M3 interaction checks ($V_{\text{base}} = 143.100\text{ m}^3, \text{DCR}_{\text{base}} = 0.983$).
* **B04 (`B04_3D_Modal_Dynamics`)**: 3D Space Frame ($2 \times 2$ bays, 3 stories) 3D modal eigenvalue analysis extracting translational/torsional periods and modal mass participation factors.
* **B05 (`B05_3D_Response_Spectrum_X`)**: 3D Space Frame ($2 \times 2$ bays, 3 stories) Response Spectrum Analysis along the X-direction per ASCE 7 ($S_{DS}=1.1g, S_{D1}=0.55g$) with CQC combination and biaxial ACI 318 checks ($V_{\text{base}} = 116.640\text{ m}^3, \text{DCR}_{\text{base}} = 0.866$).
* **B06 (`B06_3D_Response_Spectrum_MultiDir`)**: 3D Space Frame ($3 \times 2$ bays, 3 stories) multi-directional Response Spectrum Analysis (X and Y) under the 1940 El Centro spectrum with CQC combination and biaxial checks ($V_{\text{base}} = 82.508\text{ m}^3, \text{DCR}_{\text{base}} = 0.880$).
* **B08 (`B08_3D_BiDirectional_Seismic`)**: 3D Space Frame (3 stories, 2x2 bays @ 6.0 m) under bi-directional orthogonal seismic loading ($1.0 E_X \pm 0.3 E_Y$ per ASCE 7-22), evaluating corner column biaxial demands and ACI 318 design ($V_{\text{base}} = 113.636\text{ m}^3, \text{DCR}_{\text{base}} = 0.940$).

### Group C: Advanced Dynamic, Multimodal Vision, CAE & CAD Pipelines (8 Cases)
* **C01 (`C01_Dynamics_ElCentro_TimeHistory`)**: 2D 2-Bay 3-Story Frame dynamic earthquake time-history analysis under the 1940 El Centro record via Newmark-Beta integration in `structdyn`, extracting peak roof displacement, acceleration, and base shear time series.
* **C02 (`C02_Dynamics_Northridge_TimeHistory`)**: 3D $2 \times 2$ Bay 2-Story Space Frame direct numerical time-history integration under the 1994 Northridge record, extracting peak floor acceleration, drift history, and base shear time series.
* **C03 (`C03_CAE_SAP2000_RoundTrip`)**: CSI SAP2000 CAE round-trip interoperability importing `exported_seismic_frame.s2k` (`research_paper/benchmarks/fixtures/exported_seismic_frame.s2k`), validating geometry, executing linear static FEA and ACI 318 checks, and re-exporting to `.s2k` as `research_paper/benchmarks/results/exported_sap2000.s2k`.
* **C04 (`C04_CAE_ETABS_RoundTrip`)**: CSI ETABS CAE round-trip interoperability importing `exported_seismic_frame.e2k` (`research_paper/benchmarks/fixtures/exported_seismic_frame.e2k`), verifying multi-story connectivity and boundary restraints, running analysis, and re-exporting to `.e2k` as `research_paper/benchmarks/results/exported_etabs.e2k`.
* **C05 (`C05_Vision_FloorPlan_Draft_Ingestion`)**: Multimodal architectural floor plan ingestion via `struct_agent.vision` using the 3-story school plan (`research_paper/benchmarks/fixtures/floor_plan_3story_school.PNG`), compiling a 3-story 3D structural frame (`create_model_from_plan_draft`) and verifying topological connectivity.
* **C06 (`C06_Vision_To_Seismic_Design_Pipeline`)**: End-to-end multimodal floor-plan-to-seismic design pipeline on the 4-story commercial mall (`research_paper/benchmarks/fixtures/mall_plan_4story.PNG`): compiling a 3D frame from floor plan specification $\rightarrow$ ASCE 7 seismic ELF loading ($S_{DS}=1.2g, S_{D1}=0.5g$) $\rightarrow$ 3D FEA $\rightarrow$ ACI 318 biaxial verification ($V_{\text{base}} = 165.728\text{ m}^3, \text{DCR}_{\text{base}} = 0.880$).
* **C07 (`C07_2D_Dynamic_Reflection`)**: Self-Healing Reflection on a 2-bay 3-story frame initialized with undersized trial sections ($0.30\times0.30\text{ m}$ columns, $0.30\times0.45\text{ m}$ beams; initial $\text{DCR}_0 = 2.590 > 1.0$) under high seismic lateral loads, iteratively resizing columns and re-analyzing until $\text{DCR} \le 1.0$ ($V_{\text{base}} = 14.805\text{ m}^3, \text{DCR}_{\text{base}} = 0.771$).
* **C08 (`C08_Full_Pipeline_Autonomous_CAD_Production`)**: Full autonomous seismic design-to-CAD pipeline on a 2-bay 2-story frame ($L=5.0\text{ m}, H=3.2\text{ m}$): gravity + ASCE 7 Response Spectrum Analysis $\rightarrow$ ACI 318 design $\rightarrow$ production AutoCAD `.dxf` drawings with rebar schedules saved to `research_paper/drawings/C08_seismic_frame.dxf` ($V_{\text{base}} = 6.072\text{ m}^3, \text{DCR}_{\text{base}} = 0.846$).

---

## 3. Quantitative Evaluation Metrics

Each benchmark execution is evaluated across five formal metrics:

### 3.1 Task Completion Rate ($\text{TCR}$)
$$\text{TCR} = \frac{N_{\text{completed}}}{N_{\text{total}}} \times 100\% \quad \left(N_{\text{total}} = 24\right)$$
A benchmark run is counted in $N_{\text{completed}}$ if and only if the agent constructs/imports a valid `struct_core.Project` model and successfully executes all required pipeline tools specified in `expected_tools` (analysis, design, CAD drawing generation, or CAE export) without fatal runtime exceptions.

### 3.2 Code Compliance Rate ($\text{CCR}$)
$$\text{CCR} = \frac{N_{\text{compliant}}}{N_{\text{design}}} \times 100\% \quad \left(N_{\text{design}} = 16\right)$$
Evaluated across the 16 benchmark cases requiring ACI 318 structural design. A completed design is code-compliant if and only if the governing demand-capacity ratio across all structural members $e \in \mathcal{E}$ and factored load combinations $c \in \mathcal{C}$ satisfies:
$$\text{DCR}_{\text{gov}} = \max_{e \in \mathcal{E}, \, c \in \mathcal{C}} \left\{ \frac{P_{u,e,c}}{\phi P_{n,e}}, \frac{M_{u,e,c}}{\phi M_{n,e}}, \frac{V_{u,e,c}}{\phi V_{n,e}} \right\} \le 1.00$$

> **Note on Governed Minimum Flexural Steel ($A_{s,\min}$)**:
> Several human baseline designs exhibit identical governing DCR values (e.g., $0.880$ for A06, A07, B06, C06 and $0.846$ for A01, B02, C08). Investigation confirms that for standard RC beam geometries ($350\times550\text{ mm}$ and $300\times500\text{ mm}$), the section capacity is governed by ACI 318-19/25 §9.6.1.2 minimum flexural steel reinforcement ($A_{s,\min} = \frac{3\sqrt{f'_c}}{f_y} b_w d \ge \frac{200 b_w d}{f_y}$). Because reinforcement is pinned to code minimum steel requirements ($A_{s,\text{prov}} = A_{s,\min}$), the resulting ratio is deterministic and identical across distinct load cases where minimum reinforcement governs.

### 3.3 Calculation Hallucination Rate ($\text{CHR}$) and Claim Completeness ($\text{CCR}_{\text{claims}}$)
$$\text{CHR} = \frac{N_{\text{hallucinated\_claims}}}{N_{\text{claims\_made}}} \times 100\%$$
Measures the percentage of asserted engineering quantities that deviate by $>10.0\%$ from the exact deterministic mechanics solution:
$$\frac{|X_{\text{claimed}} - X_{\text{oracle}}|}{\max(|X_{\text{oracle}}|, 10^{-4})} > 0.10 \quad (>10.0\% \text{ discrepancy})$$
To evaluate precision over asserted claims without conflating omission with mathematical hallucination, $\text{CHR}$ evaluates only quantities explicitly claimed by the model ($N_{\text{claims\_made}}$). To prevent models from artificially suppressing hallucination rates by omitting complex physical quantities, we simultaneously report the **Claim Completeness Rate** ($\text{CCR}_{\text{claims}}$):
$$\text{CCR}_{\text{claims}} = \frac{|\,N_{\text{claims\_made}} \cap N_{\text{expected\_metrics}}\,|}{N_{\text{expected\_metrics}}} \times 100\%$$
where $N_{\text{expected\_metrics}} = N_{\text{active\_metrics}} \cup N_{\text{required\_metrics}}$, with $N_{\text{active\_metrics}}$ representing regime-specific physical mechanics (total dead weight $W$, lateral base shear $V_b$, fundamental period $T_1$, governing DCR) and $N_{\text{required\_metrics}}$ capturing prompt-mandated quantities (such as higher mode periods $T_2, T_3$, modal mass participation ratios, and peak displacements for modal and time-history benchmarks A05, B04, C01, C02, C03, C04). Tool-augmented agents systematically achieve $0.0\%$ $\text{CHR}$ because reported quantities originate directly from verified solver telemetry.

### 3.4 Self-Healing Convergence Iterations ($N_{\text{iter}}$)
For cases where the initial trial design is overstressed ($\text{DCR}_{\text{gov}}^{(0)} > 1.0$), $N_{\text{iter}}$ records the number of closed-loop reflection cycles (`modify_project` $\rightarrow$ `run_analysis`/`run_time_history` $\rightarrow$ `run_design`) required to achieve $\text{DCR}_{\text{gov}}^{(N_{\text{iter}})} \le 1.0$.

### 3.5 Volumetric Material Economy Ratio ($\eta_{\text{vol}}$) and Design Efficiency
$$\eta_{\text{vol}} = \frac{V_{\text{concrete}}^{\text{agent}}}{V_{\text{concrete}}^{\text{baseline}}}$$
$$\text{Design Efficiency} = \frac{V_{\text{concrete}}^{\text{baseline}}}{V_{\text{concrete}}^{\text{agent}}} = \frac{1}{\eta_{\text{vol}}}$$
Evaluated on code-compliant designs ($\text{DCR}_{\text{gov}} \le 1.0$), where $V_{\text{concrete}} = \sum_{e \in \mathcal{E}} A_e L_e$ is the total structural concrete volume ($\text{m}^3$) and $V_{\text{concrete}}^{\text{baseline}}$ is the verified human engineering baseline volume generated by `generate_human_baselines.py`. Values of $\eta_{\text{vol}} \approx 0.95\text{--}1.05$ indicate that the agent achieves human-level material efficiency without gross over-sizing; efficiency values $> 1.0$ indicate that the agent identified a lighter, structurally compliant framing configuration than the human baseline.

### 3.6 Prompt-to-Schema Fidelity Rate ($\text{PSFR}$)
$$\text{PSFR} = \frac{N_{\text{faithful}}}{N_{\text{evaluated}}} \times 100\%$$
Measures the fidelity of the agent's synthesized project schema against prompt-specified structural and mechanical requirements without argument hallucination. A run satisfies $\text{PSFR}$ if and only if all eight physical criteria are simultaneously met:
1. **Dimensionality**: Strict 2D ($z=0$) vs. 3D space frame compliance.
2. **Story Count & Spacing**: Exact match of elevated floor levels.
3. **Bay Counts & Grid Layout**: Exact match of bay counts in X (and Y for 3D).
4. **Bay Spans & Story Heights**: Column spacings and floor-to-floor heights match prompt dimensions within $\pm 0.15\text{ m}$.
5. **Boundary Restraints**: Complete fixed support boundary conditions assigned to all ground-level nodes.
6. **Material Mechanical Validity**: Assignment of standard structural concrete elastic material properties ($E \in [15, 45]\text{ GPa}$, density $\rho \ge 2000\text{ kg/m}^3$).
7. **Seismic Coefficients**: Parameter fidelity for spectral acceleration coefficients ($S_{DS}, S_{D1}$) within $\pm 0.05$ and response modification coefficient $R$ within $\pm 0.5$ on lateral seismic cases.
8. **Gravity Load Cases**: Conforming population of dead and live load cases with non-zero member/area pressures.

---

## 4. Experimental Configurations & Multi-Model Matrix

### 4.1 Comparative Configurations & Turn Budget
| Configuration ID | CLI Flag (`--config`) | Turn Budget | Description & Role in Ablation Study |
|---|---|:---:|---|
| **Baseline 0: Deterministic Heuristic** | `heuristic` | 1 | Non-LLM deterministic rules of thumb ($h_c=b_c=0.05H$, $b_b=L/14, h_b=L/12$) with DCR-proportional scaling ($\sqrt{\text{DCR}}$); establishes the non-LLM engineering floor. |
| **Baseline 1: Direct Zero-Shot LLM** | `direct_llm` | 1 | Raw LLM prompting without symbolic tools; quantifies baseline mathematical error and Calculation Hallucination Rate ($\text{CHR}$). |
| **Baseline 2: Code-Generation LLM** | `code_gen` | 1 | Prompts the LLM to write raw standalone Python/NumPy FEA and design scripts from scratch; measures syntax/convergence failures. |
| **Baseline 3: Ablated Agent (No Reflection)** | `ablated` | $\le 20$ | Full neuro-symbolic tool suite enabled, but closed-loop reflection (`modify_project`) is removed from the tool registry and `allow_model_recreation=False` strictly enforces single-pass execution; isolates the impact of self-healing on $\text{CCR}$. |
| **Proposed: Full Neuro-Symbolic Agent** | `full_agent` | $\le 20$ | Complete ontology-grounded agent with multimodal perception, symbolic solvers, and autonomous self-healing reflection loop. |

> **Turn Budget & Confound Control**:
> The `full_agent` and `ablated` configurations are allocated up to 20 dialogue turns to enable multi-step tool orchestration, stateful error recovery, and iterative member resizing. In contrast, `direct_llm`, `code_gen`, and `heuristic` represent single-shot baselines (1 turn), reflecting standard baseline practice. To prevent equifinality and self-weight bias from confounding the comparison, all baselines are evaluated on identical candidate sections via the deterministic `OracleVerifier`.

### 4.2 Evaluated LLM Backbones
| Model Identifier | Architecture & Provider | Scale | Deployment Modality | Endpoint / Authentication |
|---|---|---|---|---|
| **`gemini-3.8-flash`** | Frontier Closed-Source (Google DeepMind) | Proprietary | Cloud API | `GEMINI_API_KEY` loaded from `struct_agent/.env` |
| **`qwen3.5:9b`** | Open-Weight Dense Multimodal (Alibaba Qwen) | 9B | Local Workstation (Ollama) | `http://localhost:11434/v1` |
| **`nemotron-3-super:cloud`** | Open-Weight Math/Reasoning-Tuned (NVIDIA) | Cloud Host | Cloud Ollama / API Host | `OLLAMA_HOST` environment variable |
| **`gemma4:31b-cloud`** | Open-Weight High-Capacity Frontier (Google DeepMind) | 31B | Cloud Host via Ollama / API | `OLLAMA_HOST` environment variable |

---

## 5. Step-by-Step Reproducibility Protocol

### Step 1: Activate Environment & Verify Baselines
```powershell
conda activate structeng
python "research_paper/benchmarks/generate_human_baselines.py"
```

### Step 2: Execute Benchmark Campaigns (Multi-Seed Protocol)
Per the reproducibility protocol, multi-turn agent configurations (`full_agent`, `ablated`) are executed with `--seeds 5` (repeating across random seeds 42, 43, 44, 45, 46 via `--temperature 0.2` to generate authentic stochastic variance for paired Wilcoxon signed-rank significance testing). Single-shot baselines (`heuristic`, `direct_llm`, `code_gen`) run with `--seeds 1` at `--temperature 0.0`:

```powershell
# 0. Deterministic Heuristic Baseline (Non-LLM Floor):
python "research_paper/benchmarks/run_benchmarks.py" --config heuristic --cases all

# 1. Google Gemini 3.8 Flash (Full Agent vs. Ablated, 5 seeds):
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --config full_agent --cases all --seeds 5 --temperature 0.2
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --config ablated --cases all --seeds 5 --temperature 0.2
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --config direct_llm --cases all --seeds 1 --temperature 0.0
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --config code_gen --cases all --seeds 1 --temperature 0.0

# 2. Local Qwen 3.5 9B (Full Agent vs. Ablated, 5 seeds):
python "research_paper/benchmarks/run_benchmarks.py" --model qwen3.5:9b --config full_agent --cases all --seeds 5 --temperature 0.2
python "research_paper/benchmarks/run_benchmarks.py" --model qwen3.5:9b --config ablated --cases all --seeds 5 --temperature 0.2

# 3. Cloud Nemotron-3 Super (Full Agent vs. Ablated, 5 seeds):
python "research_paper/benchmarks/run_benchmarks.py" --model nemotron-3-super:cloud --config full_agent --cases all --seeds 5 --temperature 0.2
python "research_paper/benchmarks/run_benchmarks.py" --model nemotron-3-super:cloud --config ablated --cases all --seeds 5 --temperature 0.2

# 4. Cloud Gemma 4 31B (Full Agent vs. Ablated, 5 seeds):
python "research_paper/benchmarks/run_benchmarks.py" --model gemma4:31b-cloud --config full_agent --cases all --seeds 5 --temperature 0.2
python "research_paper/benchmarks/run_benchmarks.py" --model gemma4:31b-cloud --config ablated --cases all --seeds 5 --temperature 0.2
```

### Step 3: Compile Telemetry Tables, Significance Tests & Publication Figures

```powershell
python "research_paper/benchmarks/analyze_results.py"
```

This script processes all timestamped JSON logs in `research_paper/benchmarks/results/` (without overwriting prior runs) and outputs:

* `results/summary_table_<timestamp>.md`: Summary table of $\text{TCR}$, $\text{CCR}$, $\text{CHR}$, $N_{\text{iter}}$, $\eta_{\text{vol}}$, and runtime with mean $\pm$ standard deviation across seeds.
* `results/failure_mode_breakdown_<timestamp>.md`: Formal failure-mode taxonomy categorizing failure root causes (`model_construction`, `missing_tool`, `dcr_non_convergence`, `schema_fidelity`, `artifact_missing`).
* **Paired Wilcoxon Signed-Rank Tests**: Statistical significance testing between `full_agent` and `ablated` configurations for $\text{TCR}$, $\text{CCR}$, governing $\text{DCR}$, and runtime.
* `plots/fig_benchmark_comparison_<timestamp>.png`: 300 DPI grouped bar chart of $\text{TCR}$ and $\text{CCR}$.
* `plots/fig_dcr_convergence_<timestamp>.png`: 300 DPI self-healing $\text{DCR}$ vs. iteration trajectories.
* `plots/fig_material_economy_<timestamp>.png`: 300 DPI volumetric concrete economy comparison against the $\eta_{\text{vol}} = 1.00$ human baseline.
* `plots/fig_prompt_schema_fidelity_<timestamp>.png`: 300 DPI Prompt-to-Schema Fidelity Rate ($\text{PSFR}$) comparison across configurations.
