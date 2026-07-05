"""Ducted (Kort-nozzle) propeller model from actuator-disk momentum theory.

This replaces the previous nozzle code, which double-counted the duct thrust by
adding an (incorrect) Oosterveld KTN polynomial on top of a BEMT that was *also*
given a fixed +40% inflow boost. Here there is a single, self-consistent
momentum picture and the duct thrust is the *increment over the open propeller*
implied by it -- nothing is added twice.

PHYSICS
-------
Actuator-disk-in-a-duct theory (e.g. Carlton, "Marine Propellers and
Propulsion", Ch. 13; Kuiper, "The Wageningen Propeller Series"): an accelerating
duct raises the mass flow through the disk, so the system carries more thrust
than the bare propeller for the same delivered power. The augmentation is
largest at heavy loading (bollard) and fades to zero -- then to a small viscous
penalty -- as the advance ratio increases.

We express the system thrust as

    T_total = Tp0 * A_duct(g)  -  D_friction(Va)                          (1)

with
    g        = CTh / (CTh + CTh_half)          loading blend in [0,1)
    A_duct   = 1 + (A_bollard - 1) * g          thrust augmentation factor
    CTh      = Tp0 / (0.5 rho A Vref^2)          propeller thrust loading
    D_fric   = Cd_duct * 0.5 rho Va^2 * (pi D L) duct skin-friction drag

``A_bollard`` (~1.4 for 19A, ~1.3 for 37) is anchored to the documented Ka 4-70
bollard-thrust augmentation and exposed to the user. The duct adds no shaft
torque, so Q_total = Q0 to first order and the efficiency benefit
(eta = A_duct * eta_open at fixed power) stays bounded below 1.

Behaviour by construction:
  * heavy loading / bollard:  A_duct -> A_bollard, large positive duct thrust;
  * design point:             modest augmentation;
  * light loading / high J:   A_duct -> 1 and the friction term makes the duct a
                              small net drag -- the realistic accelerating-duct
                              penalty the old model never produced.

For the cavitation distribution the blades are additionally re-solved with the
tip loss disabled (the duct fills the tip gap and suppresses tip-vortex
roll-up), and that distribution is normalised to the blade thrust so the section
loads remain consistent with the total.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Dict, Optional

from ..models import PropellerGeometry, OperatingConditions
from .openwater import OpenWaterConstants, solve_bemt, BemtResult


@dataclass
class DuctConstants:
    A_bollard: float          # ahead system thrust augmentation at bollard (T_total/Tp0)
    A_bollard_astern: float   # astern augmentation -- 19A loses its duct benefit,
                              # 37's rounded trailing edge keeps most of it
    CTh_half: float           # thrust loading at which the augmentation is half-developed
    Cd_duct: float            # duct skin-friction drag coefficient
    L_over_D: float           # duct length / propeller diameter
    display_name: str
    note: str


# Anchored to documented accelerating-duct behaviour (Ka 4-70 in 19A / 37).
# Astern: 19A is designed for one direction (sharp trailing edge becomes a poor
# leading edge in reverse) -> almost no duct benefit; nozzle 37's rounded
# trailing edge is the reason it exists -> retains most of its augmentation.
DUCT_LIBRARY: Dict[str, DuctConstants] = {
    "19A": DuctConstants(A_bollard=1.40, A_bollard_astern=1.05, CTh_half=2.0,
                         Cd_duct=0.008, L_over_D=0.5,
                         display_name="MARIN/Wageningen 19A",
                         note="Accelerating duct; ~1.4x bollard thrust ahead, weak astern."),
    "37":  DuctConstants(A_bollard=1.30, A_bollard_astern=1.22, CTh_half=2.4,
                         Cd_duct=0.010, L_over_D=0.5,
                         display_name="MARIN/Wageningen 37",
                         note="Milder accelerating duct; lower ahead thrust, strong astern."),
}


@dataclass
class DuctedResult:
    open_bemt: BemtResult       # bare-propeller solution (loading gauge)
    dist_bemt: BemtResult       # tip-loss-free distribution for cavitation
    Tp0: float                  # open-water blade thrust
    Q: float                    # shaft torque (~ open-water torque)
    Td: float                   # net duct thrust (increment over open prop)
    T_total: float
    A_duct: float               # realised thrust augmentation factor
    tau: float                  # duct thrust share Td / T_total
    CTh: float
    D_friction: float
    u_duct: float               # duct-induced axial inflow at the disk [m/s]
    warnings: list


def get_duct(nozzle_id: str) -> Optional[DuctConstants]:
    return DUCT_LIBRARY.get(nozzle_id)


def solve_ducted(geom: PropellerGeometry,
                 cond: OperatingConditions,
                 ow_consts: OpenWaterConstants,
                 duct: DuctConstants,
                 effectiveness: float = 1.0,
                 direction: str = "ahead") -> DuctedResult:
    """Solve the propeller-in-duct system (see module docstring)."""
    warnings: list = []
    n = cond.rpm / 60.0
    omega = 2.0 * math.pi * n
    Va = cond.Va_ship * (1.0 - cond.w)
    D, R, Rh = geom.diameter, geom.radius, geom.hub_radius
    A = math.pi * (R ** 2 - Rh ** 2)
    if A <= 0:
        A = 1e-6

    # 1. Bare-propeller blade solution -> loading gauge.
    open_res = solve_bemt(geom, cond, ow_consts)
    Tp0 = max(open_res.T, 0.0)
    Q0 = open_res.Q

    # 2. Thrust-loading coefficient (Vref floored to regularise bollard).
    Vref = max(Va, 0.05 * omega * R)
    CTh = Tp0 / (0.5 * cond.rho * A * Vref ** 2) if Vref > 0 else 0.0
    g = CTh / (CTh + duct.CTh_half) if CTh > 0 else 0.0

    # 3. Augmentation factor and duct friction drag (effectiveness scales the
    #    *augmentation* the duct adds, not the bare propeller). Astern uses the
    #    reduced astern augmentation (19A loses its benefit, 37 keeps most).
    A_bollard = duct.A_bollard_astern if direction == "astern" else duct.A_bollard
    A_duct = 1.0 + (A_bollard - 1.0) * g * effectiveness
    L = duct.L_over_D * D
    D_friction = duct.Cd_duct * 0.5 * cond.rho * Va ** 2 * (math.pi * D * L)

    # 4. System thrust, duct share, torque.
    T_total = Tp0 * A_duct - D_friction
    Td = T_total - Tp0
    tau = (Td / T_total) if abs(T_total) > 1e-9 else 0.0
    Q = Q0

    if T_total <= 0 and Tp0 > 0:
        warnings.append("Net ducted thrust <= 0 (duct drag dominates at this advance ratio).")

    # 5. Section distribution for cavitation. The duct accelerates the axial
    #    inflow, so the blades run at a LOWER angle of attack (and CL) than the
    #    bare propeller -- this is the physical reason a ducted propeller sheet-
    #    cavitates less. We solve the distribution with that augmented inflow and
    #    the tip loss removed (the duct suppresses tip-vortex roll-up), then
    #    normalise the loads to the in-duct blade thrust.
    Vinf0 = math.sqrt(max(Va * Va + 2.0 * Tp0 / (cond.rho * A), 0.0))
    Vd0 = 0.5 * (Va + Vinf0)
    u_duct = Vd0 * tau / (1.0 - tau) if tau < 0.99 else 0.0
    Tp_in_duct = (1.0 - tau) * T_total
    dist = solve_bemt(geom, cond, ow_consts, va_augment=u_duct, apply_tip_loss=False)
    if dist.T > 1e-9 and Tp_in_duct > 0:
        scale = Tp_in_duct / dist.T
        for s in dist.sections:
            s.dT *= scale
            s.dQ *= scale
            s.Gamma *= scale

    return DuctedResult(open_bemt=open_res, dist_bemt=dist, Tp0=Tp0, Q=Q,
                        Td=Td, T_total=T_total, A_duct=A_duct, tau=tau,
                        CTh=CTh, D_friction=D_friction, u_duct=u_duct, warnings=warnings)
