# 4. Experimental Setup & Benchmark Protocol

**Target Venues**: *Automation in Construction* (Elsevier, IF: 10.3) | *Advanced Engineering Informatics* (Elsevier, IF: 8.0)  
**Companion Documents**: [`paper_idea.md`](../paper_idea.md), [`03_methodology.md`](03_methodology.md), [`benchmark_cases.json`](../benchmarks/benchmark_cases.json)

---

## 4.1. Benchmark Suite Design Principles & Scope

To rigorously test the proposed neuro-symbolic framework and falsify Hypotheses H1–H3, an experimental benchmark suite of **24 structural design instances** was constructed. The suite reflects real-world structural engineering workflows spanning gravity load takedown, modal eigenvalue dynamics, Equivalent Lateral Force (ELF) seismic procedures, multi-directional Response Spectrum Analysis (RSA), direct earthquake accelerogram time-history numerical integration, multimodal drawing ingestion, and production AutoCAD `.dxf` drafting with Bar Bending Schedules (BBS).

In alignment with the core capabilities of the underlying symbolic solver ecosystem, all environmental lateral loading is strictly focused on **earthquake engineering** per ASCE 7-16/22 and codified concrete capacity checks per ACI 318-19/25. Unverified environmental loads (such as wind or snow) are excluded from the test matrix to maintain absolute ground-truth determinism against commercial CAE reference software (CSI SAP2000 and ETABS).

The 24 benchmark cases are divided into three progressive groups:
1. **Group A: 2D Plane Frames (Cases A01–A08)**: Evaluates fundamental 2D frame mechanics, tributary gravity load distribution, modal vibration periods, 2D Response Spectrum Analysis under both ASCE 7 code spectra and recorded ground motion spectra (1994 Northridge), and single-bay self-healing redesign reflection.
2. **Group B: 3D Space Frames (Cases B01–B08)**: Evaluates 3D direct stiffness finite element assembly, multi-story biaxial gravity distribution, ASCE 7 Equivalent Lateral Force (ELF) seismic procedures with orthogonal combination ($1.0E_X \pm 0.3E_Y$), 3D coupled translational-torsional modal dynamics, 3D Response Spectrum Analysis, plan-asymmetric torsional irregularity, and 3D seismic self-healing redesign.
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
| **A08** | 2D Overstressed Reflection Portal | 1 bay, 1 story; $L=7.0\text{ m}, H=3.5\text{ m}$ | Heavy Storage ($w_{\text{trib}}=6.0\text{ m}$); Initial $\text{DCR}_0 > 1.0$ | Yes | $3.710\text{ m}^3$ (DCR 0.797) | `create_frame_model`, `run_analysis`, `run_design`, `modify_project`, `generate_drawings` | Self-Healing Redesign; CAD: `research_paper/drawings/A08_portal_frame.dxf` |
| **B01** | 3D Hostel Block Space Frame | $2\times2$ bays, 2 stories; $L_x=6.0\text{ m}, L_y=6.0\text{ m}, H=3.5\text{ m}$ | Residential Floor Gravity; 3D Direct Stiffness | No | Kinematics Verification | `create_frame_model`, `apply_gravity_loads`, `run_analysis` | 3D Floor Displacements & Column Shortening (Hostel Fixture) |
| **B02** | 3D $3\times2$ Bay Commercial Frame | $3\times2$ bays, 3 stories; $L_x=5.0\text{ m}, L_y=6.0\text{ m}, H=3.2\text{ m}$ | Office Gravity ($w_{\text{trib}}=5.0\text{ m}$); Biaxial Moments | Yes | $85.104\text{ m}^3$ (DCR 0.846) | `create_frame_model`, `apply_gravity_loads`, `run_analysis`, `run_design` | 3D Biaxial Column Interaction ($P-M_2-M_3$) |
| **B03** | 3D Seismic ELF Space Frame | $2\times2$ bays, 3 stories; $L_x=6.0\text{ m}, L_y=6.0\text{ m}, H=3.5\text{ m}$ | ASCE 7 Seismic ELF ($S_{DS}=1.2g, S_{D1}=0.5g, R=5$); 26 LRFD Combinations | Yes | $143.100\text{ m}^3$ (DCR 0.983) | `create_frame_model`, `apply_gravity_loads`, `apply_lateral_loads`, `run_analysis`, `run_design` | 3D Bresler Reciprocal Capacity Checks |
| **B04** | 3D Modal Eigenvalue Dynamics | $2\times2$ bays, 3 stories; $L_x=6.0\text{ m}, L_y=6.0\text{ m}, H=3.5\text{ m}$ | 3D Mass Matrix; Coupled Translational-Torsional Modes | No | 3D Dynamics ($T_1, T_2, T_3$) | `create_frame_model`, `run_modal_analysis`, `inspect_modal_results` | 3D Mass Participation & Torsional Ratios |
| **B05** | 3D Response Spectrum (X-Direction) | $2\times2$ bays, 3 stories; $L_x=6.0\text{ m}, L_y=6.0\text{ m}, H=3.5\text{ m}$ | ASCE 7 Spectrum ($S_{DS}=1.1g, S_{D1}=0.55g$); 3D CQC Combination | Yes | $116.640\text{ m}^3$ (DCR 0.929) | `create_frame_model`, `apply_gravity_loads`, `run_response_spectrum`, `run_design` | 3D Dynamic Member Capacity Envelopes |
| **B06** | 3D Multi-Directional Dynamic RSA | $3\times2$ bays, 3 stories; $L_x=5.0\text{ m}, L_y=6.0\text{ m}, H=3.2\text{ m}$ | 1940 El Centro Multi-Directional Spectrum ($1.0X \pm 0.3Y$) | Yes | $107.700\text{ m}^3$ (DCR 0.948) | `create_frame_model`, `apply_gravity_loads`, `run_response_spectrum`, `run_design` | Bi-directional Seismic Envelopes |
| **B07** | 3D High-Seismic Reflection Frame | $2\times2$ bays, 2 stories; $L_x=6.0\text{ m}, L_y=6.0\text{ m}, H=3.5\text{ m}$ | High Seismic ELF ($S_{DS}=1.2g$); Initial $\text{DCR}_0 = 1.34 > 1.0$ | Yes | $56.857\text{ m}^3$ (DCR 0.626) | `create_frame_model`, `apply_lateral_loads`, `run_analysis`, `run_design`, `modify_project` | 3D Closed-Loop Resizing Convergence |
| **B08** | 3D Asymmetric Torsional Frame | 3 stories; Non-symmetric perimeter stiffness | ASCE 7 ELF with Accidental Torsional Eccentricity ($5\%$) | Yes | $113.636\text{ m}^3$ (DCR 0.940) | `create_frame_model`, `apply_gravity_loads`, `apply_lateral_loads`, `run_analysis`, `run_design` | Torsional Drift Amplification Checks |
| **C01** | Dynamic Time-History (El Centro) | 2 bays, 3 stories; $L=6.0\text{ m}, H=3.5\text{ m}$ | 1940 El Centro Accelerogram ($a_{\text{peak}}=0.348g$); Newmark-Beta Integration | Yes | $20.869\text{ m}^3$ (DCR 0.951) | `create_frame_model`, `apply_gravity_loads`, `run_time_history`, `inspect_dynamic_results`, `run_design` | Time-History Response Envelopes & ACI 318 Design |
| **C02** | 3D Dynamic Time-History (Northridge) | $2\times2$ bays, 2 stories; $L_x=6.0\text{ m}, L_y=6.0\text{ m}, H=3.5\text{ m}$ | 1994 Northridge Accelerogram ($a_{\text{peak}}=0.583g$); Step-by-Step Dynamics | No | Linear Dynamics Verification | `create_frame_model`, `run_time_history`, `inspect_dynamic_results` | Floor Acceleration & Drift Time-Series |
| **C03** | CSI SAP2000 Round-Trip CAE | Multi-story space frame (`exported_seismic_frame.s2k`) | Linear Static FEA & ACI 318 Checks; CAE Exchange | Yes | $12.040\text{ m}^3$ (DCR 0.740) | `import_from_sap2000`, `validate_model`, `run_analysis`, `run_design`, `export_to_sap2000` | Re-exported Model: `research_paper/benchmarks/results/exported_sap2000.s2k` |
| **C04** | CSI ETABS Round-Trip CAE | Multi-story space frame (`exported_seismic_frame.e2k`) | Multi-story Connectivity & Boundary Restraints Validation | No | Round-Trip Geometry Parity | `import_from_etabs`, `validate_model`, `run_analysis`, `export_to_etabs` | Re-exported Model: `research_paper/benchmarks/results/exported_etabs.e2k` |
| **C05** | Multimodal Vision Floor Plan Ingestion | 3-story educational facility (`floor_plan_3story_school.PNG`) | Architectural Plan to 3D Frame Compilation (`create_model_from_plan_draft`) | No | Topological Topology Parity | `create_model_from_plan_draft`, `validate_model`, `inspect_project` | Synthesized 3D Project Invariant Model (School Fixture) |
| **C06** | Multimodal Vision-to-Seismic Design | 4-story commercial facility (`mall_plan_4story.PNG`) | Multimodal Compilation $\rightarrow$ Seismic ELF ($S_{DS}=1.2g, R=5$) $\rightarrow$ ACI 318 | Yes | $92.664\text{ m}^3$ (DCR 0.866) | `create_model_from_plan_draft`, `apply_gravity_loads`, `apply_lateral_loads`, `run_analysis`, `run_design` | Full Multimodal Seismic Design (Mall Fixture) |
| **C07** | Dynamic Reflection (El Centro) | 2 bays, 3 stories; Initial $0.30\times0.30\text{ m}$ columns | 1940 El Centro Dynamic Record; Initial $\text{DCR}_0 = 1.38 > 1.0$ | Yes | $20.869\text{ m}^3$ (DCR 0.951) | `create_frame_model`, `run_time_history`, `run_design`, `modify_project` | Dynamic Self-Healing Convergence |
| **C08** | Autonomous Seismic Design-to-CAD | 2 bays, 2 stories; $L=5.0\text{ m}, H=3.2\text{ m}$ | Response Spectrum ($S_{DS}=1.0g, S_{D1}=0.6g$) $\rightarrow$ ACI 318 $\rightarrow$ AutoCAD `.dxf` | Yes | $6.072\text{ m}^3$ (DCR 0.846) | `create_frame_model`, `run_response_spectrum`, `run_design`, `generate_drawings`, `inspect_detailing_results` | Scaled CAD Drawing & BBS: `research_paper/drawings/C08_seismic_frame.dxf` |

---

## 4.3. Real-World Architectural Benchmark Fixtures

To validate multimodal perceptual compilation under realistic architectural layouts, three real-world building floor plans are incorporated as benchmark fixtures:

1. **3-Story Reinforced Concrete School Facility (`floor_plan_3story_school.PNG`)**:
   - *Case Binding*: Case C05 (`C05_Vision_FloorPlan_Draft_Ingestion`).
   - *Structural Layout*: 3 stories at $3.5\text{ m}$ story height, framing an educational facility with overall footprint $21.5\text{ m} \times 9.75\text{ m}$.
   - *Grid Topology*: Orthogonal structural grids Grids A, B, C, D along the longitudinal axis and Grids 1, 2, 3, 4 along the transverse axis. The framing defines standard classroom modules with a central longitudinal circulation corridor.
   - *Role in Benchmarking*: Assesses the Vision-Language Model's ability to interpret structural grid notations, bay spacings, wall/column symbols, and correctly compile a valid, watertight 3D frame model (`FloorPlanDraft` $\rightarrow$ `struct_core.Project`).

2. **2-Story Residential Hostel Block (`hostel_block_plan_2 story.PNG`)**:
   - *Case Binding*: Case B01 (`B01_3D_2x2_2Story_Office`).
   - *Structural Layout*: 2 stories at $3.5\text{ m}$ story height, framing a residential block with overall footprint $27.3\text{ m} \times 10.9\text{ m}$.
   - *Grid Topology*: Multi-bay modular grid system (Grids A through H along the longitudinal axis and Grids 1 through 3 along the transverse axis) with repetitive room units, perimeter columns, and dual-direction framing.
   - *Role in Benchmarking*: Provides the geometric blueprint for multi-bay 3D space frame direct stiffness analysis, validating 3D gravity load takedown and tributary surface load decomposition.

3. **4-Story Commercial Mall Complex (`mall_plan_4story.PNG`)**:
   - *Case Binding*: Case C06 (`C06_Vision_To_Seismic_Design_Pipeline`).
   - *Structural Layout*: 4 stories at $3.2\text{ m}$ story height, framing a commercial retail complex with overall footprint $49'\text{-}0'' \times 36'\text{-}0''$ ($14.94\text{ m} \times 10.97\text{ m}$).
   - *Grid Topology*: Grids 5, 4, 3, 2, 1 along the longitudinal direction and Grids A, B, C, D along the transverse direction, accommodating large open retail spans and centralized column clusters.
   - *Role in Benchmarking*: Forms the ultimate end-to-end stress test: extracting architectural geometry from raster pixels $\rightarrow$ compiling a 3D structural frame $\rightarrow$ applying commercial gravity and high-seismic ASCE 7 ELF lateral forces ($S_{DS}=1.2g, S_{D1}=0.5g, R=5.0$) $\rightarrow$ executing 3D finite element analysis $\rightarrow$ verifying ACI 318 biaxial member capacities.

---

## 4.4. Comparative Baselines & Ablation Configurations

To evaluate the contribution of each architectural component, four comparative configurations are executed across the benchmark suite:

1. **Baseline 1 (Direct Zero-Shot LLM Prompting — `direct_llm`)**:
   - The language model receives natural language structural problem specifications and must directly estimate internal forces, member sizing, and capacity ratios without access to external symbolic tools.
   - *Role*: Quantifies the baseline Calculation Hallucination Rate ($\text{CHR}$) and proves that pure neural reasoning violates physical equilibrium in indeterminate structures.

2. **Baseline 2 (Code-Generation LLM — `code_gen`)**:
   - The language model is prompted to generate standalone executable Python scripts using general numerical libraries (NumPy, SciPy) to model and solve the structural problem.
   - *Role*: Evaluates whether raw code generation without a domain-specific schema or state-machine guardrails can reliably solve complex 3D seismic mechanics without syntax, singularity, or code-compliance failures.

3. **Baseline 3 (Ablated Agent without Reflection — `ablated`)**:
   - The agent is equipped with the complete suite of symbolic tools (`fem2d`, `fem3d`, `structdyn`, `aci318`, `struct_draw`), but the closed-loop self-healing reflection mechanism is disabled. If an initial trial design yields $\text{DCR}_{\text{gov}} > 1.0$, execution terminates immediately as non-compliant.
   - *Role*: Directly isolates the empirical value of the closed-loop diagnostic reflection state machine on Code Compliance Rate ($\text{CCR}$).

4. **Proposed Framework (Full Neuro-Symbolic Agent with Reflection — `full_agent`)**:
   - The complete architecture featuring ontology-grounded validation (`struct_core`), symbolic mechanics solvers, multimodal drawing compilation (`struct_agent.vision`), and closed-loop self-healing redesign driven by $\text{DCR}_{\text{gov}}$ diagnostic feedback.

---

## 4.5. Multi-Model Evaluation Testbed

To test cross-model generalization (Hypothesis H3), benchmarks are evaluated across four prominent Large Language Model backbones representing both proprietary frontier APIs and local/cloud open-weight architectures:

| Model Identifier | Architecture & Provider | Parameter Scale | Deployment Modality | Context Window |
|---|---|:---:|---|:---:|
| **`gemini-3.8-flash`** | Frontier Closed-Source (Google DeepMind) | Proprietary | Cloud API (`google-genai` SDK) | 1,000,000 tokens |
| **`qwen3.5:9b`** | Open-Weight Dense (Alibaba Cloud) | 9B | Local Workstation via Ollama | 32,768 tokens |
| **`gpt-oss:120b-cloud`** | Open-Weight MoE/Dense Foundation Model | 120B | High-Performance Cloud Host via Ollama | 65,536 tokens |
| **`nemotron-3-ultra:cloud`** | Open-Weight Math/Engineering-Tuned (NVIDIA) | Ultra Scale | High-Performance Cloud Host via Ollama | 32,768 tokens |

---

## 4.6. Quantitative Evaluation Metrics

The experimental evaluation employs five rigorous, mathematically formulated metrics:

### 1. Task Completion Rate ($\text{TCR}$)
$$\text{TCR} = \frac{N_{\text{completed}}}{N_{\text{total}}} \times 100\% \quad (N_{\text{total}} = 24)$$
A benchmark run is deemed completed ($N_{\text{completed}}$) if and only if the agent successfully synthesizes or imports a valid `struct_core.Project` passing the symbolic guard $\mathcal{V}(\mathcal{S}) = 1$ and executes all required pipeline tools in `expected_tools` without unhandled runtime exceptions.

### 2. Code Compliance Rate ($\text{CCR}$)
$$\text{CCR} = \frac{N_{\text{compliant}}}{N_{\text{design}}} \times 100\% \quad (N_{\text{design}} = 18)$$
Evaluated strictly across the 18 design-mandated benchmark cases. A completed design is code-compliant if and only if the governing Demand-Capacity Ratio satisfies:
$$\text{DCR}_{\text{gov}} = \max_{e \in \mathcal{E}, \, c \in \mathcal{C}} \left\{ \frac{P_{u,e,c}}{\phi P_{n,e}}, \, \frac{M_{u,e,c}}{\phi M_{n,e}}, \, \frac{V_{u,e,c}}{\phi V_{n,e}} \right\} \le 1.00$$

### 3. Calculation Hallucination Rate ($\text{CHR}$)
$$\text{CHR} = \frac{N_{\text{hallucinated\_claims}}}{N_{\text{total\_numerical\_claims}}} \times 100\%$$
A reported numerical engineering claim (e.g., base shear $V_b$, fundamental period $T_1$, peak bending moment $M_u$, or governing DCR) is classified as a calculation hallucination if it deviates by $>5.0\%$ from the exact deterministic mechanics solution. In the proposed framework, $\text{CHR} = 0.0\%$ by architectural construction.

### 4. Self-Healing Convergence Iterations ($N_{\text{iter}}$)
For benchmark cases initialized with undersized trial cross-sections ($\text{DCR}_{\text{gov}}^{(0)} > 1.0$), $N_{\text{iter}}$ quantifies the number of closed-loop reflection cycles (`modify_project` $\rightarrow$ `run_analysis` $\rightarrow$ `run_design`) required to achieve structural feasibility ($\text{DCR}_{\text{gov}}^{(N_{\text{iter}})} \le 1.0$).

### 5. Volumetric Material Economy Ratio ($\eta_{\text{vol}}$)
$$\eta_{\text{vol}} = \frac{V_{\text{concrete}}^{\text{agent}}}{V_{\text{concrete}}^{\text{baseline}}}$$
where $V_{\text{concrete}} = \sum_{e \in \mathcal{E}} A_e L_e$ is the total structural concrete volume ($\text{m}^3$) of the converged design, and $V_{\text{concrete}}^{\text{baseline}}$ is the verified human engineering baseline volume established by `generate_human_baselines.py`. For cases incorporating full AutoCAD reinforcement drafting (`struct_draw`), the composite material cost metric is additionally inspected:
$$\eta_{\text{material}} = \frac{V_{\text{concrete}}^{\text{agent}} + \alpha W_{\text{steel}}^{\text{agent}}}{V_{\text{concrete}}^{\text{baseline}} + \alpha W_{\text{steel}}^{\text{baseline}}}$$
where $W_{\text{steel}}$ is the total rebar mass (tonnes) extracted from the Bar Bending Schedule, and $\alpha \approx 60\text{--}80$ is the regional unit cost ratio of structural steel to concrete.
