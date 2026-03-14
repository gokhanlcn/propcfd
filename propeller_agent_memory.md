# Propeller Agent Memory File

## Purpose
This file is a **working memory / implementation brief** for an AI coding agent that must build a propeller analysis tool from HydroComp-style project files (`.hcpc` from PropCad and `.hcpl` from PropElements) **without reading PDFs**.

It is **not** a claim of exact proprietary HydroComp internals. It is a practical implementation guide built from:
- HydroComp's textual methodology notes on lifting-line analysis, foil lift/drag corrections, circulation, nozzle contribution, and force distributions. fileciteturn4file0
- HydroComp's tutorial example for the 70 m research vessel, including design inputs and expected behavior. fileciteturn4file1
- The provided sample `.hcpl` output (`RV70m.hcpl`) containing one solved ducted-propeller case with section-by-section results.

## Provenance and Trust Level
Use the following rule:
- Treat **field names and meanings in the `.hcpl` / `.hcpc` files** as authoritative.
- Treat the **methodology text** as authoritative for the overall numerical workflow and terminology. fileciteturn5file7 fileciteturn5file5
- Treat the **exact hidden equations in the PDF** as **not fully recoverable** from text extraction, because several equations appear only as embedded notation images in the exported help pages.
- Therefore implement a **transparent, standard marine lifting-line surrogate**, tuned to follow the HydroComp workflow and to reproduce the sample case within reasonable error.

Do **not** tell the user that the code is an exact clone of PropElements.

---

# 1. Core Modeling Philosophy

HydroComp's methodology is a **lifting-line propeller analysis/design workflow** for marine propellers. The textual document explicitly states that:
- blade sections are represented by foils positioned on helices,
- each section uses an advance angle `beta`,
- induced axial and tangential velocities `(Ua, Ut)` modify the hydrodynamic pitch angle `beta_i`,
- section angle of attack `alpha` is related to pitch angle `phi`,
- 2D foil lift/drag is corrected for real foil geometry and 3D lifting-surface effects,
- circulation is the central unknown linked to lift by Kutta-Joukowski,
- optimum radial circulation follows a Lerbs-type approach,
- nozzle contribution is handled by dimensional-analysis-based correlations rather than direct duct CFD, and
- radial force distributions are integrated to get thrust and torque. fileciteturn5file7 fileciteturn5file5 fileciteturn5file8

So the software must be organized around these layers:
1. Parse geometry and operating point.
2. Build radial stations.
3. Compute local inflow velocities.
4. Solve local section lift / circulation iteratively.
5. Convert section forces to thrust and torque.
6. Add nozzle contribution if ducted.
7. Estimate cavitation metrics and cavitation percent.
8. Compare against the sample `.hcpl` regression case.

---

# 2. File Types and Their Role

## 2.1 `.hcpc` (PropCad)
Use `.hcpc` as the **primary geometry source**.
Important fields:
- `Propeller.BladeCount`
- `Propeller.Diameter`
- `Propeller.ExpAreaRatio`
- `Propeller.PitchMean`
- `Propeller.PitchOfRecord`
- `Propeller.HubDiameter`
- `Propeller.BladeSections.*`
  - `RadialPos`
  - `Chord`
  - `Thickness`
  - `Pitch`
  - `Camber`
  - `SkewAngleDeg`
  - `RakeAft`
  - `BlockageRatio` if present
  - foil coordinate blocks if needed for visualization only

## 2.2 `.hcpl` (PropElements)
Use `.hcpl` as:
- a geometry source if `.hcpc` is absent,
- an operating-point source,
- and most importantly, a **regression / validation target**.

Important `.hcpl` groups:
- `WaterProperties`
- `Propeller`
- `Propeller.BladeSections`
- `LiftingLine`
- `PropellerPerformance`

### Key `.hcpl` operating fields
- `LiftingLine.ConfigTypeIndex`
- `LiftingLine.NozzleTypeIndex`
- `LiftingLine.DesignSpeed`
- `LiftingLine.DesignRPM`
- `LiftingLine.ReferencePower`
- `LiftingLine.CoefVaVs`
- `WaterProperties.Density`
- `WaterProperties.Viscosity`
- `WaterProperties.VaporPressure`
- `Propeller.HubImmersion`

### Key `.hcpl` solved outputs for validation
- `PropellerPerformance.CoefPropulsorJ`
- `PropellerPerformance.CoefPropulsorKT`
- `PropellerPerformance.CoefPropulsorKQ`
- `PropellerPerformance.PropulsorEfficiency`
- `PropellerPerformance.PropulsorThrust`
- `PropellerPerformance.PropulsorTorque`
- `PropellerPerformance.PowerDeliveredPerProp`
- `PropellerPerformance.PercentCavAverage`
- `PropellerPerformance.SigmaN`
- `PropellerPerformance.Sigma07R`
- `PropellerPerformance.NozzleCavInceptionSigmaN`

---

# 3. Units and Conventions

## 3.1 Internal Units
Always convert to SI internally:
- length: m
- speed: m/s
- rpm: rev/min, but use `n = rpm / 60` in 1/s
- pressure: Pa
- density: kg/m^3
- viscosity: m^2/s
- thrust: N
- torque: N·m
- power: W

## 3.2 Direction Conventions
The HydroComp text defines:
- positive axial direction aft,
- positive rotation in ahead rotation direction,
- for right-hand propeller, rotational sense is CW viewed from behind and positive tangential flow is the leading-edge-to-trailing-edge direction. fileciteturn5file7

For implementation, it is enough to keep a consistent scalar convention:
- `Va > 0` = inflow through disk in ahead condition,
- `Ut` reduces effective rotational advance if it is opposite blade rotation,
- `Q > 0` when the shaft must deliver power.

---

# 4. Derived Global Quantities

Given:
- ship speed `Vs`
- wake fraction `w`
- effective wake scaling coefficient `CoefVaVs` if present in `.hcpl`
- shaft rpm `rpm`
- diameter `D`
- water density `rho`

Compute:
- `n = rpm / 60`
- `omega = 2*pi*n`
- if `CoefVaVs` is present, `Va = CoefVaVs * Vs`
- else use `Va = Vs * (1 - w)`
- `J = Va / (n * D)` for nonzero `n` and `D`

For the RV70m sample:
- `Vs = 15.5 kn = 7.973722 m/s`
- `CoefVaVs = 0.841`
- `Va ≈ 6.706 m/s`
- `rpm = 375`, `n = 6.25 1/s`
- `D = 2.1 m`
- `J ≈ 0.510936`, matching the sample result. This is a critical regression check.

---

# 5. Radial Stations and Geometry Preparation

Each blade section corresponds to a radial station.
For every station, construct:
- `r_over_R`
- `R = D/2`
- `r = r_over_R * R`
- `c` = chord [m]
- `t` = thickness [m]
- `P` = local pitch [m]
- `f` = maximum camber [m]
- `skew_deg`
- `rake`
- `blockage_ratio` if available
- `dr` from neighboring stations

### `dr` construction
Use midpoint spacing:
- interior stations: `dr_i = 0.5 * (r[i+1] - r[i-1])`
- first station: one-sided
- last station: one-sided

### Active stations
Use only stations with:
- `r > Rhub`
- `c > 0`
- `t > 0`

The sample `.hcpl` contains 11 blade stations from `r/R = 1.0` down to `0.15`.

---

# 6. Section Kinematics

HydroComp's text states that the section advance angle `beta` is based on axial advance `Va` and local rotational velocity `2*pi*n*r`, and that induced velocities `(Ua, Ut)` change this to a hydrodynamic pitch angle `beta_i`. fileciteturn5file7 fileciteturn5file4

Use these definitions:

## 6.1 Geometric advance angle
`beta = atan2(Va + Vt_mean, 2*pi*n*r)`

Usually `Vt_mean = 0` unless a tangential wake distribution is explicitly provided.

## 6.2 Induced velocities
For analysis mode, solve for:
- `Ua(r)` axial induced velocity
- `Ut(r)` tangential induced velocity

Then use:
- `Vax = Va + Ua + Un`
- `Vtan = 2*pi*n*r - Ut`
- `beta_i = atan2(Vax, Vtan)`
- `Vr = sqrt(Vax^2 + Vtan^2)`

Here:
- `Un` is nozzle-induced axial inflow contribution, zero for open propeller.
- This is consistent with the methodology note that nozzle inflow is shown in `UnAxial` and that the main induced velocities are `Ua` and `Ut`. fileciteturn5file8

## 6.3 Local geometric pitch angle
Use nose-tail pitch angle from local pitch `P`:
`phi = atan( P / (2*pi*r) )`

This is the manufacturing pitch angle.

## 6.4 Angle of attack
Use:
`alpha = phi - beta_i`

This is the 3D section angle of attack before 2D corrections.
This relationship is exactly the one the HydroComp text points toward when it says angle of attack is required to determine pitch angle. fileciteturn5file4

---

# 7. 3D-to-2D Correction Strategy

The methodology PDF explicitly states that PropElements converts the real 3D section angle `alpha` into an equivalent 2D angle `alpha_2D`, using:
- a loading correction,
- a thickness correction,
- and a viscous correction. fileciteturn5file4

The extracted text does not expose the closed-form equations, so implement the following **surrogate correction stack**:

## 7.1 Definitions
- `tc = t / c`
- `fc = f / c`
- `Re = Vr * c / nu`

## 7.2 Surrogate correction model
Use:
- `alpha_load = Ka * alpha`
- `delta_alpha_thick = Kt1 * tc + Kt2 * tc^2`
- `delta_alpha_visc = Kv * CL_guess / max(Re, Re_min)^m`
- `alpha_2D = alpha_load + delta_alpha_thick + delta_alpha_visc`

Recommended defaults:
- `Ka = 1.03` to `1.10`
- `Kt1 = -0.10 rad`
- `Kt2 = -0.40 rad`
- `Kv = 2e4`
- `m = 1.0`
- `Re_min = 1e5`

These are not HydroComp proprietary constants. They are implementation parameters used only to reproduce sensible behavior.

---

# 8. Lift, Drag, and Circulation

The methodology text says:
- lift depends on angle of attack plus camber,
- real foil lift uses scaling factors,
- drag is the sum of minimum profile drag plus additional drag due to angle of attack,
- and circulation is linked to lift through Kutta-Joukowski. fileciteturn4file0

Use the following practical model.

## 8.1 Zero-lift angle
Approximate:
`alpha_0 = -k0 * fc`
with default `k0 = 4.5` in radians-per-unit-camber-ratio equivalent form.

## 8.2 Lift coefficient
Use pre-stall model:
- `CL_lin = a0 * (alpha_2D - alpha_0)`
- `a0 = 2*pi*mu`

Use `mu` as a foil-type lift multiplier.
Defaults:
- Universal foil: `mu = 1.0`
- NACA 16 a=0.8 style: `mu = 0.95` to `1.05`

Cap by a stall envelope:
- `CL_max = CLmax_base + CLmax_fc * fc - CLmax_tc * tc`
- default `CLmax_base = 0.85`
- `CLmax_fc = 8.0`
- `CLmax_tc = 1.2`
- then clamp `CL` to `[-CL_max_neg, CL_max]`
- use `CL_max_neg = 0.8 * CL_max`

This is consistent with the sample `.hcpl`, where section fields include `CL` and `CLmax` and the values rise toward the inner radii. For example the sample has at `r/R=0.7`, `CL=0.335` and `CLmax=1.281`, and at `r/R=0.4`, `CL=0.614` and `CLmax=1.97`. That pattern should be reproduced qualitatively.

## 8.3 Drag coefficient
Use:
- `CD_min = CD0 + CD_tc * tc + CD_tc2 * tc^2 + CD_re * (Re_ref / Re)^p`
- `dCD_alpha = k_drag * (CL - CL_opt)^2`
- `CD = CD_min + dCD_alpha + CD_blockage`

Recommended defaults:
- `CD0 = 0.0045`
- `CD_tc = 0.010`
- `CD_tc2 = 0.12`
- `CD_re = 0.002`
- `Re_ref = 2e6`
- `p = 0.2`
- `k_drag = 0.012`
- `CL_opt = 0.2`

## 8.4 Blockage / cascade drag correction
The methodology text states that blockage can increase drag, especially at thick high-area root sections, and that PropElements applies a fractional correction based on Hadler-inspired logic. It also says blockage ratios below `0.1` cause little correction and values above `0.5` should be avoided. fileciteturn4file0

Use:
- if `blockage_ratio < 0.1`: `CD_blockage = 0`
- else `CD_blockage = k_block * max(blockage_ratio - 0.1, 0)^2`
- default `k_block = 0.10`

## 8.5 Lift from circulation consistency
Use Kutta-Joukowski consistency as the iteration closure:
- dimensional section lift per unit span: `L' = 0.5 * rho * Vr^2 * c * CL`
- circulation from Kutta-Joukowski: `Gamma = L' / (rho * Vr)`

That implies:
`Gamma = 0.5 * Vr * c * CL`

Store `Gamma` in the section output. This corresponds to the HydroComp circulation discussion and to the sample `.hcpl` `Circulation` field. fileciteturn5file5

---

# 9. Induced Velocity Model

The methodology text says PropElements predicts principal induced velocities by a Wrench/Morgan-type method and uses them to compute `beta_i`. fileciteturn5file9

Because the exact formulas are not recoverable from the extracted text, implement a practical surrogate iterative model.

## 9.1 First-pass approximation
Initialize:
- `Ua = 0`
- `Ut = 0`

## 9.2 Iterative update from circulation
At each station, after computing `Gamma`, update induced velocities using blade-element / actuator-inspired forms:
- `sigma_local = B * c / (2*pi*r)`
- `a_ax = CL * sigma_local / (4*sin(beta)^2 + eps)`
- `a_tan = CL * sigma_local / (4*sin(beta)*cos(beta) + eps)`

Then:
- `Ua_new = k_Ua * a_ax * Va`
- `Ut_new = k_Ut * a_tan * (2*pi*n*r)`

Recommended defaults:
- `k_Ua = 0.85`
- `k_Ut = 0.55`

Use under-relaxation:
- `Ua = 0.7*Ua + 0.3*Ua_new`
- `Ut = 0.7*Ut + 0.3*Ut_new`

Stop when sectionwise `|Gamma_new - Gamma_old|` is small.

## 9.3 Calibration note
This is the main place to calibrate the surrogate solver against the sample `.hcpl` section outputs:
- `UIndAxial`
- `UIndTangent`
- `VResultant`
- `BetaDeg`
- `BetaIDeg`
- `AlphaDeg`

The goal is not exact match at every radius, but consistent trend and total-performance agreement.

---

# 10. Section Forces and Total Thrust/Torque

The methodology text says lift and drag at each thin radial slice are aligned into axial thrust and tangential torque directions and then integrated radially. fileciteturn5file8

Use:
- `L' = 0.5 * rho * Vr^2 * c * CL`
- `D' = 0.5 * rho * Vr^2 * c * CD`

For one blade section slice of width `dr`:
- `dL = L' * dr`
- `dD = D' * dr`

Resolve:
- `dT_blade = dL*cos(beta_i) - dD*sin(beta_i)`
- `dQ_blade = (dL*sin(beta_i) + dD*cos(beta_i)) * r`

Total propeller:
- `dT = B * dT_blade`
- `dQ = B * dQ_blade`
- `T_prop = sum(dT)`
- `Q_prop = sum(dQ)`
- `P_delivered = 2*pi*n*Q_prop`

Non-dimensional coefficients:
- `KT = T_prop / (rho * n^2 * D^4)`
- `KQ = Q_prop / (rho * n^2 * D^5)`
- `eta0 = J * KT / (2*pi*KQ)` for open propeller if `KQ > 0`

This matches the sample coefficient structure in `PropellerPerformance`. For the RV70m sample, the target regression values are approximately:
- `J = 0.510936`
- `KT = 0.305724`
- `KQ = 0.0475729`
- `eta = 0.522585`
- `T = 238295 N`
- `Q = 77868.8 N·m`
- `P = 3057.9 kW`

Use these as acceptance targets.

---

# 11. Optimum Circulation Design Mode (Pitch Design)

The methodology PDF explicitly states that optimum radial circulation follows a **Lerbs-type relation**, using ideal efficiency and the ratio of tangents of `beta_i` and `beta`. It further states:
- open propellers use the classic exponent `0.5`,
- ducted propellers in PropElements use exponent `0.25`,
- and an ideal-efficiency reduction constant `k ≈ 0.90` is commonly used. fileciteturn5file5

Therefore in **design mode** (not simple analysis mode):

## 11.1 Target circulation shape
Use a normalized target radial loading function of the form:
- `G_target(r) ∝ (r/R)^m * (eta_i / eta_ref)^k_eta * (tan(beta_i)/tan(beta))^n`

Practical defaults:
- open propeller exponent `n = 0.5`
- ducted propeller exponent `n = 0.25`
- ideal efficiency reduction constant `k_state = 0.90`

Then scale the distribution to meet the required total thrust.

## 11.2 Solve-for modes
Support:
- `Solve for = Thrust` → analyze known geometry at fixed pitch/camber
- `Solve for = Pitch` → adjust pitch distribution to hit thrust / power targets
- optionally later: `Solve for = Pitch + Camber`

In pitch-design mode:
1. start from current `P(r)`
2. solve performance
3. compare `T_prop` with target thrust
4. modify `phi(r)` based on local circulation error
5. smooth pitch distribution
6. re-run until thrust and power constraints are met

This matches the tutorial example, where the software proceeds from analysis of a known geometry to `Solve for = Pitch` with interactive smoothing. fileciteturn5file1

---

# 12. Wake Distribution Handling

The example tutorial says PropElements can use:
- speed-scaled uniform inflow,
- or a user-defined radial wake distribution,
- with mean tangential wake often neglected. fileciteturn5file0

Implement both:

## 12.1 Uniform wake mode
- `Va(r) = Vs * (1 - w)` or `CoefVaVs * Vs`
- `Vt(r) = 0`

## 12.2 Radial wake mode
Let the user provide arrays on `r/R`:
- `Va_ratio(r)`
- optional `Vt_ratio(r)`

Then scale them so the disk-average axial wake matches the requested effective wake fraction or requested `CoefVaVs`.

Use interpolation to each blade section.

---

# 13. Nozzle / Ducted Propeller Rules

The methodology PDF is explicit on three points:
1. nozzle thrust contribution is not from direct analytical nozzle-shape CFD; it is based on dimensional-analysis correlations from model test data,
2. the nozzle changes both thrust and inflow velocity distribution, and
3. nozzle presence changes radial loading through a tip/rim image effect with tip-gap relief. fileciteturn5file8

That means the software should not pretend to derive nozzle thrust from pure geometry.

## 13.1 Ducted configuration flags
Use:
- `ConfigTypeIndex == DuctedFPP`
- `NozzleTypeIndex` (e.g. sample has `37`)
- nozzle length/diameter ratio
- inlet radius / diameter ratio
- effectiveness multiplier
- tip-gap image mode

## 13.2 Nozzle model structure
Represent nozzle effects as three components:

### A. Additional axial inflow
Add `Un(r)` to the axial velocity seen by the blade.
Use a bell-shaped radial weighting with larger influence near tip regions for accelerating nozzles.

Practical surrogate:
- `Un(r) = k_noz_u * F_noz(J, nozzle_type, L_over_D, effectiveness) * shape_tip(r/R)`

### B. Nozzle thrust contribution
Total unit thrust coefficient:
- `KT_total = KTP + KTN`

Propeller torque remains mainly from the propeller:
- `KQ_total ≈ KQ_prop`

For accelerating nozzles, define:
- `KTN = F_KTN(J, nozzle_type, L_over_D, effectiveness)`

Use correlation surfaces or editable polynomial fits by nozzle type.

### C. Tip image / rim effect
For ducted propellers, the methodology says the tip loading is not relieved as in open water, and a rim image / tip-gap image changes circulation. fileciteturn5file5

Implement a tip-loading multiplier:
- `M_tip(r) = 1 + k_tip_image * exp(-((1 - r/R)/s_tip)^2)`

Apply this only in ducted mode.
Use smaller values when tip gap is nonzero.

## 13.3 Nozzle effectiveness multiplier
If the user reduces nozzle effectiveness, decrease both:
- induced inflow `Un`
- nozzle thrust `KTN`

and allow the propeller `KTP` and `KQ` to increase slightly to compensate, which is exactly what the methodology note describes. fileciteturn5file8

## 13.4 Nozzle length correction
The methodology note says nozzle length changes `KTN` and inflow effects, with zero contribution at zero length and nominal behavior at the standard length ratio. fileciteturn5file8

So implement a normalized length factor:
- `f_L = 0` at `L/D = 0`
- `f_L = 1` at standard `L/D`
- smooth extrapolation between `0.6x` and `2.0x` standard length

## 13.5 Nozzle cavitation / breakdown check
The document says nozzle breakdown risk is indicated when tip-speed cavitation number `SigmaN` falls below inception value `SigmaNi`, but the magnitude of breakdown is not predicted. fileciteturn5file8

Implement:
- compute `SigmaN`
- compare to nozzle-type threshold `SigmaNi`
- if `SigmaN < SigmaNi`, raise a warning: `risk of nozzle thrust breakdown`
- do not automatically reduce thrust unless the user enables a conservative penalty model

---

# 14. Cavitation Assessment

## 14.1 What the files tell us
The tutorial example says PropElements evaluates cavitation using a **Burrill chart** analysis and also shows local checks using:
- `Sigma`
- `ChordMin`
- `RLEMin` / `LERadiusMin`
- plus a summary `PercentCavAverage`. fileciteturn5file6

The sample `.hcpl` includes:
- section-level `Sigma`
- `SigmaCheck`
- `ChordMin`
- `ChordMinCheck`
- `LERadiusMin`
- `LERadiusMinCheck`
- total `PercentCavAverage = 30.4039`
- `SigmaN = 1.43766`
- `Sigma07R = 0.282052`
- `NozzleCavInceptionSigmaN = 2.43531`

## 14.2 Practical cavitation model to implement
Because the exact Burrill-chart mapping is not recoverable from the text export, implement a hybrid engineering estimate.

### Step 1. Section cavitation number
For each station:
- local static pressure at section depth:
  - `p_static = p_atm + rho*g*h_local`
- cavitation number based on resultant speed:
  - `sigma_local = (p_static - p_v) / (0.5 * rho * Vr^2)`

If `Sigma` is already stored in `.hcpl`, use it only for validation.

### Step 2. Minimum required cavitation number
Use a surrogate threshold function depending on:
- `CL`
- `tc`
- blade-area / blockage severity
- optionally leading-edge radius adequacy

Recommended form:
- `sigma_req = s0 + s1*CL + s2*CL^2 + s3*tc + s4*blockage_ratio`

### Step 3. Section cavitation severity
- if `sigma_local >= sigma_req`, cavitation severity near zero
- else severity rises smoothly, e.g.
  - `sev_i = clip((sigma_req - sigma_local) / max(sigma_req, eps), 0, 1.5)`

### Step 4. Area-weighted percent cavitation
- section weight `w_i = c_i * dr_i`
- `PercentCavAverage = 100 * sum(w_i * clip(sev_i,0,1)) / sum(w_i)`

### Step 5. Burrill-style local checks
Also compute and report three simple pass/fail diagnostics:
- `SigmaCheck`
- `ChordMinCheck`
- `LERadiusMinCheck`

Use these heuristics:
- `SigmaCheck = Fail` if `sigma_local < sigma_req`
- `ChordMinCheck = Fail` if actual chord is less than cavitation-safe minimum chord estimated from local loading
- `LERadiusMinCheck = Fail` if actual leading-edge radius proxy is less than required radius estimated from loading and inflow

These checks do not need to match HydroComp exactly; they are local warnings, not direct outputs used in thrust/torque integration.

## 14.3 Tip-speed cavitation number
Compute a global nozzle-relevant cavitation number:
- `V_tip = pi * D * n`
- `SigmaN = (p_static_hub - p_v) / (0.5 * rho * V_tip^2)`

This is consistent with the file's `SigmaN` field and the nozzle breakdown note.

---

# 15. Force Distributions

The methodology text explains that the blade is sliced into thin sections and forces are resolved into axial, tangential, and radial components, then shown as force-per-length-per-length distributions for FEA or CFD body-force use. fileciteturn5file8

Implement optional outputs:
- `FAxialDistChord`
- `FTangentDistChord`
- `FRadialDistChord`

Use:
- divide resolved section forces by `c * dr`
- radial force is material/centrifugal if structural output is enabled
- do not use radial material force for CFD body force export

Also provide equivalent point forces and their radial locations by center-of-pressure weighting, because the sample performance output stores these summary values.

---

# 16. Structural Fields

The methodology tutorial says the strength page is **not FEA**, but a cantilever-beam approximation using thrust, torque, rake, skew, and centrifugal tension. fileciteturn4file1

If structural features are implemented later:
- compute section area
- neutral axis
- section modulus
- bending moments from thrust / torque / rake / skew
- tensile stress from rotation
- total stress and safety factors

This is secondary to the thrust/cavitation tool. Do not block the main hydrodynamic solver on structural features.

---

# 17. Minimum Viable Numerical Workflow

Use this exact solver order.

## Analysis mode (known geometry)
1. Parse file and convert units.
2. Build sections and `dr`.
3. Compute `Va`, `J`, `omega`, `R`, `Rh`.
4. If ducted, initialize nozzle model and `Un(r)`.
5. For each section, iterate:
   - initialize `Ua, Ut`
   - compute `beta`, `beta_i`, `alpha`
   - compute `alpha_2D`
   - compute `CL, CD`
   - compute `Gamma`
   - update `Ua, Ut`
   - under-relax until convergence
6. Compute section forces.
7. Integrate to `T`, `Q`, `P`, `KT`, `KQ`, `eta`.
8. If ducted, add `KTN` and recompute total thrust coefficient and total thrust.
9. Compute cavitation section metrics and `PercentCavAverage`.
10. Emit section table and summary.

## Design mode (solve for pitch)
1. Start from current pitch distribution.
2. Run analysis mode.
3. Compare `T` to target thrust and `P` to reference power.
4. Update pitch angle stationwise according to circulation / thrust deficit.
5. Smooth pitch distribution.
6. Repeat until thrust is met and power is below limit.

---

# 18. Regression Target: RV70m Sample

Use the provided sample `.hcpl` as a regression case.

## 18.1 Inputs
- configuration: `DuctedFPP`
- nozzle type: `37`
- `D = 2.1 m`
- `B = 4`
- `EAR = 0.700075`
- `hub immersion = 2.72 m`
- `Vs = 15.5 kn`
- `rpm = 375`
- `rho = 1026 kg/m^3`
- `nu = 1.1892e-6 m^2/s`
- `pv = 1.6709 kPa`
- `CoefVaVs = 0.841`
- reference power `= 2750 kW`

## 18.2 Expected outputs
Target values from the file:
- `J = 0.510936`
- `KT = 0.305724`
- `KQ = 0.0475729`
- `eta = 0.522585`
- `T = 238295 N`
- `Q = 77868.8 N·m`
- `P = 3057.9 kW`
- `TipSpeed = 41.2334 m/s`
- `PercentCavAverage = 30.4039`
- `SigmaN = 1.43766`
- `Sigma07R = 0.282052`

## 18.3 Acceptable initial surrogate error band
For first implementation:
- `J` within 1%
- `KT` within 8%
- `KQ` within 10%
- `eta` within 8%
- `T` within 8%
- `Q` within 10%
- `PercentCavAverage` within 20% relative error

Then calibrate constants to improve match.

---

# 19. Calibration Strategy

Tune in this order:
1. `CoefVaVs` / wake scaling handling → match `J`
2. `Ua`, `Ut` induced velocity multipliers → match `KT`, `KQ`
3. lift-surface correction multipliers → match section `CL`
4. drag coefficients → match `KQ` and power
5. nozzle `Un(r)` and `KTN` parameters → match ducted case thrust
6. cavitation threshold coefficients → match `PercentCavAverage`

Never calibrate everything at once.

---

# 20. What the Agent Must Say and Must Not Say

## Must say
- this is a HydroComp-style lifting-line surrogate
- exact proprietary equations are not fully recoverable from the exported help pages
- the code is calibrated against sample `.hcpl` outputs

## Must not say
- “This is exactly PropElements internally.”
- “Nozzle thrust is solved from exact duct CFD.”
- “The Burrill chart is reproduced exactly.”

---

# 21. Recommended Software Architecture

Use modules like:
- `parser_hcpc.py`
- `parser_hcpl.py`
- `geometry.py`
- `wake.py`
- `lifting_line.py`
- `foil_model.py`
- `nozzle_model.py`
- `cavitation.py`
- `performance.py`
- `batch.py`
- `ui_streamlit.py`

Each section row should expose at least:
- geometry inputs
- `Va`, `Ua`, `Ut`, `Un`
- `Vr`
- `beta_deg`, `beta_i_deg`, `alpha_deg`
- `Re`
- `CL`, `CLmax`, `CD`
- `Gamma`
- `Sigma`
- local cavitation checks
- `dT`, `dQ`

---

# 22. Final Implementation Priority

If time is limited, implement in this order:
1. parse `.hcpc` and `.hcpl`
2. single operating-point analysis for open propeller
3. ducted/nozzle correction layer
4. cavitation estimate
5. batch multi-file comparison
6. pitch-design mode
7. structural outputs

That priority is justified by the tutorial flow and by the user's stated need for thrust and cavitation calculations. fileciteturn5file2 fileciteturn5file1

---

# 23. Short Executive Summary for the Agent

Implement a **marine propeller lifting-line surrogate**.

Use the HydroComp-style workflow:
- `Va` + rotation → `beta`
- solve induced velocities `(Ua, Ut)` → `beta_i`
- use local pitch to get `alpha`
- convert `alpha` to equivalent 2D angle
- compute `CL`, `CD`, circulation `Gamma`
- resolve forces and integrate to `T`, `Q`, `P`, `KT`, `KQ`, `eta`
- add nozzle inflow/thrust correction in ducted mode
- estimate cavitation percent from local sigma-vs-threshold deficit
- validate against `RV70m.hcpl`

This is the operational memory the coding agent should follow.
