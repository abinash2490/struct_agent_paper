# 4. Experimental Setup & Benchmark Protocol

**Target Venues**: *Automation in Construction* (Elsevier, IF: 10.3) | *Advanced Engineering Informatics* (Elsevier, IF: 8.0)  
**Companion Documents**: [`paper_idea.md`](../paper_idea.md), [`03_methodology.md`](03_methodology.md), [`benchmark_cases.json`](../benchmarks/benchmark_cases.json)

---

## 4.1. Benchmark Suite Design Principles & Scope

To rigorously test the proposed neuro-symbolic framework and falsify Hypotheses H1–H3, an experimental benchmark suite of **24 structural design instances** was constructed. The suite reflects real-world structural engineering workflows spanning gravity load takedown, modal eigenvalue dynamics, Equivalent Lateral Force (ELF) seismic procedures, multi-directional Response Spectrum Analysis (RSA), direct earthquake accelerogram time-history numerical integration, multimodal drawing ingestion, and production AutoCAD `.dxf` drafting with Bar Bending Schedules (BBS).

In alignment with the core capabilities of the underlying symbolic solver ecosystem, all environmental lateral loading is strictly focused on **earthquake engineering** per ASCE 7-16/22 and codified concrete capacity checks per ACI 318-19/25. Unverified environmental loads (such as wind or snow) are excluded from the test matrix to maintain absolute ground-truth determinism against commercial CAE reference software (CSI SAP2000 and ETABS).

**Engineering Scope Boundary & Codified Limit States**: To establish an unambiguous, reproducible ground truth for evaluating agentic structural reasoning, the benchmark suite focuses on *preliminary structural proportioning and strength-level limit states* governed by ASCE 7-22 Chapter 12 and ACI 318-19/25 Chapters 6, 9, 10, and 11 (flexural yield capacity, one-way beam shear, and 3D axial-flexural $P-M_2-M_3$ interaction via the Bresler reciprocal load method). While several seismic archetypes specify response modification factors ($R=5.0$) corresponding to Intermediate Moment Frames (IMRF) in moderate-to-high seismic regimes, the evaluation scope is strictly focused on member sizing and preliminary strength checks; prescriptive seismic detailing provisions governed by ACI 318 Chapter 18 (e.g., strong-column/weak-beam moment ratios per §18.7.3.2, special seismic transverse hoop spacing, and beam-column joint shear checks) are decoupled from cross-section proportioning and evaluated downstream during production CAD reinforcement generation (`struct_draw`).

The 24 benchmark cases are divided into three progressive groups:
1. **Group A: 2D Plane Frames (Cases A01–A08)**: Evaluates fundamental 2D frame mechanics, tributary gravity load distribution, modal vibration periods, 2D Response Spectrum Analysis under both ASCE 7 code spectra and recorded ground motion spectra (1994 Northridge), and single-bay self-healing redesign reflection.
2. **Group B: 3D Space Frames (Cases B01–B08)**: Evaluates 3D direct stiffness finite element assembly, multi-story biaxial gravity distribution, ASCE 7 Equivalent Lateral Force (ELF) seismic procedures with orthogonal combination ($1.0E_X \pm 0.3E_Y$), 3D coupled modal dynamics, 3D Response Spectrum Analysis, bi-directional orthogonal seismic combination, and 3D seismic self-healing redesign.
3. **Group C: Advanced Dynamic, Multimodal Vision, CAE & CAD Pipelines (Cases C01–C08)**: Evaluates direct numerical time-history integration of nonlinear/linear equations of motion under recorded accelerograms (1940 El Centro, 1994 Northridge), lossless round-trip CAE exchange with CSI SAP2000 (`.s2k`) and ETABS (`.e2k`), multimodal architectural floor plan ingestion via Vision-Language Models (`struct_agent.vision`), dynamic reflection under time-history demands, and autonomous end-to-end seismic design-to-CAD production.

---

## 4.2. Systematic Benchmark Case Taxonomy (24 Cases)

Table 2 presents the systematic taxonomy of all 24 benchmark problems, detailing the structural archetype, loading regime, governing code checks, expected symbolic tools, and verified baseline metrics.

### Table 2: Standardized 24-Case Structural and Seismic Benchmark Matrix

| Case ID | Name & Structural Archetype | Geometric Configuration | Loading & Analysis Regime | Design Required? | Verified Baseline ($V_{\text{base}}, \text{DCR}_{\text{base}}$) | Expected Tool Pipeline | Target Deliverable / Output |
|---|---|---|---|:---:|:---:|---|---|
| **A01** | Single-Bay Portal Frame (Office) | 1 bay, 1 story; $L=6.0\text{ m}, H=3.5\text{ m}$ | Office Gravity ($w_{\text{trib}}=4.0\text{ m}$); Linear Static | Yes | $1.757\text{ m}^3$ (DCR 0.846) | `create_frame_model`, `apply_gravity_loads`, `run_analysis`, `run_design`, `generate_drawings` | CAD Drawing: `research_paper/drawings/A01_portal_frame.dxf` |
| **A02** | Wide-Span Portal Frame (Storage) | 1 bay, 1 story; $L=8.0\text{ m}, H=4.0\text{ m}$ | Heavy Storage Gravity ($w_{\text{trib}}=4.5\text{ m}$); Linear Static | Yes | $3.820\text{ m}^3$ (DCR 0.864) | `create_frame_model`, `apply_gravity_loads`, `run_analysis`, `run_design` | ACI 318 Capacity Envelope |
| **A03** | 2-Bay 2-Story Frame (Office) | 2 bays, 2 stories; $L=5.0\text{ m}, H=3.2\text{ m}$ | Office Gravity ($w_{\text{trib}}=5.0\text{ m}$); Linear Static | Yes | $5.772\text{ m}^3$ (DCR 0.599) | `create_frame_model`, `apply_gravity_loads`, `run_analysis`, `run_design` | Multi-story Member Design |
| **A04** | 2-Bay 3-Story Frame (Residential) | 2 bays, 3 stories; $L=6.0\text{ m}, H=3.0\text{ m}$ | Residential Gravity ($w_{\text{trib}}=4.5\text{ m}$); Linear Static | Yes | $9.720\text{ m}^3$ (DCR 0.677) | `create_frame_model`, `apply_gravity_loads`, `run_analysis`, `run_design` | Beam/Column Capacity Ratios |
| **A05** | 2D Modal Dynamics Frame | 2 bays, 3 stories; $L=6.0\text{ m}, H=3.5\text{ m}$ | Consistent Mass Formulation; Generalized Eigenproblem | No | Pure Dynamics ($T_1, T_2, T_3$) | `create_frame_model`, `run_modal_analysis`, `inspect_modal_results` | Eigenvalue Vibration Frequencies & Shapes |
| **A06** | 2D Response Spectrum (ASCE 7) | 2 bays, 3 stories; $L=6.0\text{ m}, H=3.5\text{ m}$ | ASCE 7 Spectrum ($S_{DS}=1.0g, S_{D1}=0.6g$); CQC Modal Combination | Yes | $13.309\text{ m}^3$ (DCR 0.880) | `create_frame_model`, `apply_gravity_loads`, `run_response_spectrum`, `run_design` | Seismic Envelopes & ACI 318 Checks |
| **A07** | 2D RSA Ground Motion (Northridge) | 3 bays, 4 stories; $L=5.5\text{ m}, H=3.5\text{ m}$ | 1994 Northridge Accelerogram Response Spectrum; CQC | Yes | $26.705\text{ m}^3$ (DCR 0.880) | `create_frame_model`, `apply_gravity_loads`, `run_response_spectrum`, `run_design` | High-Rise Dynamic Response |
| **A08** | 2D Overstressed Reflection Portal | 1 bay, 1 story; $L=7.0\text{ m}, H=3.5\text{ m}$ | Heavy Storage ($w_{\text{trib}}=6.0\text{ m}$); Preliminary trial sections ($0.30\times0.30\text{ m}$ cols, $0.30\times0.45\text{ m}$ beams), Initial $\text{DCR}_0 = 3.95 > 1.0$ | Yes | $3.710\text{ m}^3$ (DCR 0.797) | `create_frame_model`, `run_analysis`, `run_design`, `modify_project`, `generate_drawings` | Self-Healing Redesign; CAD: `research_paper/drawings/A08_portal_frame.dxf` |
| **B01** | 3D Space Frame (2x2, 2-Story Gravity) | $2\times2$ bays, 2 stories; $L_x=6.0\text{ m}, L_y=6.0\text{ m}, H=3.5\text{ m}$ | Residential Floor Gravity; 3D Direct Stiffness | No | Kinematics Verification | `create_frame_model`, `apply_gravity_loads`, `run_analysis` | 3D Floor Displacements & Column Shortening |
| **B02** | 3D $3\times2$ Bay Commercial Frame | $3\times2$ bays, 3 stories; $L_x=5.0\text{ m}, L_y=6.0\text{ m}, H=3.2\text{ m}$ | Office Floor Gravity; Two-Way Slab Distribution | Yes | $65.178\text{ m}^3$ (DCR 0.846) | `create_frame_model`, `apply_gravity_loads`, `run_analysis`, `run_design` | 3D Biaxial Column Interaction ($P-M_2-M_3$) |
| **B03** | 3D Space Frame Seismic ELF (Near Limit) | $2\times2$ bays, 3 stories; $L_x=6.0\text{ m}, L_y=6.0\text{ m}, H=3.5\text{ m}$ | ASCE 7-22 Seismic ELF ($S_{DS}=1.2g, S_{D1}=0.5g, R=5$); LRFD Combinations | Yes | $143.100\text{ m}^3$ (DCR 0.983) | `create_frame_model`, `apply_gravity_loads`, `apply_lateral_loads`, `run_analysis`, `run_design` | 3D Bresler Reciprocal Capacity Checks |
| **B04** | 3D Modal Eigenvalue Dynamics | $2\times2$ bays, 3 stories; $L_x=6.0\text{ m}, L_y=6.0\text{ m}, H=3.5\text{ m}$ | 3D Mass Matrix; Coupled Translational-Torsional Modes | No | 3D Dynamics ($T_1, T_2, T_3$) | `create_frame_model`, `run_analysis`, `inspect_analysis_results` | 3D Mass Participation & Torsional Ratios |
| **B05** | 3D Response Spectrum (X-Direction) | $2\times2$ bays, 3 stories; $L_x=6.0\text{ m}, L_y=6.0\text{ m}, H=3.5\text{ m}$ | ASCE 7-22 Spectrum ($S_{DS}=1.1g, S_{D1}=0.55g$); 3D CQC Combination | Yes | $116.640\text{ m}^3$ (DCR 0.866) | `create_frame_model`, `apply_gravity_loads`, `run_response_spectrum`, `run_design` | 3D Dynamic Member Capacity Envelopes |
| **B06** | 3D Response Spectrum (El Centro) | $3\times2$ bays, 3 stories; $L_x=5.0\text{ m}, L_y=6.0\text{ m}, H=3.2\text{ m}$ | 1940 El Centro Ground Motion Spectrum ($R=5.0, \xi=5\%$); CQC Combination | Yes | $82.508\text{ m}^3$ (DCR 0.880) | `create_frame_model`, `apply_gravity_loads`, `run_response_spectrum`, `run_design` | Dynamic Member Code Verification |
| **B07** | 3D High-Seismic Reflection Frame | $2\times2$ bays, 2 stories; $L_x=6.0\text{ m}, L_y=6.0\text{ m}, H=3.5\text{ m}$ | High Seismic ELF ($S_{DS}=1.2g$); Initial $\text{DCR}_0 = 1.77 > 1.0$ | Yes | $56.857\text{ m}^3$ (DCR 0.970) | `create_frame_model`, `apply_lateral_loads`, `run_analysis`, `run_design`, `modify_project` | 3D Closed-Loop Resizing Convergence |
| **B08** | 3D Bi-Directional Seismic Space Frame | $2\times2$ bays, 3 stories; $L_x=6.0\text{ m}, L_y=6.0\text{ m}, H=3.5\text{ m}$ | ASCE 7-22 ELF Orthogonal Combination ($1.0E_X \pm 0.3E_Y$) | Yes | $113.636\text{ m}^3$ (DCR 0.940) | `create_frame_model`, `apply_gravity_loads`, `apply_lateral_loads`, `run_analysis`, `run_design` | Corner Column Biaxial Interaction & Design |
| **C01** | Dynamic Time-History Elastic Check | 2 bays, 3 stories; $L=6.0\text{ m}, H=3.5\text{ m}$ | 1940 El Centro Accelerogram (S00E); Newmark-Beta Integration | No | Elastic Dynamic Assessment ($u_{\text{roof}}, V_b$) | `create_frame_model`, `apply_gravity_loads`, `run_time_history`, `inspect_dynamic_results` | Elastic Dynamic Response Verification |
| **C02** | 3D Dynamic Time-History Elastic Check | $2\times2$ bays, 2 stories; $L_x=6.0\text{ m}, L_y=6.0\text{ m}, H=3.5\text{ m}$ | 1994 Northridge Accelerogram (Sylmar 360); Direct Dynamic Integration | No | Elastic Dynamics Assessment | `create_frame_model`, `apply_gravity_loads`, `run_time_history`, `inspect_dynamic_results` | Floor Acceleration & Drift Time-Series |
| **C03** | CSI SAP2000 Round-Trip CAE | 2 stories, $2\times1$ bays; $L_x=10.0\text{ m}, L_y=5.0\text{ m}$ (`exported_seismic_frame.s2k`) | Gravity ($D, L$), ASCE 7-22 ELF ($EQ_x$), Modal Dynamics | No | $12.040\text{ m}^3$ ($D=988.96\text{ kN}, V_b=132.37\text{ kN}, T_1=0.458\text{ s}$) | `import_from_sap2000`, `validate_model`, `run_analysis`, `inspect_analysis_results`, `export_to_sap2000` | Re-exported Model: `research_paper/benchmarks/results/exported_sap2000.s2k` |
| **C04** | CSI ETABS Round-Trip CAE | 2 stories, $2\times1$ bays; $L_x=10.0\text{ m}, L_y=5.0\text{ m}$ (`exported_seismic_frame.e2k`) | Gravity ($D, L$), ASCE 7-22 ELF ($EQ_x$), Modal Dynamics | No | $12.040\text{ m}^3$ ($D=988.96\text{ kN}, V_b=132.37\text{ kN}, T_1=0.458\text{ s}$) | `import_from_etabs`, `validate_model`, `run_analysis`, `inspect_analysis_results`, `export_to_etabs` | Re-exported Model: `research_paper/benchmarks/results/exported_etabs.e2k` |
| **C05** | Multimodal Vision Floor Plan Ingestion | 3-story educational facility (`floor_plan_3story_school.PNG`) | Architectural Plan to 3D Frame Compilation (`create_model_from_plan_draft`) | No | Topological Topology Parity | `create_model_from_plan_draft`, `validate_model`, `inspect_project` | Synthesized 3D Project Invariant Model (School Fixture) |
| **C06** | Multimodal Vision-to-Seismic Design | 4-story commercial facility (`mall_plan_4story.PNG`) | Multimodal Compilation $\rightarrow$ Seismic ELF ($S_{DS}=1.2g, R=5$) $\rightarrow$ ACI 318-25 | Yes | $165.728\text{ m}^3$ (DCR 0.880) | `create_model_from_plan_draft`, `apply_gravity_loads`, `apply_lateral_loads`, `run_analysis`, `run_design` | Full Multimodal Seismic Design (Mall Fixture) |
| **C07** | 2D Dynamic Reflection (High-Seismic) | 2 bays, 3 stories; Initial $0.30\times0.30\text{ m}$ columns | High-Seismic ELF ($S_{DS}=1.5g$); Initial $\text{DCR}_0 = 2.59 > 1.0$ | Yes | $14.805\text{ m}^3$ (DCR 0.771) | `create_frame_model`, `apply_lateral_loads`, `run_analysis`, `run_design`, `modify_project` | Closed-Loop Resizing Convergence |
| **C08** | Autonomous Seismic Design-to-CAD | 2 bays, 2 stories; $L=5.0\text{ m}, H=3.2\text{ m}$ | Response Spectrum ($S_{DS}=1.0g, S_{D1}=0.6g$) $\rightarrow$ ACI 318-25 $\rightarrow$ AutoCAD `.dxf` | Yes | $6.072\text{ m}^3$ (DCR 0.846) | `create_frame_model`, `run_response_spectrum`, `run_design`, `generate_drawings`, `inspect_detailing_results` | Scaled CAD Drawing & BBS: `research_paper/drawings/C08_seismic_frame.dxf` |

### 4.2.1. Design-Case Diversity & Governing Limit States

To ensure the benchmark does not reward models that merely memorize a single governing check, the 16 design cases deliberately sample the full spectrum of structural concrete failure modes under ACI 318-25:
1. **Minimum Flexural Reinforcement ($A_{s,\min}$, ACI 318 §9.6.1)**: In moderate seismic and gravity frames with conventional spans (Cases A01, A03, A04, A06, A07, B02, B03, B05, B06, B08, C06, C08), beam flexural strength is governed by the statutory minimum reinforcement ratio $\rho_{\min} = 3\sqrt{f'_c}/f_y \ge 200/f_y$. When factored moment demands $M_u$ are light-to-moderate, code provisions mandate $A_{s,\min}$, yielding an identical design capacity ratio $\text{DCR} \approx 0.846 - 0.880$. Cases A06 and A07 intentionally test this critical boundary condition: verifying whether an agent correctly detects that increasing section depth or reinforcing bar count beyond $A_{s,\min}$ cannot reduce the governing DCR below this code threshold.
2. **Column Biaxial P-M Interaction (ACI 318 §10.5 & Bresler Reciprocal Formulation)**: In heavy storage and high-seismic configurations (Cases A02, A08, B07, C07), axial loads and reversible lateral moments govern. In particular, A08 exhibits column overstress under heavy storage ($11.97\text{ kPa}$), governing at $\text{DCR} = 0.797$ post-convergence, while 3D reflection cases B07 and C07 govern under coupled biaxial flexure and axial compression.
3. **Seismic Shear and Joint Equilibrium (ACI 318 §18.6 & §18.8)**: In cases B03 and B08, high lateral base shears and orthogonal combinations ($1.0E_X \pm 0.3E_Y$) engage shear stirrup spacing limits and column-beam moment capacity ratio ($\sum M_{nc} / \sum M_{nb} \ge 1.2$) requirements.

---

## 4.3. Real-World Architectural Benchmark Fixtures

To validate multimodal perceptual compilation under realistic architectural layouts, three real-world building floor plans are incorporated as benchmark fixtures:

1. **3-Story Reinforced Concrete School Facility (`floor_plan_3story_school.PNG`)**:
   - *Case Binding*: Case C05 (`C05_Vision_FloorPlan_Draft_Ingestion`).
   - *Structural Layout*: 3 stories at $3.5\text{ m}$ story height, framing an educational facility with overall footprint $21.5\text{ m} \times 9.75\text{ m}$.
   - *Grid Topology*: Orthogonal structural grids Grids A, B, C, D along the longitudinal axis and Grids 1, 2, 3, 4 along the transverse axis. The framing defines standard classroom modules with a central longitudinal circulation corridor.
   - *Role in Benchmarking*: Assesses the Vision-Language Model's ability to interpret structural grid notations, bay spacings, wall/column symbols, and correctly compile a valid, watertight 3D frame model (`FloorPlanDraft` $\rightarrow$ `struct_core.Project`).

2. **2-Story Residential Hostel Block (`hostel_block_plan_2story.PNG`)**:
   - *Suite Role*: Maintained in the benchmark fixtures library as an extended $7\times2$ bay architectural floor plan fixture for future multimodal extensions, while Case B01 (`B01_3D_2x2_2Story_Gravity`) benchmarks pure text-to-space-frame gravity synthesis.
   - *Structural Layout*: 2 stories at $3.5\text{ m}$ story height, framing a residential block with overall footprint $27.3\text{ m} \times 10.9\text{ m}$.
   - *Grid Topology*: Multi-bay modular grid system (Grids A through H along the longitudinal axis and Grids 1 through 3 along the transverse axis) with repetitive room units, perimeter columns, and dual-direction framing.

3. **4-Story Commercial Mall Complex (`mall_plan_4story.PNG`)**:
   - *Case Binding*: Case C06 (`C06_Vision_To_Seismic_Design_Pipeline`).
   - *Structural Layout*: 4 stories at $3.2\text{ m}$ story height, framing a commercial retail complex with overall footprint $49'\text{-}0'' \times 36'\text{-}0''$ ($14.94\text{ m} \times 10.97\text{ m}$).
   - *Grid Topology*: Grids 5, 4, 3, 2, 1 along the longitudinal direction and Grids A, B, C, D along the transverse direction, accommodating large open retail spans and centralized column clusters.
   - *Role in Benchmarking*: Forms the ultimate end-to-end stress test: extracting architectural geometry from raster pixels $\rightarrow$ compiling a 3D structural frame $\rightarrow$ applying commercial gravity and high-seismic ASCE 7 ELF lateral forces ($S_{DS}=1.2g, S_{D1}=0.5g, R=5.0$) $\rightarrow$ executing 3D finite element analysis $\rightarrow$ verifying ACI 318 biaxial member capacities.

---

## 4.4. Comparative Baselines, Ablation Guards & Informational Parity

To rigorously evaluate the contribution of each architectural component while avoiding strawman baselines, five comparative configurations are executed across the benchmark suite:

0. **Baseline 0 (Deterministic Engineering Heuristic — `heuristic`)**:
   - Implements classical structural engineering rule-of-thumb preliminary proportions: columns $b = h = \max(0.30\text{ m}, 0.05 \cdot H_{\text{total}})$, beams $b = 0.30\text{ m}, h = \max(0.35\text{ m}, L / 12.0)$, rounded to nearest $0.05\text{ m}$.
   - If overstressed ($\text{DCR} > 1.0$), sections are resized iteratively via the square-root rule ($h_{\text{new}} = h_{\text{curr}}\sqrt{\text{DCR}}$). This non-LLM baseline establishes the deterministic engineering floor, benchmarking the added value of the neuro-symbolic framework against standard engineering practice.

1. **Baseline 1 (Direct Zero-Shot LLM — `direct_llm`)**:
   - The conversational language model receives natural language structural problem specifications and is prompted to output candidate member cross-section dimensions (`col_b`, `col_h`, `beam_b`, `beam_h`) and claimed physical metrics ($W, V_b, T_1, \text{DCR}$).
   - **Deterministic Oracle Verification**: To resolve the fundamental critique of *equifinality* (infinite valid indeterminate designs) and *self-weight coupling*, the benchmark harness passes the LLM's proposed cross-sections into the deterministic `OracleVerifier` (`fem2d`/`fem3d`/`structdyn`/`aci318`). This computes true ground-truth physics ($W_{\text{oracle}}, V_{b,\text{oracle}}, T_{1,\text{oracle}}, \text{DCR}_{\text{oracle}}$) on the LLM's exact geometry. If the model's chosen sections satisfy $\text{DCR}_{\text{oracle}} \le 1.00$, it is legitimately credited with Code Compliance ($\text{CCR}$).
   - **Informational Parity**: For commercial CAE interoperability cases (C03, C04), the raw text of the fixture exchange files (`sample_frame.s2k` and `sample_frame.e2k`) is appended directly to the prompt, ensuring unaugmented baselines have identical geometric and loading data as the tool-augmented agent.

2. **Baseline 2 (Code-Generation LLM — `code_gen`)**:
   - The language model is prompted to generate standalone executable Python scripts using general numerical libraries (`numpy`, `scipy`) to model and solve the structural problem from first principles without domain-specific schemas.
   - The script is executed in an isolated runtime environment. If execution succeeds, the generated cross-section dimensions and claimed metrics are passed into `OracleVerifier` to compute true physical quantities and assess calculation hallucinations.

3. **Baseline 3 (Ablated Agent without Reflection — `ablated`)**:
   - The agent is equipped with symbolic modeling, analysis, and design tools, but the closed-loop self-healing reflection mechanism is disabled to isolate the empirical value of iterative diagnostic feedback.
   - **Multi-Layer Ablation Guard**: To prevent the model from circumventing the ablation: (i) `modify_project` is physically stripped from tool schemas; (ii) explicit reflection directives in case prompts (A08, B07, C07) are sanitized so the model evaluates initial trial sections in a strict single pass; and (iii) runtime re-creation tools (`create_frame_model`, `build_structural_model`) are dynamically blocked by `allow_model_recreation=False` from executing a second time once `run_design` has been invoked.

4. **Proposed Framework (Full Neuro-Symbolic Agent with Reflection — `full_agent`)**:
   - The complete architecture featuring ontology-grounded validation (`struct_core`), symbolic mechanics solvers, multimodal drawing compilation (`struct_agent.vision`), and closed-loop self-healing redesign driven by $\text{DCR}_{\text{gov}}$ diagnostic feedback.

---

## 4.5. Multi-Model Evaluation Testbed

To test cross-model generalization (Hypothesis H3), benchmarks are evaluated across four prominent Large Language Model backbones representing both proprietary frontier APIs and local/cloud open-weight architectures:

| Model Identifier | Architecture & Provider | Parameter Scale | Deployment Modality | Context Window |
|---|---|:---:|---|:---:|
| **`gemini-3.8-flash`** | Frontier Closed-Source Multimodal (Google DeepMind) | Proprietary | Cloud API (`google-genai` SDK) | 1,000,000 tokens |
| **`qwen3.5:9b`** | Open-Weight Dense Multimodal (Alibaba Qwen) | 9B | Local Workstation via Ollama | 128,000 tokens |
| **`nemotron-3-super:cloud`** | Open-Weight Math/Engineering-Tuned (NVIDIA) | Cloud Host | High-Performance Cloud Host via Ollama | 128,000 tokens |
| **`gemma4:31b-cloud`** | Open-Weight High-Capacity Frontier (Google DeepMind) | 31B | Cloud Host via Ollama / API | 128,000 tokens |

---

## 4.6. Quantitative Evaluation Metrics

The experimental evaluation employs rigorous, mathematically formulated metrics:

### 1. Task Completion Rate ($\text{TCR}$)
$$\text{TCR} = \frac{N_{\text{completed}}}{N_{\text{total}}} \times 100\% \quad (N_{\text{total}} = 24)$$
To avoid ontological strawman definitions, task completion is defined as the generation of an executable, verifiable digital twin deliverable (stiffness/mass matrices, FEA displacement vectors, code compliance verification certificates, or production CAD DXF drawings). Baseline 1 produces unverified conversational text ($\text{TCR} = 0.0\%$), Baseline 2 achieves completion if its generated Python script executes without runtime exceptions, and Baselines 3 & 4 achieve completion if all mandatory tools in `expected_tools` execute successfully to deliver the final project state.

### 2. Code Compliance Rate ($\text{CCR}$)
$$\text{CCR} = \frac{N_{\text{compliant}}}{N_{\text{design}}} \times 100\% \quad (N_{\text{design}} = 16)$$
Evaluated strictly across the 16 design-mandated benchmark cases. A structural design is code-compliant if and only if the governing Demand-Capacity Ratio evaluated by the deterministic engine satisfies:
$$\text{DCR}_{\text{gov}} = \max_{e \in \mathcal{E}, \, c \in \mathcal{C}} \left\{ \frac{P_{u,e,c}}{\phi P_{n,e}}, \, \frac{M_{u,e,c}}{\phi M_{n,e}}, \, \frac{V_{u,e,c}}{\phi V_{n,e}}, \, \text{Bresler}(P_u, M_{u2}, M_{u3}) \right\} \le 1.00$$
For Baselines 1 and 2, compliance is awarded via `OracleVerifier` if the LLM's proposed cross-sections satisfy $\text{DCR}_{\text{oracle}} \le 1.00$ under physical sanity bounds ($b, h \in [0.15\text{ m}, 1.50\text{ m}]$).

### 3. Calculation Hallucination Rate ($\text{CHR}$) & Claim Completeness
To prevent biased metrics that penalize silence as hallucination or conversely reward models that make zero claims, a rigorous dual-metric formulation is adopted:
$$\text{CHR} = \frac{N_{\text{hallucinated\_claims}}}{N_{\text{claims\_made}}} \times 100\%$$
$$\text{CCR}_{\text{claims}} = \frac{|\,N_{\text{claims\_made}} \cap N_{\text{expected\_metrics}}\,|}{N_{\text{expected\_metrics}}} \times 100\%$$
where $N_{\text{expected\_metrics}} = N_{\text{active\_metrics}} \cup N_{\text{required\_metrics}}$, with $N_{\text{active\_metrics}}$ representing regime-specific physical mechanics (total dead weight $W$, lateral base shear $V_b$, fundamental period $T_1$, governing DCR) and $N_{\text{required\_metrics}}$ capturing prompt-mandated quantities (e.g., higher modal periods $T_2, T_3$, modal mass participation ratios, and peak displacements for modal and time-history cases).

A reported numerical engineering claim $X_{\text{claimed}}$ is classified as a calculation hallucination if:
$$\frac{|X_{\text{claimed}} - X_{\text{oracle}}|}{\max(|X_{\text{oracle}}|, 10^{-4})} > 0.10 \quad (>10.0\% \text{ discrepancy})$$
Crucially, CHR represents precision over claims actually asserted, whereas Claim Completeness $\text{CCR}_{\text{claims}}$ captures coverage across active and prompt-demanded physical quantities. Tool-augmented agents achieve $0.0\%$ CHR because reported numbers originate directly from solver telemetry, whereas direct LLMs hallucinate internal calculations frequently.

### 4. Prompt-to-Schema Fidelity Rate ($\text{PSFR}$)
$$\text{PSFR} = \frac{\sum_{i=1}^{N_{\text{cases}}} \mathbb{I}(\text{SchemaMatchesTarget}_i)}{N_{\text{cases}}} \times 100\%$$
Quantifies whether the agent accurately synthesizes tool arguments matching the problem specifications from natural language without argument hallucination. Checks include: (i) model dimensionality (2D plane frame vs 3D space frame); (ii) story count ($N_{\text{stories}}$); (iii) bay counts ($N_{\text{bays}}$ in 2D, $N_x, N_y$ in 3D); and (iv) overall envelope dimensions within $1.0\%$.

### 5. Self-Healing Convergence Iterations ($N_{\text{iter}}$)
For benchmark cases initialized with undersized trial cross-sections ($\text{DCR}_{\text{gov}}^{(0)} > 1.0$), $N_{\text{iter}}$ quantifies the number of closed-loop reflection cycles (`modify_project` $\rightarrow$ `run_analysis` $\rightarrow$ `run_design`) required to achieve structural feasibility ($\text{DCR}_{\text{gov}}^{(N_{\text{iter}})} \le 1.0$).

### 6. Volumetric Material Economy Ratio ($\eta_{\text{vol}}$) & Design Efficiency
$$\eta_{\text{vol}} = \frac{V_{\text{concrete}}}{V_{\text{concrete}}^{\text{baseline}}}, \quad \text{Efficiency} = \frac{V_{\text{concrete}}^{\text{baseline}}}{V_{\text{concrete}}}$$
where $V_{\text{concrete}} = \sum_{e \in \mathcal{E}} A_e L_e$ is the total structural concrete volume ($\text{m}^3$) of the code-compliant design, and $V_{\text{concrete}}^{\text{baseline}}$ is the verified human engineering baseline volume. Values of $\eta_{\text{vol}} < 1.00$ ($\text{Efficiency} > 1.00$) indicate material economy and outperformance relative to standard initial sizing, while $\eta_{\text{vol}} > 1.00$ reflects cross-section enlargement necessary to satisfy high seismic or dynamic demands.

---

## 4.7. Reproducibility Protocol & Statistical Rigor

To ensure scientific reproducibility and avoid single-sample anecdotal conclusions:
1. **Multi-Seed Execution Protocol**: For stochastic multi-turn dialogue configurations (`full_agent` and `ablated`), all 24 cases are executed across 5 independent seeds ($N_{\text{seeds}} = 5$, random seeds 42--46 with sampling temperature $T = 0.2$) to evaluate statistical stability and provide genuine variance for paired Wilcoxon signed-rank significance testing. In contrast, deterministic single-shot baselines (`direct_llm`, `code_gen`, `heuristic`) are executed with $N_{\text{seeds}} = 1$ at $T = 0.0$.
2. **Deterministic Baseline Sampling**: Single-shot baselines use $T = 0.0$ to guarantee strict determinism, while multi-seed agent evaluations use $T = 0.2$ to explore the solution space under minor stochastic variations.
3. **Model Version Pinning**: All proprietary and open-weight models are pinned to their canonical released checkpoints: Google `gemini-3.8-flash` (API accessed October 2026), Alibaba `qwen3.5:9b` (local Ollama deployment), NVIDIA `nemotron-3-super:cloud` (cloud host), and Google `gemma4:31b-cloud` (cloud host).
4. **Hypothesis Testing**: To formally test the superiority of closed-loop reflection over single-pass execution (Hypothesis H2), paired non-parametric Wilcoxon signed-rank tests are computed across all matched case pairs. Statistical significance is declared at $p < 0.05$.
