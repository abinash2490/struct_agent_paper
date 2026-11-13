# Code-Compliance Notes: Gaps and Simplifications

What the design tools (`aci318` against ACI 318-25, `struct_load` against ASCE 7-22) do not implement, and where
they simplify. The manuscript (Sections 4.1 and 6) refers to this list. Every other check that the benchmark
relies on (member strength, Chapter 15 joints, the Chapter 18 requirements of IMF and SMF, slenderness by moment
magnification, story drift and stability) is implemented, with regression tests in its package
(`aci318/tests/test_code_compliance_318_25.py` and the `struct_load` and `struct_agent` test suites).

## Not implemented

- **Combined footings, grade beams, and tension piles.** Each supported column gets an isolated footing, sized for stability and the net allowable soil pressure under the ASCE 7-22 §2.4 service combinations and designed for the factored ones, with the footing's own weight and the soil above it scaled by each combination's dead-load factor. Where no isolated footing within the sizer's range works, the design fails; the tools offer no combined footing, grade beam, or pile as a remedy. Biaxial bending with soil lift-off about both axes superposes the one-way peak pressures (conservative).
- §18.7.3.3 (columns not designed as part of the lateral system, using the alternative to strong-column/weak-beam)
  is not offered.
- Circular columns get member design and slenderness, but no Chapter 18 or joint checks.
- Response-history envelopes (`run_time_history`) get no second-order magnification or drift checks.
- An imported CSI model (C02) has no seismic system, so Chapter 18 is not applied; Chapter 15 joints and slenderness
  are.

## Simplifications (conservative)

- Non-square columns use the smaller dimension and the weaker axis for joint shear and strong-column/weak-beam;
  the column capacity-design shear checks both principal axes (the in-plane axis in a planar frame).
- Frame beams carry no slab: $\sum M_{nb}$ excludes slab bars and the flange.
- Footing one-way and two-way shear use the general provisions (size effect $\lambda_s$, $\rho_w$); ACI 318-25
  §13.2.6.2 permits $\lambda_s = 1$ and $V_c = 2\lambda\sqrt{f'_c} b_w d$ for footings on soil.
- Column hoops are sized up to #5, one leg per longitudinal bar.
- The least dimensions of special moment frame members take the values of ACI 318M-25, 250 mm for the beam
  width (§18.6.2.1(b)) and 300 mm for the column (§18.7.2.1(a)), which are 1.6 % below the 10 in. and 12 in. of
  ACI 318-25. The prompts allow 0.25 m beams and 0.30 m columns with reference to these clauses.
- $M_{2,\min}$ is applied about both axes at once.
- The stability index $Q$ uses the largest $\Sigma P_u$ among the lateral combinations.
- The column $P_u$ range covers all combinations.
- IMF and OMF capacity-design shear uses option (a) ($M_n$ at both ends).
- $P_x = 1.0D + 0.4L$ covers the gravity load of §12.8.6.1.
- Beams assume equal top and bottom steel for $M_{pr}$ and the joint forces.
- A record-spectrum response spectrum analysis (B06) has no $S_{DS}$, so it is not scaled to the ELF base shear.
- Column bar layouts keep each face's bar spacing within 14 in, assuming every bar is tied by a hoop leg or crosstie.
  The 8 in limit of §18.7.5.2(f), for $P_u > 0.3 A_g f'_c$, is checked but not designed for.
- Column bars are not increased for the column capacity-design shear (§18.7.6.1), which more column steel raises;
  the shear is checked with the designed bars.
- Deflections are not computed; design cases use the minimum beam depth ℓ/18.5 of ACI 318-25 Table 9.3.1.1.
