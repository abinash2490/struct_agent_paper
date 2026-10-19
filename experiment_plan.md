# Experimental Benchmarking Plan & Evaluation Protocol

**Paper Title**: *A Neuro-Symbolic Agentic Framework for Autonomous Structural Modeling, Code-Compliant Design, and Detailing from Multimodal Inputs*  
**Target Venue**: *Automation in Construction* / *Advanced Engineering Informatics*  
**Companion Blueprint**: `research_paper/paper_idea.md`  

---

## 1. Experimental Objectives

The experimental campaign is designed to rigorously test Hypotheses H1–H3 across five core dimensions:
1. **Numerical Parity & Solver Trust**: Verifying that the deterministic symbolic solvers (`fem2d`, `fem3d`, `structdyn`, `aci318`) match commercial CSI SAP2000/ETABS and analytical benchmarks within $<0.5\%$.
2. **Determinism & Hallucination Elimination (H1)**: Confirming a $0.0\%$ Calculation Hallucination Rate ($\text{CHR}$) compared to direct zero-shot LLM prompting and raw script generation.
3. **Self-Healing Convergence (H2)**: Measuring the ability of the closed-loop reflection mechanism to autonomously resize initially failing or overstressed structural members ($\text{DCR}_0 > 1.0 \rightarrow \text{DCR}_{\text{final}} \le 1.0$) under static, Response Spectrum, and earthquake time-history loading.
4. **Multi-Model Generalization (H3)**: Evaluating robustness across frontier closed-source APIs (`gemini-3.8-flash`) and local/cloud open-weight models via Ollama (`qwen3.5:9b`, `gpt-oss:120b-cloud`, `nemotron-3-ultra:cloud`).
5. **Design Quality & Material Economy (H2)**: Comparing the agent's converged concrete volumes ($V_{\text{concrete}}^{\text{agent}}$) and turnaround times against verified ACI 318-compliant human baseline designs ($V_{\text{concrete}}^{\text{baseline}}$).

---

## 2. Standardized 24-Case Benchmark Suite (`benchmark_cases.json`)

The benchmark suite consists of **24 structural engineering problems** divided into three progressive groups (18 cases requiring full ACI 318 code compliance verification and 6 cases evaluating pure modal dynamics, 3D kinematics, vision compilation, or CAE round-trip interoperability):

### Group A: 2D Plane Frames (8 Cases) — Gravity, Modal Dynamics & Response Spectrum
* **A01 (`A01_Portal_Frame_Office`)**: Single-Bay RC Portal Frame ($L=6.0\text{ m}, H=3.5\text{ m}$) under ASCE 7 office gravity loads ($w_{\text{trib}}=4.0\text{ m}$), fixed base, ACI 318 design, and production DXF drawing generation saved to `research_paper/drawings/A01_portal_frame.dxf` ($V_{\text{base}} = 1.757\text{ m}^3, \text{DCR}_{\text{base}} = 0.846$).
* **A02 (`A02_Portal_Frame_Storage`)**: Wide-Span Portal Frame ($L=8.0\text{ m}, H=4.0\text{ m}$) under heavy industrial storage gravity loads ($w_{\text{trib}}=4.5\text{ m}$) and ACI 318 checks ($V_{\text{base}} = 3.820\text{ m}^3, \text{DCR}_{\text{base}} = 0.864$).
* **A03 (`A03_2Bay_2Story_Office`)**: 2-Bay 2-Story RC Moment Frame ($L=5.0\text{ m}, H=3.2\text{ m}$) under office gravity loads ($w_{\text{trib}}=5.0\text{ m}$) and ACI 318 verification ($V_{\text{base}} = 5.772\text{ m}^3, \text{DCR}_{\text{base}} = 0.599$).
* **A04 (`A04_2Bay_3Story_Residential`)**: 2-Bay 3-Story Frame ($L=6.0\text{ m}, H=3.0\text{ m}$) under residential gravity loads ($w_{\text{trib}}=4.5\text{ m}$) and ACI 318 design ($V_{\text{base}} = 9.720\text{ m}^3, \text{DCR}_{\text{base}} = 0.677$).
* **A05 (`A05_2D_Modal_Dynamics`)**: 2-Bay 3-Story Frame ($L=6.0\text{ m}, H=3.5\text{ m}$) eigenvalue modal analysis extracting fundamental periods ($T_1, T_2, T_3$) and mode shapes via `structdyn`.
* **A06 (`A06_2D_Response_Spectrum_ASCE7`)**: 2-Bay 3-Story Frame ($L=6.0\text{ m}, H=3.5\text{ m}$) Response Spectrum Analysis (RSA) using ASCE 7 design spectrum ($S_{DS}=1.0g, S_{D1}=0.6g$), CQC modal combination, gravity enveloping, and ACI 318 checks ($V_{\text{base}} = 13.309\text{ m}^3, \text{DCR}_{\text{base}} = 0.880$).
* **A07 (`A07_2D_RSA_Ground_Motion`)**: 3-Bay 4-Story Frame ($L=5.5\text{ m}, H=3.5\text{ m}$) Response Spectrum Analysis computed from the 1994 Northridge ground motion record with CQC combination and ACI 318 checks ($V_{\text{base}} = 26.705\text{ m}^3, \text{DCR}_{\text{base}} = 0.880$).
* **A08 (`A08_2D_Overstressed_Portal_Reflection`)**: Self-Healing Reflection benchmark on a 1-bay 1-story frame ($L=7.0\text{ m}, H=3.5\text{ m}$) deliberately initialized with undersized members ($0.25\times0.25\text{ m}$ columns, $0.25\times0.30\text{ m}$ beams) under heavy storage loads ($w_{\text{trib}}=6.0\text{ m}$), testing autonomous resizing via `modify_project` until $\text{DCR} \le 1.0$ followed by DXF CAD generation saved to `research_paper/drawings/A08_portal_frame.dxf` ($V_{\text{base}} = 3.710\text{ m}^3, \text{DCR}_{\text{base}} = 0.797$).

### Group B: 3D Space Frames (8 Cases) — 3D Biaxial Gravity, Seismic ELF & 3D RSA
* **B01 (`B01_3D_2x2_2Story_Office`)**: 3D Space Frame (2-Story Hostel Block Plan): $2 \times 2$ bays at $6.0\text{ m}$, 2 stories at $3.5\text{ m}$, based on the 2-story hostel block framing plan (`research_paper/benchmarks/fixtures/hostel_block_plan_2 story.PNG`) under residential floor gravity loads, LRFD combinations, and 3D direct stiffness analysis.
* **B02 (`B02_3D_3x2_3Story_Gravity`)**: 3D Space Frame ($3 \times 2$ bays at $5.0\text{ m} \times 6.0\text{ m}$, 3 stories at $3.2\text{ m}$) under office gravity loads with 3D biaxial column checks ($V_{\text{base}} = 85.104\text{ m}^3, \text{DCR}_{\text{base}} = 0.846$).
* **B03 (`B03_3D_2x2_Seismic_ELF`)**: 3D Space Frame ($2 \times 2$ bays at $6.0\text{ m}$, 3 stories at $3.5\text{ m}$) under ASCE 7 Seismic Equivalent Lateral Force (ELF) ($S_{DS} = 1.2g, S_{D1} = 0.5g$, $R=5.0$) and 3D Bresler P-M2-M3 interaction checks ($V_{\text{base}} = 143.100\text{ m}^3, \text{DCR}_{\text{base}} = 0.983$).
* **B04 (`B04_3D_Modal_Dynamics`)**: 3D Space Frame ($2 \times 2$ bays, 3 stories) 3D modal eigenvalue analysis extracting translational/torsional periods and modal mass participation factors.
* **B05 (`B05_3D_Response_Spectrum_X`)**: 3D Space Frame ($2 \times 2$ bays, 3 stories) Response Spectrum Analysis along the X-direction per ASCE 7 ($S_{DS}=1.1g, S_{D1}=0.55g$) with CQC combination and biaxial ACI 318 checks ($V_{\text{base}} = 116.640\text{ m}^3, \text{DCR}_{\text{base}} = 0.929$).
* **B06 (`B06_3D_Response_Spectrum_MultiDir`)**: 3D Space Frame ($3 \times 2$ bays, 3 stories) multi-directional Response Spectrum Analysis (X and Y) under the 1940 El Centro spectrum with CQC combination and biaxial checks ($V_{\text{base}} = 107.700\text{ m}^3, \text{DCR}_{\text{base}} = 0.948$).
* **B07 (`B07_3D_HighSeismic_Reflection`)**: 3D Space Frame ($2 \times 2$ bays, 2 stories) Self-Healing Reflection initialized with undersized columns ($0.35\times0.35\text{ m}$) under high seismic ELF loads ($\text{DCR}_0 > 1.3$), iteratively enlarging sections via `modify_project` until $\text{DCR} \le 1.0$ ($V_{\text{base}} = 56.857\text{ m}^3, \text{DCR}_{\text{base}} = 0.626$).
* **B08 (`B08_3D_Asymmetric_Seismic`)**: 3D Asymmetric Space Frame (3 stories) with plan irregularity and torsional eccentricity under bi-directional seismic loading, evaluating torsional drift amplification and corner column demands ($V_{\text{base}} = 113.636\text{ m}^3, \text{DCR}_{\text{base}} = 0.940$).

### Group C: Advanced Dynamic, Multimodal Vision, CAE & CAD Pipelines (8 Cases)
* **C01 (`C01_Dynamics_ElCentro_TimeHistory`)**: 2D 2-Bay 3-Story Frame dynamic earthquake time-history analysis under the 1940 El Centro record via Newmark-Beta integration in `structdyn`, peak internal force enveloping, and ACI 318 design ($V_{\text{base}} = 20.869\text{ m}^3, \text{DCR}_{\text{base}} = 0.951$).
* **C02 (`C02_Dynamics_Northridge_TimeHistory`)**: 3D $2 \times 2$ Bay 2-Story Space Frame direct numerical time-history integration under the 1994 Northridge record, extracting peak floor acceleration, drift history, and base shear time series.
* **C03 (`C03_CAE_SAP2000_RoundTrip`)**: CSI SAP2000 CAE round-trip interoperability importing `exported_seismic_frame.s2k` (`research_paper/benchmarks/fixtures/exported_seismic_frame.s2k`), validating geometry, executing linear static FEA and ACI 318 checks, and re-exporting to `.s2k` as `research_paper/benchmarks/results/exported_sap2000.s2k` ($V_{\text{base}} = 12.040\text{ m}^3, \text{DCR}_{\text{base}} = 0.740$).
* **C04 (`C04_CAE_ETABS_RoundTrip`)**: CSI ETABS CAE round-trip interoperability importing `exported_seismic_frame.e2k` (`research_paper/benchmarks/fixtures/exported_seismic_frame.e2k`), verifying multi-story connectivity and boundary restraints, running analysis, and re-exporting to `.e2k` as `research_paper/benchmarks/results/exported_etabs.e2k`.
* **C05 (`C05_Vision_FloorPlan_Draft_Ingestion`)**: Multimodal architectural floor plan ingestion via `struct_agent.vision` using the 3-story school plan (`research_paper/benchmarks/fixtures/floor_plan_3story_school.PNG`), compiling a 3-story 3D structural frame (`create_model_from_plan_draft`) and verifying topological connectivity.
* **C06 (`C06_Vision_To_Seismic_Design_Pipeline`)**: End-to-end multimodal floor-plan-to-seismic design pipeline on the 4-story commercial mall (`research_paper/benchmarks/fixtures/mall_plan_4story.PNG`): compiling a 3D frame from floor plan specification $\rightarrow$ ASCE 7 seismic ELF loading ($S_{DS}=1.2g, S_{D1}=0.5g$) $\rightarrow$ 3D FEA $\rightarrow$ ACI 318 biaxial verification ($V_{\text{base}} = 92.664\text{ m}^3, \text{DCR}_{\text{base}} = 0.866$).
* **C07 (`C07_Seismic_TimeHistory_Dynamic_Reflection`)**: Dynamic Self-Healing Reflection on a 2-bay 3-story frame initialized with undersized $0.30\times0.30\text{ m}$ columns under the 1940 El Centro time-history record ($\text{DCR}_0 > 1.20$), iteratively resizing columns and re-integrating equations of motion until $\text{DCR} \le 1.0$ ($V_{\text{base}} = 20.869\text{ m}^3, \text{DCR}_{\text{base}} = 0.951$).
* **C08 (`C08_Full_Pipeline_Autonomous_CAD_Production`)**: Full autonomous seismic design-to-CAD pipeline on a 2-bay 2-story frame ($L=5.0\text{ m}, H=3.2\text{ m}$): gravity + ASCE 7 Response Spectrum Analysis $\rightarrow$ ACI 318 design $\rightarrow$ production AutoCAD `.dxf` drawings with rebar schedules saved to `research_paper/drawings/C08_seismic_frame.dxf` ($V_{\text{base}} = 6.072\text{ m}^3, \text{DCR}_{\text{base}} = 0.846$).

---

## 3. Quantitative Evaluation Metrics

Each benchmark execution is evaluated across five formal metrics:

### 3.1 Task Completion Rate ($\text{TCR}$)
$$\text{TCR} = \frac{N_{\text{completed}}}{N_{\text{total}}} \times 100\% \quad \left(N_{\text{total}} = 24\right)$$
A benchmark run is counted in $N_{\text{completed}}$ if and only if the agent constructs/imports a valid `struct_core.Project` model and successfully executes all required pipeline tools specified in `expected_tools` (analysis, design, CAD drawing generation, or CAE export) without fatal runtime exceptions.

### 3.2 Code Compliance Rate ($\text{CCR}$)
$$\text{CCR} = \frac{N_{\text{compliant}}}{N_{\text{design}}} \times 100\% \quad \left(N_{\text{design}} = 18\right)$$
Evaluated across the 18 benchmark cases requiring ACI 318 structural design. A completed design is code-compliant if and only if the governing demand-capacity ratio across all structural members $e \in \mathcal{E}$ and factored load combinations $c \in \mathcal{C}$ satisfies:
$$\text{DCR}_{\text{gov}} = \max_{e \in \mathcal{E}, \, c \in \mathcal{C}} \left\{ \frac{P_{u,e,c}}{\phi P_{n,e}}, \frac{M_{u,e,c}}{\phi M_{n,e}}, \frac{V_{u,e,c}}{\phi V_{n,e}} \right\} \le 1.00$$

### 3.3 Calculation Hallucination Rate ($\text{CHR}$)
$$\text{CHR} = \frac{N_{\text{hallucinated\_claims}}}{N_{\text{total\_numerical\_claims}}} \times 100\%$$
Measures the percentage of reported engineering quantities (base shear, fundamental period $T_1$, peak moment/shear, or governing $\text{DCR}$) that deviate by $>5\%$ from the exact deterministic mechanics solution. In the proposed neuro-symbolic framework, $\text{CHR} = 0.0\%$ by construction because all numerical outputs are read directly from verified symbolic tool states.

### 3.4 Self-Healing Convergence Iterations ($N_{\text{iter}}$)
For cases where the initial trial design is overstressed ($\text{DCR}_{\text{gov}}^{(0)} > 1.0$), $N_{\text{iter}}$ records the number of closed-loop reflection cycles (`modify_project` $\rightarrow$ `run_analysis`/`run_time_history` $\rightarrow$ `run_design`) required to achieve $\text{DCR}_{\text{gov}}^{(N_{\text{iter}})} \le 1.0$.

### 3.5 Volumetric Material Economy Ratio ($\eta_{\text{vol}}$)
$$\eta_{\text{vol}} = \frac{V_{\text{concrete}}^{\text{agent}}}{V_{\text{concrete}}^{\text{baseline}}}$$
Evaluated on code-compliant designs ($\text{DCR}_{\text{gov}} \le 1.0$), where $V_{\text{concrete}} = \sum_{e \in \mathcal{E}} A_e L_e$ is the total structural concrete volume ($\text{m}^3$) and $V_{\text{concrete}}^{\text{baseline}}$ is the verified human engineering baseline volume generated by `generate_human_baselines.py`. Values of $\eta_{\text{vol}} \approx 0.95\text{--}1.05$ indicate that the agent achieves human-level material efficiency without gross over-sizing; when reinforcement detailing is generated (`struct_draw`), the composite cost ratio $\eta_{\text{material}} = \frac{V_{\text{concrete}}^{\text{agent}} + \alpha W_{\text{steel}}^{\text{agent}}}{V_{\text{concrete}}^{\text{baseline}} + \alpha W_{\text{steel}}^{\text{baseline}}}$ is also inspected.

---

## 4. Experimental Configurations & Multi-Model Matrix

### 4.1 Comparative Configurations
| Configuration ID | CLI Flag (`--config`) | Description & Role in Ablation Study |
|---|---|---|
| **Baseline 1: Direct Zero-Shot LLM** | `direct_llm` | Raw LLM prompting without symbolic tools; quantifies baseline mathematical error and Calculation Hallucination Rate ($\text{CHR}$). |
| **Baseline 2: Code-Generation LLM** | `code_gen` | Prompts the LLM to write raw standalone Python/NumPy FEA and design scripts from scratch; measures syntax/convergence failures. |
| **Baseline 3: Ablated Agent (No Reflection)** | `ablated` | Full neuro-symbolic tool suite enabled, but closed-loop reflection (`modify_project` resizing) is strictly disabled; isolates the impact of self-healing on $\text{CCR}$. |
| **Proposed: Full Neuro-Symbolic Agent** | `full_agent` | Complete ontology-grounded agent with multimodal perception, symbolic solvers, and autonomous self-healing reflection loop. |

### 4.2 Evaluated LLM Backbones
| Model Identifier | Architecture & Provider | Scale | Deployment Modality | Endpoint / Authentication |
|---|---|---|---|---|
| **`gemini-3.8-flash`** | Frontier Closed-Source (Google DeepMind) | Proprietary | Cloud API | `GEMINI_API_KEY` loaded from `struct_agent/.env` |
| **`qwen3.5:9b`** | Open-Weight Dense (Alibaba Qwen) | 9B | Local Workstation (Ollama) | `http://localhost:11434/v1` |
| **`gpt-oss:120b-cloud`** | Open-Weight Large Model | 120B | Cloud Ollama Host | `OLLAMA_HOST` environment variable |
| **`nemotron-3-ultra:cloud`** | Open-Weight Math/Reasoning-Tuned (NVIDIA) | Ultra Scale | Cloud Ollama Host | `OLLAMA_HOST` environment variable |

---

## 5. Step-by-Step Reproducibility Protocol

### Step 1: Activate Environment & Verify Baselines
```powershell
conda activate structeng
python "research_paper/benchmarks/generate_human_baselines.py"
```

### Step 2: Execute Full & Ablated Benchmark Campaigns

```powershell
# 1. Google Gemini 3.8 Flash (Full Agent vs. Ablated):
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --config full_agent --cases all
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --config ablated --cases all

# 2. Local Qwen 3.5 9B (Full Agent vs. Ablated):
python "research_paper/benchmarks/run_benchmarks.py" --model qwen3.5:9b --config full_agent --cases all
python "research_paper/benchmarks/run_benchmarks.py" --model qwen3.5:9b --config ablated --cases all

# 3. Cloud GPT-OSS 120B (Full Agent vs. Ablated):
python "research_paper/benchmarks/run_benchmarks.py" --model gpt-oss:120b-cloud --config full_agent --cases all
python "research_paper/benchmarks/run_benchmarks.py" --model gpt-oss:120b-cloud --config ablated --cases all

# 4. Cloud Nemotron 3 Ultra (Full Agent vs. Ablated):
python "research_paper/benchmarks/run_benchmarks.py" --model nemotron-3-ultra:cloud --config full_agent --cases all
python "research_paper/benchmarks/run_benchmarks.py" --model nemotron-3-ultra:cloud --config ablated --cases all
```

### Step 3: Compile Telemetry Tables & Publication Figures

```powershell
python "research_paper/benchmarks/analyze_results.py"
```

This script processes all timestamped JSON logs in `research_paper/benchmarks/results/` (without overwriting prior runs) and outputs:

* `results/summary_table_<timestamp>.md`: Markdown table of $\text{TCR}$, $\text{CCR}$, $N_{\text{iter}}$, $\eta_{\text{vol}}$, and runtime ready for Section 5.
* `plots/fig_benchmark_comparison_<timestamp>.png`: 300 DPI grouped bar chart of $\text{TCR}$ and $\text{CCR}$.
* `plots/fig_dcr_convergence_<timestamp>.png`: 300 DPI self-healing $\text{DCR}$ vs. iteration trajectories.
* `plots/fig_material_economy_<timestamp>.png`: 300 DPI volumetric concrete economy comparison against the $\eta_{\text{vol}} = 1.00$ human baseline.
