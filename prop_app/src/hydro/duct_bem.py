"""Axisymmetric vortex-ring panel method for the duct (experimental).

This is an ALTERNATIVE, higher-fidelity route to the duct-induced inflow that
does NOT touch the production momentum model in ``ducted.py``. It follows the
methodology requested for the project:

  1. Discretise the duct camber line (built from the real scaled X-Y nozzle
     coordinates) into a set of axisymmetric ring vortices.
  2. Impose flow tangency on the camber line and solve the linear influence
     system for the ring circulations gamma_j.
  3. Use Biot-Savart (circular-vortex-filament velocity, via complete elliptic
     integrals) to evaluate the duct-induced axial velocity field u_a(r) exactly
     at the propeller plane.
  4. Local propeller kinematics: V_A(r) = V_inflow*(1-w) + u_a(r).
  5. Feed the local velocity field into a per-radius cavitation evaluation
     (local sigma + Burrill), instead of any KT/KQ regression.

The SIGN of u_a(r) is an OUTPUT of the geometry, not an assumption: an
accelerating (converging) duct yields u_a > 0, a decelerating (diverging) duct
yields u_a < 0. The method therefore decides, objectively from the coordinates,
whether 19A / 37 accelerate or decelerate.

Numerical notes:
  * The ring self/near influence is desingularised with a finite vortex core
    (~half a panel length) -- a standard regularised-ring treatment. The u_a
    sign and radial shape are robust; the absolute magnitude carries this one
    modelling parameter (``core_fraction``).
  * The camber-line (thin-duct) model captures the geometry-driven acceleration
    in the free stream; the additional propeller-loading-driven duct circulation
    is not included here (that is what the momentum model in ``ducted.py``
    lumps into its augmentation factor).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List
import numpy as np
from scipy.special import ellipk, ellipe

import math
from ..models import PropellerGeometry, OperatingConditions
from ..nozzle_library import get_nozzle_geometry
from ..nozzle_geometry import generate_scaled_nozzle
from .openwater import OpenWaterConstants, _section_cl_cd, solve_bemt
from .cavitation import (CavitationConstants, section_cavitation,
                         burrill_back_cavitation, tip_leakage_tvc, TipLeakageTVC)


def ring_velocity(a: np.ndarray, xc: np.ndarray, x: np.ndarray, r: np.ndarray,
                  core2: float = 0.0):
    """Velocity at field point (x, r) induced by a unit-circulation ring of
    radius ``a`` at axial station ``xc``. Returns (u_x, u_r) per unit Gamma.

    Uses the closed-form circular vortex-filament field with complete elliptic
    integrals K(m), E(m) (scipy m = k^2 convention). ``core2`` desingularises
    the near field.
    """
    r = np.maximum(r, 1e-9)
    dx = x - xc
    s2 = (a + r) ** 2 + dx ** 2 + core2
    d2 = (a - r) ** 2 + dx ** 2 + core2
    m = 4.0 * a * r / s2
    m = np.clip(m, 0.0, 1.0 - 1e-10)
    K = ellipk(m)
    E = ellipe(m)
    s = np.sqrt(s2)
    ux = (1.0 / (2.0 * np.pi)) * (1.0 / s) * (K + (a ** 2 - r ** 2 - dx ** 2) / d2 * E)
    ur = (1.0 / (2.0 * np.pi)) * (dx / (r * s)) * (-K + (a ** 2 + r ** 2 + dx ** 2) / d2 * E)
    return ux, ur


@dataclass
class DuctBEMResult:
    r_over_R: np.ndarray          # radial stations at the propeller plane
    r: np.ndarray                 # radii [m]
    u_a: np.ndarray               # duct-induced axial velocity at prop plane [m/s]
    V_A: np.ndarray               # local axial inflow V_inflow*(1-w) + u_a [m/s]
    V_inflow_axial: float         # V_inflow*(1-w) [m/s]
    mean_u_a: float               # span-averaged u_a [m/s]
    accelerating: bool            # mean_u_a > 0
    x_cam: np.ndarray             # camber node axial positions [m]
    r_cam: np.ndarray             # camber node radii [m]
    gamma: np.ndarray             # solved ring circulations
    note: str = ""


def _build_camber(prop_geom: PropellerGeometry, nozzle_id: str,
                  clearance_override: Optional[float], n_panels: int):
    ndef = get_nozzle_geometry(nozzle_id)
    if ndef is None:
        return None
    scaled = generate_scaled_nozzle(prop_geom, ndef, clearance_m_override=clearance_override)
    if scaled is None:
        return None
    x = np.asarray(scaled.x_m, dtype=float)
    r_cam = 0.5 * (np.asarray(scaled.r_in_m) + np.asarray(scaled.r_out_m))
    # resample to n_panels nodes along the profile
    idx = np.linspace(0, len(x) - 1, n_panels).astype(int)
    return x[idx], r_cam[idx]


def solve_duct_bem(prop_geom: PropellerGeometry, nozzle_id: str,
                   V_inflow: float, w: float,
                   clearance_override: Optional[float] = None,
                   n_panels: int = 60, core_fraction: float = 0.5,
                   v_prop_induced: float = 0.0) -> Optional[DuctBEMResult]:
    """Solve the duct ring-vortex system and return u_a(r) at the prop plane.

    The duct responds to the TOTAL axial flow through it, i.e. the ship advance
    PLUS the axial velocity the propeller itself draws through the duct
    (``v_prop_induced``). Without the propeller term the method degenerates to
    zero at bollard (V_inflow = 0); with it, the duct still accelerates the
    propeller-pumped flow, as it physically does.
    """
    cam = _build_camber(prop_geom, nozzle_id, clearance_override, n_panels)
    if cam is None:
        return None
    xc, rc = cam
    N = len(xc)
    Va_axial = V_inflow * (1.0 - w) + v_prop_induced

    # Panel geometry: control points at nodes, tangents/normals from centred diff.
    dx = np.gradient(xc)
    dr = np.gradient(rc)
    seg = np.hypot(dx, dr)
    seg[seg < 1e-12] = 1e-12
    tx, tr = dx / seg, dr / seg
    nx, nr = -tr, tx                       # unit normal (rotate tangent +90 deg)
    panel_len = float(np.mean(seg))
    core2 = (core_fraction * panel_len) ** 2

    # Influence matrix: A[i,j] = (velocity at ctrl i from unit ring j) . n_i
    A = np.zeros((N, N))
    for j in range(N):
        ux, ur = ring_velocity(rc[j], xc[j], xc, rc, core2=core2)
        A[:, j] = ux * nx + ur * nr

    # Tangency BC: A gamma = -(freestream . n) = -Va_axial * nx
    rhs = -Va_axial * nx
    gamma = np.linalg.solve(A, rhs)

    # Duct-induced axial velocity at the propeller plane (x = 0) across the disk.
    R_prop, Rh = prop_geom.radius, prop_geom.hub_radius
    r_eval = np.linspace(max(Rh, 0.05 * R_prop), 0.995 * R_prop, 25)
    u_a = np.zeros_like(r_eval)
    for j in range(N):
        ux, _ = ring_velocity(rc[j], xc[j], np.zeros_like(r_eval), r_eval, core2=core2)
        u_a += gamma[j] * ux

    V_A = Va_axial + u_a
    mean_u = float(np.mean(u_a))
    return DuctBEMResult(
        r_over_R=r_eval / R_prop, r=r_eval, u_a=u_a, V_A=V_A,
        V_inflow_axial=Va_axial, mean_u_a=mean_u, accelerating=(mean_u > 0),
        x_cam=xc, r_cam=rc, gamma=gamma,
        note=f"{N}-ring camber-line panel method, core={core_fraction:.2f} panel",
    )


@dataclass
class DuctBEMCavitation:
    bem: DuctBEMResult
    section_rR: List[float] = field(default_factory=list)
    section_VA: List[float] = field(default_factory=list)     # local axial inflow [m/s]
    section_VR: List[float] = field(default_factory=list)     # local relative velocity [m/s]
    section_sigma: List[float] = field(default_factory=list)  # local cavitation number
    section_sheet: List[float] = field(default_factory=list)  # local sheet severity [0-1]
    T_blade: float = 0.0
    sheet_pct: float = 0.0
    tip_pct: float = 0.0
    combined_pct: float = 0.0
    burrill_back_pct: float = 0.0
    sigma_0_7R: float = 0.0
    tvc: Optional[TipLeakageTVC] = None    # analytical tip-leakage-vortex result
    note: str = ""


def solve_duct_bem_cavitation(geom: PropellerGeometry, cond: OperatingConditions,
                              nozzle_id: str,
                              ow: Optional[OpenWaterConstants] = None,
                              cav: Optional[CavitationConstants] = None,
                              clearance_override: Optional[float] = None,
                              n_panels: int = 60,
                              tvc_C_D: float = 0.7,
                              tvc_core_factor: float = 5.0) -> Optional[DuctBEMCavitation]:
    """Panel-method duct inflow -> local blade kinematics -> local cavitation.

    Implements the requested pipeline: the duct-induced u_a(r) sets the true
    local axial velocity V_A(r) at every blade section; the local relative
    velocity and cavitation number are formed from V_A(r) (NOT from a KT/KQ
    regression) and fed into the bounded sheet and Burrill cavitation checks.
    """
    ow = ow or OpenWaterConstants()
    cav = cav or CavitationConstants()
    V_inflow = cond.Va_ship

    n = cond.rpm / 60.0
    omega = 2.0 * math.pi * n
    R, Rh, B = geom.radius, geom.hub_radius, geom.blade_count

    # Propeller-induced axial velocity through the duct (from a bare-prop pass),
    # so the panel method works at bollard where the free stream is zero.
    A_disk = math.pi * (R ** 2 - Rh ** 2)
    open_bemt = solve_bemt(geom, cond, ow)
    Va0 = V_inflow * (1.0 - cond.w)
    v_prop = 0.5 * (math.sqrt(max(Va0 ** 2 + 2.0 * max(open_bemt.T, 0.0) / (cond.rho * max(A_disk, 1e-9)), 0.0)) - Va0)

    bem = solve_duct_bem(geom, nozzle_id, V_inflow, cond.w,
                         clearance_override=clearance_override, n_panels=n_panels,
                         v_prop_induced=v_prop)
    if bem is None:
        return None

    # Lifting-line interaction: feed the panel-method radial field u_a(r) into
    # the blade-element momentum solver so the blades carry their own axial+swirl
    # induction on top of the duct inflow (tip loss off -- the duct fills the gap).
    rR_tab = np.asarray(bem.r_over_R)
    ua_tab = np.asarray(bem.u_a)

    def ua_of_rR(rr: float) -> float:
        return float(np.interp(rr, rR_tab, ua_tab))

    bemt = solve_bemt(geom, cond, ow, va_augment_radial=ua_of_rR, apply_tip_loss=False)
    if not bemt.sections:
        return None

    # --- Analytical tip-leakage-vortex cavitation (replaces the 0.15 fudge) ---
    # Evaluated at the outermost blade section, driven by the physical tip gap.
    ndef = get_nozzle_geometry(nozzle_id)
    delta = (clearance_override if clearance_override is not None
             else (ndef.default_tip_clearance_ratio * geom.diameter if ndef else 0.01 * geom.diameter))
    tip_sec = max(bemt.sections, key=lambda s: s.r_over_R)
    P_local_tip = cond.p_atm + cond.rho * cond.g * (cond.h - tip_sec.r)
    tvc = tip_leakage_tvc(cond.rho, tip_sec.Vrel, tip_sec.CL, tip_sec.chord,
                          delta, P_local_tip, cond.pv,
                          C_D=tvc_C_D, core_factor=tvc_core_factor)

    sec_rR, sec_VA, sec_VR, sec_sig, sec_sheet = [], [], [], [], []
    sum_sheet = sum_tip = sum_comb = sum_w = 0.0
    T_blade = bemt.T

    for s in bemt.sections:
        tc = s.thickness / s.chord if s.chord > 0 else 0.0
        V_A = V_inflow * (1.0 - cond.w) + ua_of_rR(s.r_over_R)
        p_ref = cond.p_atm + cond.rho * cond.g * (cond.h - s.r)
        q = max(s.q_dyn, 1e-6)
        sc = section_cavitation(p_ref - cond.pv, q, s.CL, tc, s.r_over_R, s.Re, cav)

        # Tip region blends in the analytical tip-leakage-vortex severity.
        span = max(cav.tip_end_rR - cav.tip_start_rR, 1e-3)
        tip_factor = max(min((s.r_over_R - cav.tip_start_rR) / span, 1.0), 0.0)
        tip_sev = tip_factor * tvc.severity
        combined = max(sc.sheet_severity, tip_sev)

        area_w = s.chord * s.dr
        sum_sheet += sc.sheet_severity * area_w
        sum_tip += tip_sev * area_w
        sum_comb += combined * area_w
        sum_w += area_w

        sec_rR.append(s.r_over_R)
        sec_VA.append(V_A)
        sec_VR.append(s.Vrel)
        sec_sig.append(sc.sigma_local)
        sec_sheet.append(sc.sheet_severity)

    PD = 1.0
    for s in geom.sections:
        if abs(s.r_over_R - 0.7) < 0.1 and geom.diameter > 0:
            PD = s.pitch / geom.diameter
            break
    burrill_pct, sigma_07 = burrill_back_cavitation(
        max(T_blade, 0.0), cond.rho,
        V_inflow * (1.0 - cond.w) + float(np.interp(0.7, bem.r_over_R, bem.u_a)),
        omega, geom.diameter, geom.expanded_area_ratio, PD,
        cond.p_atm, cond.pv, cond.g, cond.h)

    return DuctBEMCavitation(
        bem=bem, section_rR=sec_rR, section_VA=sec_VA, section_VR=sec_VR,
        section_sigma=sec_sig, section_sheet=sec_sheet, T_blade=T_blade,
        sheet_pct=100.0 * sum_sheet / max(sum_w, 1e-9),
        tip_pct=100.0 * sum_tip / max(sum_w, 1e-9),
        combined_pct=100.0 * sum_comb / max(sum_w, 1e-9),
        burrill_back_pct=burrill_pct, sigma_0_7R=sigma_07, tvc=tvc,
        note=bem.note,
    )
