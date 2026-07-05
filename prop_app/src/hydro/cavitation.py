"""Bounded, physically-scaled cavitation model.

Why the old model produced nonsense
-----------------------------------
``src/cavitation.py`` computed the sheet-cavitation inception number as

    cpmin_loading = k * dCL**2 / max(t/c, 0.02)

which blows up at the thin tip sections (t/c -> 0.02), giving -Cp_min ~ 6 and
flagging almost the whole blade as cavitating. The tip-vortex term mixed
dimensions and produced an unbounded "index".

This module fixes both:

  * Local cavitation number with the standard reference (top dead centre, the
    worst case for a blade passing 12 o'clock):
        sigma = (p_atm + rho*g*(h - r) - pv) / (0.5 rho Vrel^2)
  * Sheet inception via a BOUNDED -Cp_min superposition: a thickness suction
    peak ((1+t/c)^2 - 1) plus a loading peak (k * CL^2). No division by t/c.
  * Tip-vortex inception in the proper McCormick (1962) form
        sigma_i = K * CL_tip^2 * (Re/Re_ref)^0.35
    blended over the tip region; the reported index is clamped for display.
  * An independent Burrill (1943) back-cavitation cross-check on the whole blade.

Every severity is a clamped fraction in [0, 1]; the reported percentages are
area-weighted averages, so they cannot exceed 100 % or run away.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import List


@dataclass
class CavitationConstants:
    # Sheet (-Cp_min) inception. sheet_loading_k = 2.5 makes the section
    # -Cp_min model agree in magnitude with the independent Burrill criterion.
    sheet_thickness_k: float = 1.0     # weight on the ((1+t/c)^2 - 1) thickness peak
    sheet_loading_k: float = 2.5       # weight on the CL^2 loading/incidence peak
    sheet_severity_scale: float = 1.0  # calibration multiplier on the output fraction
    # Tip-vortex (McCormick 1962). tip_K set so the inception index is O(1) at a
    # typical loaded tip with the normalised Reynolds term.
    tip_K: float = 3.0                 # proportionality constant
    tip_Re_ref: float = 2.0e6
    tip_Re_exp: float = 0.35
    tip_start_rR: float = 0.85
    tip_end_rR: float = 1.00
    tip_index_cap: float = 10.0        # clamp on the reported sigma_i/sigma index
    # Analytical tip-leakage-vortex model (used for DUCTED modes instead of an
    # empirical suppression multiplier). See tip_leakage_tvc().
    tvc_C_D: float = 0.7               # gap discharge coefficient (0.6-0.8)
    tvc_core_factor: float = 5.0       # vortex core radius a_c = core_factor * tip gap
    # Combined
    lambda_tip: float = 1.0            # weight of tip severity in the combined metric


@dataclass
class SectionCavitation:
    sigma_local: float
    sigma_crit_sheet: float
    sheet_severity: float
    sigma_i_tip: float
    tip_factor: float
    tip_severity: float
    tip_index: float
    combined_severity: float


@dataclass
class CavitationSummary:
    sheet_pct: float
    tip_pct: float
    combined_pct: float
    tip_index_max: float
    burrill_back_pct: float
    sigma_0_7R: float
    sections: List[SectionCavitation]


def _clamp01(x: float) -> float:
    return max(min(x, 1.0), 0.0)


def section_cavitation(p_minus_pv: float, q: float, CL: float, tc: float,
                       r_over_R: float, Re: float,
                       c: CavitationConstants) -> SectionCavitation:
    """Bounded sheet + tip-vortex indicators for a single blade section.

    ``p_minus_pv`` is (p_ref - p_vapour) [Pa] at the section, ``q`` is the
    section dynamic pressure 0.5*rho*Vrel^2 [Pa].
    """
    eps = 1e-6
    sigma = p_minus_pv / max(q, eps)

    # --- sheet cavitation: bounded -Cp_min superposition ---------------------
    cp_thickness = (1.0 + tc) ** 2 - 1.0                     # ~2*t/c, bounded
    cp_loading = CL * CL                                     # suction peak from loading
    sigma_crit_sheet = c.sheet_thickness_k * cp_thickness + c.sheet_loading_k * cp_loading
    if sigma_crit_sheet > eps:
        sheet_sev = (sigma_crit_sheet - sigma) / sigma_crit_sheet
    else:
        sheet_sev = 0.0
    sheet_severity = _clamp01(sheet_sev * c.sheet_severity_scale)

    # --- tip-vortex cavitation: McCormick (1962) -----------------------------
    Re_ratio = (max(Re, 1.0) / c.tip_Re_ref) ** c.tip_Re_exp
    sigma_i_tip = c.tip_K * (CL * CL) * Re_ratio
    span = max(c.tip_end_rR - c.tip_start_rR, 1e-3)
    tip_factor = _clamp01((r_over_R - c.tip_start_rR) / span)
    if sigma_i_tip > eps:
        tip_sev = (sigma_i_tip - sigma) / sigma_i_tip
    else:
        tip_sev = 0.0
    tip_severity = tip_factor * _clamp01(tip_sev)
    tip_index = min(sigma_i_tip / max(sigma, eps), c.tip_index_cap)

    combined = max(sheet_severity, c.lambda_tip * tip_severity)
    return SectionCavitation(
        sigma_local=sigma, sigma_crit_sheet=sigma_crit_sheet,
        sheet_severity=sheet_severity, sigma_i_tip=sigma_i_tip,
        tip_factor=tip_factor, tip_severity=tip_severity, tip_index=tip_index,
        combined_severity=combined,
    )


@dataclass
class TipLeakageTVC:
    dP_tip: float          # pressure-side/suction-side loading pressure diff [Pa]
    V_leak: float          # gap leakage velocity [m/s]
    Gamma_leak: float      # leakage-vortex circulation [m^2/s]
    core_radius: float     # Rankine core radius a_c [m]
    dP_core: float         # core pressure depression [Pa]
    P_core: float          # vortex core pressure [Pa]
    sigma_tvc: float       # analytical TVC inception number
    sigma_local: float     # local (ambient) cavitation number
    cavitates: bool        # P_core < p_vapour
    severity: float        # bounded extent [0,1]


def tip_leakage_tvc(rho: float, V_local: float, CL_tip: float, c_tip: float,
                    delta: float, P_local: float, pv: float,
                    C_D: float = 0.7, core_factor: float = 1.0,
                    delta_floor: float = 1.0e-4) -> TipLeakageTVC:
    """Analytical tip-leakage-vortex cavitation via a Rankine vortex core.

    Replaces the empirical tip-vortex suppression multiplier with explicit
    tip-leakage-flow physics. Exact steps (all analytical, no fudge factor):

      1. Tip loading pressure difference:  dP_tip = 0.5*rho*V_local^2*|CL_tip|
      2. Gap leakage velocity (Bernoulli): V_L    = C_D*sqrt(2*dP_tip/rho)
      3. Leakage-vortex circulation:       Gamma  = V_L * c_tip
      4. Rankine core pressure:            P_core = P_local - rho*Gamma^2/(4*pi^2*a_c^2)
      5. Inception number:                 sigma_tvc = (P_local - P_core)/(0.5*rho*V_local^2)

    Cavitation occurs when P_core < p_vapour  (equivalently sigma_local < sigma_tvc).

    ``C_D`` is the gap discharge coefficient (0.6-0.8, from gap geometry).
    ``core_factor`` sets the core radius a_c = core_factor * delta. The base
    assumption a_c = delta (core_factor = 1) tends to over-concentrate the
    vortex for sub-millimetre gaps (giving unphysical core pressures); the
    physical core is usually a few times the gap, so core_factor is exposed as a
    documented physical parameter rather than an arbitrary suppression term.
    """
    delta_eff = max(delta, delta_floor)
    a_c = core_factor * delta_eff
    q = 0.5 * rho * V_local ** 2

    dP_tip = 0.5 * rho * V_local ** 2 * abs(CL_tip)
    V_L = C_D * math.sqrt(2.0 * dP_tip / rho) if dP_tip > 0 else 0.0
    Gamma_L = V_L * c_tip
    dP_core = rho * Gamma_L ** 2 / (4.0 * math.pi ** 2 * a_c ** 2)
    P_core = P_local - dP_core

    sigma_tvc = dP_core / q if q > 1e-9 else 0.0
    sigma_local = (P_local - pv) / q if q > 1e-9 else 0.0
    cavitates = P_core < pv
    severity = (max(min((sigma_tvc - sigma_local) / sigma_tvc, 1.0), 0.0)
                if sigma_tvc > 1e-9 else 0.0)
    return TipLeakageTVC(dP_tip=dP_tip, V_leak=V_L, Gamma_leak=Gamma_L, core_radius=a_c,
                         dP_core=dP_core, P_core=P_core, sigma_tvc=sigma_tvc,
                         sigma_local=sigma_local, cavitates=cavitates, severity=severity)


def burrill_back_cavitation(T_total: float, rho: float, Va: float, omega: float,
                            D: float, EAR: float, PD: float, p_atm: float,
                            pv: float, g: float, h: float) -> tuple:
    """Burrill (1943) mean back-cavitation cross-check.

    Returns (back_cavitation_pct, sigma_0_7R). Uses the 0.7R relative velocity
    and Taylor's projected-area ratio. The percentage comes from a monotone fit
    to Burrill's back-cavitation lines (2.5 / 5 / 10 / 20 %), clamped to [0,100].
    """
    r07 = 0.35 * D                                   # 0.7 * R, R = D/2
    Vr = math.hypot(Va, omega * r07)
    q07 = 0.5 * rho * Vr ** 2
    if q07 <= 0:
        return 0.0, 0.0
    sigma_07 = (p_atm + rho * g * (h - r07) - pv) / q07

    # Projected blade area (Taylor): Ap = Ad * EAR * (1.067 - 0.229*P/D)
    Ad = math.pi * D ** 2 / 4.0
    Ap = Ad * EAR * max(1.067 - 0.229 * PD, 0.3)
    tau_c = T_total / (q07 * Ap) if Ap > 0 else 0.0

    # Burrill limit lines fit: tau_c allowable ~ k_pct * sigma_07^0.57.
    # k for 5% back cavitation ~ 0.30; lower k lines = more cavitation.
    base = sigma_07 ** 0.57 if sigma_07 > 0 else 1e-3
    k_eff = tau_c / base if base > 0 else 0.0
    # Map k_eff to a back-cavitation percentage (monotone, clamped):
    #   k_eff <= 0.20 -> ~0%, 0.30 -> ~5%, 0.40 -> ~10%, >=0.60 -> ~30%+.
    back_pct = max(0.0, (k_eff - 0.20) / 0.013)
    back_pct = min(back_pct, 100.0)
    return back_pct, sigma_07
