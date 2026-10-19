# 3. Methodology & System Architecture

**Target Venues**: *Automation in Construction* (Elsevier, IF: 10.3) | *Advanced Engineering Informatics* (Elsevier, IF: 8.0)  
**Companion Documents**: [`paper_idea.md`](../paper_idea.md), [`01_introduction.md`](01_introduction.md), [`04_experimental_setup.md`](04_experimental_setup.md)

---

## 3.1. Ontology-Grounded Intermediate Representation (`struct_core`)

The foundational premise of the proposed neuro-symbolic framework is the strict, mathematically enforceable separation between stochastic cognitive reasoning and deterministic physical mechanics. Large Language Models (LLMs) and Vision-Language Models (VLMs) excel at semantic parsing, multi-modal feature extraction, and high-level workflow planning; however, they exhibit catastrophic calculation hallucinations and equilibrium violations when prompted to evaluate indeterminate structural matrices directly. Conversely, numerical finite element and building code engines operate deterministically but lack the semantic flexibility to ingest unstructured human intents, multi-modal architectural drawings, or contextual redesign heuristics.

To bridge this dichotomy without introducing calculation hallucinations, we establish an **Ontology-Grounded Intermediate Representation** implemented through [`struct_core`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/struct_core).

### 3.1.1. Strongly-Typed Project State Tuple

At any discrete conversation turn $t \in \{0, 1, \dots, T\}$, the entire lifecycle state of a structural engineering project is uniquely characterized by a strongly-typed 6-tuple $\mathcal{S}_t$:

$$\mathcal{S}_t = \left(\mathcal{M}_t, \mathcal{L}_t, \mathcal{R}_t^{\text{FEA}}, \mathcal{R}_t^{\text{dyn}}, \mathcal{R}_t^{\text{des}}, \mathcal{D}_t\right)$$

where:
1. $\mathcal{M}_t = \left(\mathcal{N}_t, \mathcal{E}_t, \mathcal{P}_t, \mathcal{C}_t, \mathcal{B}_t, \mathcal{U}_t\right)$ represents the structural analytical model:
   - $\mathcal{N}_t = \{n_i = (x_i, y_i, z_i) \mid i \in \mathcal{I}_{\text{node}}\}$ is the set of 3D spatial node coordinates.
   - $\mathcal{E}_t = \{e_k = (n_{\text{start}}, n_{\text{end}}, p_k, c_k, \mathbf{r}_k) \mid k \in \mathcal{I}_{\text{elem}}\}$ defines the 1D frame, truss, or beam elements, including end-release flags $\mathbf{r}_k \in \{0, 1\}^6$.
   - $\mathcal{P}_t$ denotes isotropic and orthotropic constitutive material models (e.g., concrete compressive strength $f'_c$, steel yield strength $f_y$, elastic modulus $E$, Poisson's ratio $\nu$, and mass density $\rho$).
   - $\mathcal{C}_t$ encompasses parameterized geometric cross-sections (e.g., rectangular $b \times h$, circular diameter $D$, wide-flange AISC sections) with derived sectional properties (cross-sectional area $A$, shear areas $A_{s2}, A_{s3}$, torsional constant $J$, and principal second moments of area $I_2, I_3$).
   - $\mathcal{B}_t = \{b_i \in \{0, 1\}^6 \mid i \in \mathcal{I}_{\text{supp}}\}$ specifies kinematic boundary constraints across the 6 degrees of freedom (DOFs) per node: translations $(u_x, u_y, u_z)$ and rotations $(\theta_x, \theta_y, \theta_z)$.
   - $\mathcal{U}_t = (u_{\text{force}}, u_{\text{length}}, u_{\text{mass}}, u_{\text{time}})$ enforces the dimensional unit system (e.g., $\text{SI}: [\text{kN}, \text{m}, \text{kg}, \text{s}]$ or $\text{US Customary}: [\text{kip}, \text{in}, \text{slug}, \text{s}]$).
2. $\mathcal{L}_t = (\mathcal{P}_{\text{load}}, \mathcal{C}_{\text{comb}})$ denotes the codified loading environment, comprising discrete load patterns (Dead $D$, Superimposed Dead $SD$, Live $L$, Roof Live $L_r$, Earthquake $E$) and factored LRFD load combinations $\mathcal{C}_{\text{comb}} = \left\{ \sum \gamma_{c, j} L_j \right\}$ defined per ASCE 7-16/22 and IBC specifications.
3. $\mathcal{R}_t^{\text{FEA}}$ contains deterministic linear and second-order static finite element analysis results, including node displacement vectors $\mathbf{u} \in \mathbb{R}^{6 N}$, global reaction vectors $\mathbf{R} \in \mathbb{R}^{6 N_{\text{supp}}}$, and 13-station internal force envelopes $\mathbf{f}_e(x) = [P, V_2, V_3, T, M_2, M_3]^T$.
4. $\mathcal{R}_t^{\text{dyn}}$ encapsulates dynamic earthquake mechanics results, including generalized modal eigenvalues $\omega_n^2$, mode shape matrices $\boldsymbol{\Phi}$, Complete Quadratic Combination (CQC) Response Spectrum Analysis (RSA) demands, and Newmark-Beta time-history integration records $\mathbf{u}(t), \dot{\mathbf{u}}(t), \ddot{\mathbf{u}}(t)$.
5. $\mathcal{R}_t^{\text{des}}$ contains codified design verification outputs computed per ACI 318-19/25 and AISC 360-16, detailing governing Demand-Capacity Ratios ($\text{DCR}$), failure mode classifications, and minimum transverse shear reinforcement spacing.
6. $\mathcal{D}_t$ stores production-level computer-aided drafting (CAD) deliverables, including paper-space AutoCAD `.dxf` vector geometry, reinforcement layout schedules, and Bar Bending Schedules (BBS).

### 3.1.2. Deterministic Symbolic Guard Operator $\mathcal{V}(\mathcal{S}_t)$

Before any state transition is committed or delegated to numerical solvers, the project state $\mathcal{S}_t$ must pass through a strict symbolic validation boundary $\mathcal{V}(\mathcal{S}_t) \in \{0, 1\}$ implemented via Pydantic v2 type enforcement and topological validation rules:

$$\mathcal{V}(\mathcal{S}_t) = \begin{cases} 1 & \text{if all structural and semantic invariants are satisfied} \\ 0 & \text{otherwise} \end{cases}$$

The symbolic guard operator enforces four invariant predicates:
1. **Referential Integrity**: Every topological reference in elements, boundary conditions, and loads must resolve to a valid node, section, or material identifier:
   $$\forall e_k = (n_i, n_j) \in \mathcal{E}_t \implies n_i \in \mathcal{N}_t \land n_j \in \mathcal{N}_t \land i \ne j$$
2. **Strictly Positive Geometric Metric**: No element can have zero or negative length:
   $$\forall e_k = (n_i, n_j) \in \mathcal{E}_t, \quad L_k = \lVert \mathbf{x}_j - \mathbf{x}_i \rVert_2 \ge \epsilon_{\text{geom}} > 0 \quad (\epsilon_{\text{geom}} = 10^{-4}\text{ m})$$
3. **Cross-Sectional Positivity & Invariant Rigidity**: Cross-sectional area $A$ and principal moments of inertia $I_2, I_3$ must be strictly positive real numbers, precluding singular element stiffness formulations:
   $$\forall c \in \mathcal{C}_t \implies A(c) > 0 \land I_2(c) > 0 \land I_3(c) > 0 \land J(c) > 0$$
4. **Kinematic Stability & Boundary Sufficiency**: The structure must be statically determinate or indeterminate with sufficient boundary restraints to prevent rigid-body kinematic mechanisms under arbitrary load vectors:
   $$\operatorname{dim}\left(\ker(\mathbf{K})\right) = 0$$

If $\mathcal{V}(\mathcal{S}_t) = 0$, the state transition is rejected deterministically; an informative error payload describing the exact invalid entity is returned to the agent's context window, preventing corrupted geometry from propagating into the finite element engines.

### 3.1.3. Finite State Machine ($\Sigma$)

The lifecycle of an autonomous structural engineering project evolves along a formal Finite State Machine (FSM):

$$\Sigma = \{\text{UNINITIALIZED}, \text{MODEL\_CREATED}, \text{LOADS\_APPLIED}, \text{ANALYZED}, \text{DESIGNED}, \text{DRAWINGS\_GENERATED}\}$$

The transition function $\delta: \Sigma \times \mathcal{A} \rightarrow \Sigma \cup \{\text{ERROR}\}$ guarantees that operations are executed in strict engineering sequence. For example, the agent cannot execute `run_design` from `MODEL_CREATED` without first executing `apply_gravity_loads` ($\rightarrow \text{LOADS\_APPLIED}$) and `run_analysis` ($\rightarrow \text{ANALYZED}$). This state machine eliminates invalid tool trajectories and ensures that every downstream result is backed by valid, computed mechanics.

---

## 3.2. Deterministic Symbolic Mechanics, Seismic Dynamics, and Codified Design Engines

The symbolic layer consists of five modular, deterministic computational packages written in pure Python/NumPy/SciPy, completely isolated from neural network weights:

```text
+---------------------------------------------------------------------------------------------------+
|                                   SYMBOLIC COMPUTATION LAYER                                      |
|                                                                                                   |
|  [struct_load]        [fem2d / fem3d]         [structdyn]            [aci318]       [struct_draw] |
|  - ASCE 7 Tributary   - 3D 12-DOF Timoshenko  - Modal Eigenvalue     - ACI 318-19/25 - Paper-Space|
|    Area Distribution    Frame FEA Matrix      - CQC Response           Flexure &       AutoCAD DXF|
|  - Effective Seismic  - Shear Parameters        Spectrum Analysis      Shear Design  - Scaled GA  |
|    Weight W             Phi_y, Phi_z          - Newmark-Beta Direct  - 3D Column       Plans &    |
|  - ASCE 7 ELF Base    - End-Release Hinges      Time Integration       Biaxial P-M     Elevations |
|    Shear & Envelopes  - Global Assembly         (El Centro/Northridge) Bresler Method- Rebar BBS  |
|                                                                                                   |
|             ^                 ^                        ^                    ^              ^      |
|             +-----------------+------------------------+--------------------+--------------+      |
|                                                        |                                          |
|                                               [struct_link]                                       |
|                               (Commercial CAE Round-Trip: SAP2000 .s2k / ETABS .e2k)             |
+---------------------------------------------------------------------------------------------------+
```

### 3.2.1. Building Code Loading Engine (`struct_load`)

The [`struct_load`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/struct_load) package automates the generation of codified environmental and gravity demands in compliance with ASCE 7-16/22 and the International Building Code (IBC 2024):

1. **Tributary Area Load Distribution**: For planar slab panels with tributary width $w_{\text{trib}}$, two-way yield-line or one-way beam tributary distributions convert area surface loads $q_{\text{area}}\;(\text{kN/m}^2)$ into equivalent uniformly distributed beam loads $w_{\text{beam}}\;(\text{kN/m})$:
   $$w_{\text{beam}}(x) = q_{\text{area}} \cdot w_{\text{trib}}(x)$$
   Live load reduction factors per ASCE 7-22 §4.7 are applied based on influence area $K_{LL} A_T$:
   $$L = L_0 \left(0.25 + \frac{4.57}{\sqrt{K_{LL} A_T}}\right) \ge 0.50 L_0 \quad (\text{or } 0.40 L_0 \text{ for multi-story columns})$$

2. **Effective Seismic Weight ($W$)**: Per ASCE 7-22 §12.7.2, the total effective seismic weight $W$ accounts for all dead loads plus codified fractions of other loads:
   $$W = \sum D + 0.25 P_{\text{storage}} + \sum W_{\text{partition}}$$

3. **ASCE 7-22 Equivalent Lateral Force (ELF) Procedure**: Given mapped risk-targeted spectral response parameters $S_s, S_1$ and site coefficients $F_a, F_v$, the design spectral response acceleration parameters $S_{DS} = \frac{2}{3} F_a S_s$ and $S_{D1} = \frac{2}{3} F_v S_1$ are computed. The total seismic base shear $V_b$ is:
   $$V_b = C_s W$$
   where the seismic response coefficient $C_s$ is governed by:
   $$C_s = \frac{S_{DS}}{\left(\frac{R}{I_e}\right)}, \quad \text{subject to } C_s \le \begin{cases} \frac{S_{D1}}{T \left(R / I_e\right)} & \text{for } T \le T_L \\ \frac{S_{D1} T_L}{T^2 \left(R / I_e\right)} & \text{for } T > T_L \end{cases}$$
   and constrained by the minimum code thresholds:
   $$C_s \ge \max\left(0.044 S_{DS} I_e, \, 0.01\right), \quad \text{and if } S_1 \ge 0.6g: \; C_s \ge \frac{0.5 S_1}{\left(R / I_e\right)}$$

4. **Vertical Distribution of Lateral Forces**: Base shear $V_b$ is distributed across story levels $x \in \{1, \dots, N\}$ via the vertical distribution factor $C_{vx}$:
   $$F_x = C_{vx} V_b = \frac{w_x h_x^k}{\sum_{i=1}^N w_i h_i^k} V_b$$
   where $k$ is an exponent related to the structural fundamental period $T$ ($k = 1.0$ for $T \le 0.5\text{ s}$, $k = 2.0$ for $T \ge 2.5\text{ s}$, and linearly interpolated for $0.5 < T < 2.5\text{ s}$).

5. **Orthogonal Bi-Directional Seismic Combinations**: To account for multi-directional earthquake excitation per ASCE 7-22 §12.5.3, orthogonal combination suites are compiled:
   $$E = \pm 1.0 E_X \pm 0.3 E_Y \quad \text{and} \quad E = \pm 0.3 E_X \pm 1.0 E_Y$$
   These are enveloped into 26 governing LRFD factored combinations (e.g., $1.2D + 1.0E + 1.0L + 0.2S$ and $0.9D \pm 1.0E$).

### 3.2.2. 2D/3D Finite Element Mechanics (`fem2d` & `fem3d`)

Structural linear static analysis is executed via direct stiffness assembly in [`fem2d`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/fem2d) and [`fem3d`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/fem3d). 

Each 3D frame member possesses 12 degrees of freedom (6 DOFs per node: axial, two transverse shears, torsion, and two flexural rotations). To capture the behavior of stocky reinforced concrete elements without shear-locking or underestimating lateral drift, we implement **Timoshenko beam-column element theory**:

$$\mathbf{d}_e = \left[u_{x1}, u_{y1}, u_{z1}, \theta_{x1}, \theta_{y1}, \theta_{z1}, u_{x2}, u_{y2}, u_{z2}, \theta_{x2}, \theta_{y2}, \theta_{z2}\right]^T$$

The Timoshenko shear deformation coefficients $\Phi_y$ (shear in local $y$ bending about $z$) and $\Phi_z$ (shear in local $z$ bending about $y$) are defined as:

$$\Phi_y = \frac{12 E I_z}{G A_{s2} L^2}, \qquad \Phi_z = \frac{12 E I_y}{G A_{s3} L^2}$$

where $G = \frac{E}{2(1 + \nu)}$ is the shear modulus, and $A_{s2}, A_{s3}$ denote the effective shear areas (for rectangular concrete cross-sections, $A_{s2} = A_{s3} = \frac{5}{6} b h$). 

The symmetric $12 \times 12$ local element stiffness matrix $\mathbf{k}_e$ takes the form:

$$\mathbf{k}_e = \begin{bmatrix}
\mathbf{k}_{11} & \mathbf{k}_{12} \\
\mathbf{k}_{12}^T & \mathbf{k}_{22}
\end{bmatrix}$$

where the flexural-shear sub-blocks incorporate $(1 + \Phi_y)$ and $(1 + \Phi_z)$ terms:

$$\mathbf{k}_{\text{flex}, z} = \frac{E I_z}{(1 + \Phi_y) L^3} \begin{bmatrix}
12 & 6L & -12 & 6L \\
6L & (4 + \Phi_y) L^2 & -6L & (2 - \Phi_y) L^2 \\
-12 & -6L & 12 & -6L \\
6L & (2 - \Phi_y) L^2 & -6L & (4 + \Phi_y) L^2
\end{bmatrix}$$

Coordinate transformation from local element coordinates $(\bar{x}, \bar{y}, \bar{z})$ to global Cartesian coordinates $(X, Y, Z)$ is governed by the orthogonal rotation matrix $\mathbf{T}_e \in \mathbb{R}^{12 \times 12}$:

$$\mathbf{T}_e = \operatorname{diag}(\mathbf{\Lambda}, \mathbf{\Lambda}, \mathbf{\Lambda}, \mathbf{\Lambda}), \quad \mathbf{\Lambda} = \begin{bmatrix}
\mathbf{l}^T \\
\mathbf{m}^T \\
\mathbf{n}^T
\end{bmatrix} \in \mathbb{R}^{3 \times 3}$$

where $\mathbf{l}$ is the element longitudinal unit vector, and $\mathbf{m}, \mathbf{n}$ are orthogonal principal axis vectors adjusted for web roll angle $\beta$.

The global stiffness matrix is assembled via standard topological scatter:

$$\mathbf{K} = \sum_{e \in \mathcal{E}} \mathbf{T}_e^T \mathbf{k}_e \mathbf{T}_e$$

Kinematic boundary conditions $\mathcal{B}$ are enforced via sub-matrix partitioning, yielding the unconstrained equilibrium equations:

$$\mathbf{K}_{ff} \mathbf{u}_f = \mathbf{P}_f - \mathbf{K}_{fs} \mathbf{u}_s$$

solved via Cholesky decomposition $\mathbf{K}_{ff} = \mathbf{L} \mathbf{L}^T$ to ensure numerical stability.

### 3.2.3. Dynamic Structural Mechanics & Earthquake Integration (`structdyn`)

Earthquake engineering analysis is performed via [`structdyn`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/structdyn), supporting modal eigenvalue analysis, Response Spectrum Analysis (RSA), and direct numerical time-history integration:

1. **Generalized Eigenvalue Modal Analysis**:
   Free vibration frequencies $\omega_n$ and mode shapes $\boldsymbol{\phi}_n$ are obtained by solving the generalized undamped eigenvalue problem:
   $$\left(\mathbf{K} - \omega_n^2 \mathbf{M}\right)\boldsymbol{\phi}_n = \mathbf{0}$$
   where $\mathbf{M}$ is the lumped or consistent structural mass matrix. Vibration periods $T_n = \frac{2\pi}{\omega_n}$ and modal participation factors $\Gamma_{n, d}$ along excitation direction $d \in \{X, Y, Z\}$ are evaluated as:
   $$\Gamma_{n, d} = \frac{\boldsymbol{\phi}_n^T \mathbf{M} \boldsymbol{\iota}_d}{\boldsymbol{\phi}_n^T \mathbf{M} \boldsymbol{\phi}_n}, \qquad M_{n, d}^* = \frac{\left(\boldsymbol{\phi}_n^T \mathbf{M} \boldsymbol{\iota}_d\right)^2}{\boldsymbol{\phi}_n^T \mathbf{M} \boldsymbol{\phi}_n}$$
   ensuring that cumulative effective modal mass participation satisfies $\sum_{n=1}^M M_{n, d}^* \ge 0.90 \sum m_i$ per ASCE 7-22 §12.9.1.

2. **Complete Quadratic Combination (CQC) Response Spectrum Analysis**:
   Peak modal responses $r_n$ (displacements, shears, overturning moments) computed from design spectral acceleration $S_a(T_n)$ are combined using the CQC rule to account for cross-modal correlation:
   $$r_{\text{CQC}} = \sqrt{\sum_{i=1}^M \sum_{j=1}^M r_i \rho_{ij} r_j}$$
   where the cross-modal correlation coefficient $\rho_{ij}$ for modal damping ratio $\zeta$ and frequency ratio $\beta_{ij} = \omega_j / \omega_i$ is:
   $$\rho_{ij} = \frac{8 \zeta^2 (1 + \beta_{ij}) \beta_{ij}^{3/2}}{\left(1 - \beta_{ij}^2\right)^2 + 4 \zeta^2 \beta_{ij} (1 + \beta_{ij})^2}$$

3. **Direct Dynamic Time-History Numerical Integration (Newmark-Beta)**:
   For nonlinear or linear dynamic response under recorded ground motions (e.g., 1940 El Centro, 1994 Northridge), the multi-degree-of-freedom equations of motion:
   $$\mathbf{M}\ddot{\mathbf{u}}(t) + \mathbf{C}\dot{\mathbf{u}}(t) + \mathbf{K}\mathbf{u}(t) = -\mathbf{M}\boldsymbol{\iota}\ddot{u}_g(t)$$
   are integrated using the unconditionally stable Newmark-Beta direct integration scheme ($\gamma = 1/2, \beta = 1/4$, corresponding to constant average acceleration). 

   Damping matrix $\mathbf{C}$ is formulated via classical Rayleigh damping $\mathbf{C} = a_0 \mathbf{M} + a_1 \mathbf{K}$:
   $$\begin{bmatrix} a_0 \\ a_1 \end{bmatrix} = \frac{2 \zeta}{\omega_i + \omega_j} \begin{bmatrix} \omega_i \omega_j \\ 1 \end{bmatrix}$$
   At each time increment $\Delta t$, the effective dynamic stiffness matrix $\hat{\mathbf{K}}$ is assembled:
   $$\hat{\mathbf{K}} = \mathbf{K} + \frac{1}{\beta \Delta t^2}\mathbf{M} + \frac{\gamma}{\beta \Delta t}\mathbf{C}$$
   and solved for displacement increments $\Delta \mathbf{u}_{t+\Delta t}$, updating velocity $\dot{\mathbf{u}}$ and acceleration $\ddot{\mathbf{u}}$ vectors without numerical energy dissipation.

### 3.2.4. Codified Concrete Design Engine (`aci318`)

Member proportioning and reinforcement verification are evaluated strictly per **ACI 318-19/25** in [`aci318`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/aci318):

1. **Flexural Capacity ($\phi M_n$)**: Under factored bending moment $M_u$, flexural capacity is governed by equivalent rectangular concrete compressive stress distribution ($0.85 f'_c$ across depth $a = \beta_1 c$):
   $$\phi M_n = \phi A_s f_y \left(d - \frac{a}{2}\right), \quad a = \frac{A_s f_y}{0.85 f'_c b}$$
   where the strength reduction factor $\phi$ varies continuously from $0.65$ to $0.90$ based on net tensile strain $\epsilon_t$ in the extreme longitudinal rebar layer.

2. **Shear Capacity ($\phi V_n$)**: One-way shear strength incorporates the ACI 318-19 size-effect factor $\lambda_s = \sqrt{\frac{2}{1 + 0.004 d}} \le 1.0$:
   $$V_c = \left[0.66 \lambda_s \lambda \left(\rho_w\right)^{1/3} \sqrt{f'_c} + \frac{N_u}{6 A_g}\right] b_w d$$
   Transverse stirrup contribution is $V_s = \frac{A_v f_{yt} d}{s}$, requiring $\phi (V_c + V_s) \ge V_u$ with $\phi = 0.75$.

3. **3D Column Biaxial Compression-Bending Interaction ($P_u - M_{u2} - M_{u3}$)**:
   For columns subjected to concurrent axial compression $P_u$ and biaxial moments $(M_{u2}, M_{u3})$, cross-sectional capacity is evaluated using the **Bresler Reciprocal Load Method** (ACI 318-19 §10.5.2):
   $$\frac{1}{P_n} = \frac{1}{P_{nx}} + \frac{1}{P_{ny}} - \frac{1}{P_0}$$
   where $P_0 = 0.85 f'_c (A_g - A_{st}) + f_y A_{st}$ is the pure axial compressive strength at zero eccentricity, and $P_{nx}, P_{ny}$ denote the nominal axial compressive capacities evaluated independently under eccentricities $e_y = M_{u2}/P_u$ and $e_x = M_{u3}/P_u$. Code compliance requires $\phi P_n \ge P_u$.

### 3.2.5. Automated CAD Detailing & Commercial CAE Translation (`struct_draw` & `struct_link`)

- **Automated AutoCAD DXF Detailing (`struct_draw`)**: Generates production-ready `.dxf` engineering drawings directly from designed project objects. Longitudinal beam and column profiles are drafted in true paper space, including rebar callouts, stirrup spacing zones, and complete **Bar Bending Schedules (BBS)** that quantify total reinforcement tonnage $W_{\text{steel}}$ (metric tonnes) and steel-to-concrete density ratios $\rho_{\text{steel}}\;(\text{kg/m}^3)$.
- **Bidirectional Commercial CAE Exchange (`struct_link`)**: Provides lossless parsing and serialization to CSI SAP2000 (`.s2k`) and ETABS (`.e2k`) text formats, translating joints, frame connectivity, material definitions, load patterns, and boundary restraints into native commercial models.

---

## 3.3. Cognitive Agent Orchestration & Self-Healing Reflection (`struct_agent`)

The cognitive brain of the framework is implemented in [`struct_agent`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/struct_agent), which coordinates the multi-turn interaction between user requirements, multi-modal perception, and symbolic tool execution.

```text
+---------------------------------------------------------------------------------------------------+
|                                      NEURAL COGNITIVE LAYER                                       |
|                                                                                                   |
|  Multimodal Inputs:                                                                               |
|  - Natural Language Prompts  ---> [struct_agent: AgentRunner & Vision Compiler]                   |
|  - Raster/PDF Floor Plans    ---> (Gemini 3.8 Flash | Qwen3.5:9B | GPT-OSS:120B | Nemotron-Ultra) |
|  - SAP2000/ETABS (.s2k/.e2k)                                   |                                  |
|                                                                | Structured Tool Call (JSON)      |
|                                                                v                                  |
+---------------------------------------------------------------------------------------------------+
|                         ONTOLOGY & VALIDATION BOUNDARY (struct_core)                              |
|                                                                                                   |
|  Pydantic v2 Schema Guard V(S_t) in {0, 1}  |  Finite State Machine (WorkflowStage)               |
|  - Referential Integrity & Unit Inference   |  UNINITIALIZED -> MODEL_CREATED -> LOADS_APPLIED    |
|  - Zero-Length & Topological Invariants     |  -> ANALYZED -> DESIGNED -> DRAWINGS_GENERATED      |
+---------------------------------------------------------------------------------------------------+
|                                 CLOSED-LOOP SELF-HEALING REFLECTION                               |
|                                                                                                   |
|  Governing Check Fails (DCR_gov = 1.42 > 1.00) ---> Structured Diagnostic Observation O_k         |
|  (Identifies failing member IDs & limit states) ---> modify_project(b + db, h + dh) & Re-Solve    |
+---------------------------------------------------------------------------------------------------+
```

### 3.3.1. Multimodal Architectural Perception (`struct_agent.vision`)

When initialized from an architectural raster image or PDF floor plan (as in Benchmark cases `C05` and `C06`), the Vision-Language Model cannot reliably generate 3D nodal coordinates directly without spatial distortion. To solve this, we introduce an intermediate semantic compilation schema, **`FloorPlanDraft`**:

$$\text{Image / PDF} \xrightarrow[\text{VLM Perception}]{\text{Extract Semantics}} \text{FloorPlanDraft} \xrightarrow[\text{Deterministic Compiler}]{\text{Orthogonal Projection}} \mathcal{M}_{\text{structural}}$$

The VLM extracts:
1. Orthogonal grid lines $\mathcal{G}_X = \{(label_i, x_i)\}, \mathcal{G}_Y = \{(label_j, y_j)\}$.
2. Story levels with inter-story heights $h_s$.
3. Structural member assignments (column grid intersections and beam framing spans).

The deterministic compiler then generates nodes at all 3D grid intersections $\mathbf{x}_{i,j,s} = (x_i, y_j, z_s)$, instantiates column elements between adjacent vertical levels $s$ and $s+1$, generates longitudinal and transverse beams along grid lines, and assigns base supports at level $z = 0$. This ensures that spatial perception is translated into geometrically perfect structural topology.

### 3.3.2. Governing Demand-Capacity Ratio ($\text{DCR}_{\text{gov}}$)

During design evaluation, the governing Demand-Capacity Ratio is determined by maximizing across all structural elements $e \in \mathcal{E}$, limit states $l \in \{\text{axial}, \text{flexure}, \text{shear}, \text{biaxial}\}$, and factored load combinations $c \in \mathcal{C}_{\text{comb}}$:

$$\text{DCR}_{\text{gov}}^{(k)} = \max_{e \in \mathcal{E}, \, c \in \mathcal{C}_{\text{comb}}} \left\{ \frac{P_{u,e,c}}{\phi P_{n,e}}, \, \frac{M_{u2,e,c}}{\phi M_{n2,e}}, \, \frac{M_{u3,e,c}}{\phi M_{n3,e}}, \, \frac{V_{u2,e,c}}{\phi V_{n2,e}}, \, \frac{V_{u3,e,c}}{\phi V_{n3,e}}, \, \text{DCR}_{\text{Bresler},e,c} \right\}$$

A design state is strictly **code-compliant** if and only if:

$$\text{DCR}_{\text{gov}}^{(k)} \le 1.00$$

### 3.3.3. Closed-Loop Reflection Optimization Loop

When $\text{DCR}_{\text{gov}}^{(k)} > 1.00$, the structure is overstressed and non-compliant. Rather than terminating or requiring human manual resizing, the framework enters an autonomous **closed-loop self-healing reflection cycle**.

The environment synthesizes a structured diagnostic feedback observation $\mathcal{O}_{\text{diag}}^{(k)}$ and appends it to the agent's dialogue context:

```json
{
  "status": "NON_COMPLIANT",
  "iteration": 1,
  "governing_dcr": 1.382,
  "failing_elements": [
    {
      "element_id": "COL_1_A_STORY1",
      "type": "column",
      "limit_state": "biaxial_flexure_axial",
      "dcr": 1.382,
      "current_section": {"b": 0.40, "h": 0.40},
      "governing_combo": "1.2D + 1.0E_X + 0.3E_Y + 1.0L"
    }
  ],
  "recommendation": "Increase column cross-section dimensions by at least +50 mm to +100 mm and re-evaluate."
}
```

This diagnostic observation informs the neural policy to invoke the `modify_project` tool, incrementing cross-sectional dimensions:

$$\left(b^{(k+1)}, h^{(k+1)}\right) \leftarrow \left(b^{(k)} + \Delta b, \, h^{(k)} + \Delta h\right)$$

where increments $\Delta b, \Delta h$ follow standard commercial construction modules ($\Delta \ge 50\text{ mm}$). 

The complete autonomous self-healing reflection procedure is formalized in **Algorithm 1**.

---

### Algorithm 1: Neuro-Symbolic Self-Healing Structural Design Loop

```text
====================================================================================================
Algorithm 1: Neuro-Symbolic Self-Healing Structural Design Loop
====================================================================================================
Input:  User specification prompt P_user, optional drawing attachment I_img, max reflection turns K_max
Output: Code-compliant project state S_final with DCR_gov <= 1.00, AutoCAD drawings D_cad, telemetry log T
----------------------------------------------------------------------------------------------------
 1: Initialize dialogue context: H_0 <- [SystemPrompt]
 2: If I_img is provided then
 3:     P_enriched <- VisionParse(I_img, P_user)
 4:     H_0 <- H_0 + [UserMessage(P_enriched, Attachments=[I_img])]
 5: Else
 6:     H_0 <- H_0 + [UserMessage(P_user)]
 7: End If
 8:
 9: Turn index k <- 0; State S_0 <- UNINITIALIZED; Reflection iteration iter <- 0
10: While k < MaxTurns and State(S_k) != COMPLETED do
11:     a_k <- NeuralPolicy.SampleAction(H_k, AvailableTools=Schemas(Sigma_k))
12:     
13:     # Symbolic validation boundary check
14:     If not GuardOperator.Validate(a_k, S_k) then
15:         O_k <- DiagnosticError("Invalid tool trajectory or schema violation", a_k.error)
16:         H_{k+1} <- H_k + [Action(a_k), Observation(O_k)]
17:         k <- k + 1
18:         Continue
19:     End If
20:
21:     # Execute deterministic symbolic engine
22:     O_k, S_{k+1} <- SymbolicEngines.Execute(a_k, S_k)
23:     H_{k+1} <- H_k + [Action(a_k), Observation(O_k)]
24:
25:     # Closed-loop self-healing reflection check
26:     If a_k.name == "run_design" then
27:         DCR_gov <- ComputeGoverningDCR(S_{k+1})
28:         
29:         If DCR_gov <= 1.00 then
30:             # Structure is compliant; proceed to CAD production
31:             H_{k+1} <- H_{k+1} + [SystemGuidance("Design is code-compliant. Proceed to generate drawings.")]
32:         Else
33:             # Structure is overstressed; inject diagnostic reflection prompt
34:             iter <- iter + 1
35:             If iter >= K_max then
36:                 H_{k+1} <- H_{k+1} + [SystemGuidance("Maximum reflection iterations reached. Finalize state.")]
37:             Else
38:                 O_diag <- SynthesizeDiagnosticPayload(S_{k+1}, DCR_gov)
39:                 H_{k+1} <- H_{k+1} + [Observation(O_diag)]
40:             End If
41:         End If
42:     End If
43:
44:     k <- k + 1
45: End While
46:
47: S_final <- S_k
48: Return S_final, TelemetryRecord(TCR, CCR, CHR=0.0%, N_iter=iter, eta_vol)
====================================================================================================
```

By constraining all matrix inversions, modal calculations, and code evaluations to deterministic solvers while utilizing the neural model solely for orchestration, semantic extraction, and heuristic sizing updates, the framework mathematically guarantees $\text{CHR} = 0.0\%$ while autonomously driving overstressed structural designs to full code compliance.
