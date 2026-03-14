# Propeller Agent Memory / Implementation Reference

- **Methodology Pipeline**: Section-based approach extending 2D foil data with 3D tip/hub losses.
- **Workflow**: Parse `.hcpc` -> Apply Geometry Model -> Extract Sections (r/R, chord, pitch, thickness, camber) -> Compute induced/effective velocities -> Compute local lift/drag -> Integrate for Thrust/Torque.
- **Vessel Context**: `Va = Va_ship * (1 - w)` where ship speed and wake fraction dictate the inflow.
- **Cavitation**: A suction factor $k=1.35$ limits the maximum allowable $-C_p$. Estimated fraction based on relative depth vs static pressure.
- **Propeller Types and Nozzles**: Nozzles are strictly empirical modifiers to total $dK_T$, $dK_Q$. "No direct CFD" is strictly enforced for nozzles.
- **Validation**: RV70m-like setups confirm sanity. Output MUST provide $K_T, K_Q, \eta_o$, section distributions, avoiding negative values without explicit warnings.
