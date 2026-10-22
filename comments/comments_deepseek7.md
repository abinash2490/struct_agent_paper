Only the items below remain. The previous code-level fixes (seeds, temperature, CAE modal extraction, CHR plots) are correct. The issues below stem from analyzing the actual fixture drawings you just provided. 

---

## P0 — Fix Target Constraints for Vision Cases

### 1. C05 (School Floor Plan) fails PSFR on bay widths
**File:** `benchmark_cases.json` → `C05_Vision_FloorPlan_Draft_Ingestion`

The `floor_plan_3story_school.PNG` shows **irregular** bay spans:
*   X-axis (Grids A–D): 8.484 m, 4.170 m, 8.484 m
*   Y-axis (Grids 1–4): 2.600 m, 2.650 m, 4.651 m

The `target_constraints` enforces uniform `"bay_width": 6.0`. A VLM that correctly extracts the dimensions from the drawing will **fail** `evaluate_prompt_to_schema_fidelity` (tolerance is ±0.15 m).

**Fix:** Remove `"bay_width"`, `"bay_width_x"`, and `"bay_width_y"` from C05's `target_constraints` in `benchmark_cases.json`. Keep `"bays_x": 3` and `"bays_y": 3`. 

### 2. C06 (Mall Floor Plan) fails PSFR on metric conversions
**File:** `benchmark_cases.json` → `C06_Vision_To_Seismic_Design_Pipeline`

The `mall_plan_4story.PNG` shows dimensions in feet/inches (e.g., 12', 13', 11'). The `target_constraints` currently enforces strict metric averages (`"bay_width_x": 3.735`, `"bay_width_y": 3.66`). A VLM that correctly extracts "13'" and converts it to meters (3.96 m) will fail the ±0.15 m span tolerance.

**Fix:** Remove `"bay_width"`, `"bay_width_x"`, and `"bay_width_y"` from C06's `target_constraints`. Let the metric verify only the bay counts (`"bays_x": 4`, `"bays_y": 3`).

---

## P1 — Naming and Documentation Consistency

### 3. B01 name contradicts the prompt and fixture
**File:** `benchmark_cases.json` and `README.md`

`B01_3D_2x2_2Story_Residential` is named "Hostel Block" in the README, but the prompt asks for a basic `2x2` frame, and the actual `hostel_block_plan_2story.PNG` fixture shows a `7x2` bay layout. Because B01 does not load an image, it is a pure text case, making the "Hostel" naming misleading.

**Fix:** 
* In `benchmark_cases.json`, rename the case ID to `B01_3D_2x2_2Story_Gravity` and change the `"name"` to `"3D Space Frame (2x2, 2-Story Gravity)"`.
* In `benchmarks/README.md`, update the B01 description to remove the "2-story hostel block plan" wording.

---

## P2 — Minor Script Cleanup

### 4. `verify_cae_parity.py` version strings mismatch
**File:** `verify_cae_parity.py` (top of file)

The constants say `SAP2000 v27.0.0` and `ETABS v23.0.0`, but the hardcoded test data and printed tables use `v24.0.0` and `v21.0.0`.

**Fix:** Revert the constants to match the data:
```python
SAP2000_VERSION = "CSI SAP2000 v24.0.0 (Build 1865)"
ETABS_VERSION = "CSI ETABS v21.0.0 (Build 2430)"
```

---

## Definition of Done
1. `python -m json.tool research_paper/benchmarks/benchmark_cases.json` runs clean, and C05/C06 no longer contain `bay_width` keys.
2. B01 is renamed and the README no longer claims it uses the hostel floor plan.
3. `verify_cae_parity.py` version strings match the v24/v21 tables.
4. Run the test suite: `pytest research_paper/tests -v` — ensure no PSFR tests break from removing the C05/C06 bay width checks.

Once these are done, the benchmark suite is fully aligned with the fixture drawings and ready for the 5-seed campaign.