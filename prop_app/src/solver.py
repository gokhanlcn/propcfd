"""Performance orchestrator.

Thin router that wires the physics package (``src.hydro``) together and packs
the result into the :class:`PerformanceResult` the UI/exporters already expect.

Pipeline per analysis:
  1. Bare-propeller BEMT (loading gauge + always-available open-water numbers).
  2. Open-water reference: validated Wageningen B polynomial when the propeller
     is a recognised series, used to calibrate the BEMT *level* (the
     distribution shape still comes from the BEMT). Generic geometry runs on the
     calibrated-slope BEMT alone.
  3. Ducted modes (19A / 37): consistent actuator-disk-in-duct momentum model
     (no double counting). Open mode skips this.
  4. Bounded cavitation (sheet + tip-vortex) per section + Burrill cross-check.

Backwards compatibility: ``solve_performance(geom, cond, constants, nozzle_sel)``
keeps its old signature. ``constants`` (legacy ``ModelConstants``) is accepted
but the physics now lives in the hydro dataclasses; an optional ``hydro_config``
may be supplied to override them.
"""
from __future__ import annotations
import math
from typing import Optional

from .models import (PropellerGeometry, OperatingConditions, ModelConstants,
                     NozzleSelection, SectionResult, PerformanceResult)
from .hydro.openwater import OpenWaterConstants, solve_bemt
from .hydro.ducted import get_duct, solve_ducted
from .hydro.cavitation import (CavitationConstants, section_cavitation,
                               burrill_back_cavitation, tip_leakage_tvc)
from .hydro import reference as ref


def _coeffs(rho: float, n: float, D: float):
    return rho * n ** 2 * D ** 4, rho * n ** 2 * D ** 5


def _static_metrics(T: float, rho: float, D: float, Pshaft: float):
    """Actuator-disk static efficiency + thrust/power, with sanity warnings."""
    warnings = []
    A = math.pi * D ** 2 / 4.0
    static_eff = None
    if T > 0 and Pshaft > 0 and rho > 0 and A > 0:
        vi = math.sqrt(T / (2.0 * rho * A))
        static_eff = (T * vi) / Pshaft
        P_ideal = (T ** 1.5) / math.sqrt(2.0 * rho * A)
        if static_eff > 1.0:
            warnings.append(f"Static figure of merit > 1 ({static_eff:.2f}); check inputs.")
        if Pshaft < P_ideal:
            warnings.append("Shaft power below ideal actuator power (unphysical).")
    tpp = (T / Pshaft) if Pshaft > 0 else None
    if tpp is not None and tpp > 0.4:
        warnings.append(f"Very high thrust/power ratio ({tpp:.2f} N/W).")
    return static_eff, tpp, warnings


def solve_performance(geom: PropellerGeometry,
                      cond: OperatingConditions,
                      constants: Optional[ModelConstants] = None,
                      nozzle_selection: Optional[NozzleSelection] = None,
                      hydro_config: Optional[OpenWaterConstants] = None,
                      cav_config: Optional[CavitationConstants] = None,
                      series_hint: str = "",
                      direction: str = "ahead") -> PerformanceResult:
    nozzle_selection = nozzle_selection or NozzleSelection()
    ow = hydro_config or OpenWaterConstants()
    cav = cav_config or CavitationConstants()
    mode = cond.nozzle_mode
    warnings: list = []

    # Astern (reverse-rotation) blade effectiveness. A fixed-pitch blade running
    # in reverse is a poor aerofoil (rounded trailing edge leads); the penalty
    # grows with camber, since cambered sections are strongly directional. These
    # multipliers reduce the blade thrust/torque and section loading for astern;
    # the 19A/37 astern difference itself comes from the duct astern constants.
    astern = (direction == "astern")
    if astern and geom.sections:
        mean_fc = sum(abs(s.camber) / s.chord for s in geom.sections if s.chord > 0) \
            / max(sum(1 for s in geom.sections if s.chord > 0), 1)
        kT_astern = min(max(0.88 - 2.5 * mean_fc, 0.50), 0.90)
        kQ_astern = min(max(0.95 - 1.5 * mean_fc, 0.70), 0.95)
    else:
        kT_astern = kQ_astern = 1.0

    n = cond.rpm / 60.0
    D, R, Rh = geom.diameter, geom.radius, geom.hub_radius
    Va = cond.Va_ship * (1.0 - cond.w)
    J = (Va / (n * D)) if (n != 0 and D != 0) else 0.0
    rho_n2D4, rho_n2D5 = _coeffs(cond.rho, n, D)

    # 1. Bare-propeller BEMT (always) ----------------------------------------
    open_res = solve_bemt(geom, cond, ow)
    KT_bemt = open_res.T / rho_n2D4 if rho_n2D4 > 0 else 0.0
    KQ_bemt = open_res.Q / rho_n2D5 if rho_n2D5 > 0 else 0.0

    # 2. Open-water reference + BEMT level calibration -----------------------
    series = ref.detect_series(geom, series_hint)
    reference = ref.open_water_reference(geom, J, series)
    fT, fQ = ref.calibration_factors(reference, KT_bemt, KQ_bemt)

    T_open = fT * open_res.T * kT_astern
    Q_open = fQ * open_res.Q * kQ_astern
    KT_open = T_open / rho_n2D4 if rho_n2D4 > 0 else 0.0
    KQ_open = Q_open / rho_n2D5 if rho_n2D5 > 0 else 0.0
    Pshaft_open = 2.0 * math.pi * n * Q_open
    eta_open = (T_open * Va) / Pshaft_open if (Pshaft_open > 0 and Va > 0) else 0.0

    # 3. Branch: open vs ducted ----------------------------------------------
    duct = get_duct(mode) if mode in ("19A", "37") else None
    T_duct = 0.0
    duct_share = 0.0
    A_duct = 1.0
    duct_u = 0.0
    method = "BEMT (Wageningen-B calibrated)" if reference.KT is not None else "BEMT"

    if duct is not None:
        dres = solve_ducted(geom, cond, ow, duct, effectiveness=nozzle_selection.effectiveness,
                            direction=direction)
        warnings.extend(dres.warnings)
        # Apply the open-water level calibration + astern blade factor to the
        # duct's bare-prop base.
        T_total = fT * dres.T_total * kT_astern
        Q_total = fQ * dres.Q * kQ_astern
        T_duct = fT * dres.Td * kT_astern
        duct_share = dres.tau
        A_duct = dres.A_duct
        duct_u = dres.u_duct
        dist_sections = dres.dist_bemt.sections
        dist_thrust = sum(s.dT for s in dist_sections)
        method = f"Ducted momentum ({duct.display_name})"
    else:
        T_total = T_open
        Q_total = Q_open
        dist_sections = open_res.sections
        dist_thrust = open_res.T

    if astern:
        method += " [ASTERN]"

    KT_total = T_total / rho_n2D4 if rho_n2D4 > 0 else 0.0
    KQ_total = Q_total / rho_n2D5 if rho_n2D5 > 0 else 0.0
    Pshaft_total = 2.0 * math.pi * n * Q_total
    eta_total = (T_total * Va) / Pshaft_total if (Pshaft_total > 0 and Va > 0) else 0.0

    # Scale the distribution so summed dT matches the headline blade thrust.
    blade_thrust = T_total - T_duct
    dist_scale = (blade_thrust / dist_thrust) if abs(dist_thrust) > 1e-9 else 1.0

    # 4. Cavitation + assemble section results -------------------------------
    # Tip vortex: an open propeller sheds a free tip vortex (McCormick, in
    # section_cavitation). A ducted propeller instead has a tip-LEAKAGE vortex
    # forced through the physical gap -- modelled analytically (Rankine core,
    # tip_leakage_tvc), with no empirical suppression multiplier.
    section_results = []
    sum_sheet = sum_tip = sum_comb = sum_w = 0.0
    tip_index_max = 0.0
    PD = ref.representative_PD(geom)

    # Local static-pressure drop from the duct accelerating the inflow (Bernoulli
    # from far field to the disk): p_disk = p_far - 0.5*rho*((Va+u_duct)^2 - Va^2).
    # An accelerating duct therefore LOWERS the reference pressure and raises the
    # cavitation risk -- and the stronger accelerator (19A) drops it more. Open
    # mode has u_duct = 0, so no change.
    p_bernoulli_drop = (0.5 * cond.rho * ((Va + duct_u) ** 2 - Va ** 2)
                        if duct is not None else 0.0)

    # Ducted: analytical tip-leakage-vortex severity, evaluated once at the tip
    # section from the physical tip clearance (replaces the old 0.15 multiplier).
    tvc_severity = 0.0
    tvc_sigma = 0.0
    if duct is not None and dist_sections:
        delta = (nozzle_selection.tip_clearance_m_override
                 if nozzle_selection.tip_clearance_m_override is not None else 0.01 * D)
        tip_s = max(dist_sections, key=lambda x: x.r_over_R)
        P_local_tip = cond.p_atm + cond.rho * cond.g * (cond.h - tip_s.r) - p_bernoulli_drop
        tvc = tip_leakage_tvc(cond.rho, tip_s.Vrel, tip_s.CL * kT_astern, tip_s.chord,
                              delta, P_local_tip, cond.pv,
                              C_D=cav.tvc_C_D, core_factor=cav.tvc_core_factor)
        tvc_severity = tvc.severity
        tvc_sigma = tvc.sigma_tvc

    for s in dist_sections:
        dT = s.dT * dist_scale
        dQ = s.dQ * dist_scale
        tc = s.thickness / s.chord if s.chord > 0 else 0.0
        # Reference pressure at top dead centre (worst case), incl. duct suction.
        p_ref = cond.p_atm + cond.rho * cond.g * (cond.h - s.r) - p_bernoulli_drop
        p_minus_pv = p_ref - cond.pv
        q = max(s.q_dyn, 1e-6)
        CL_eff = s.CL * kT_astern     # astern: reduced blade loading
        sc = section_cavitation(p_minus_pv, q, CL_eff, tc, s.r_over_R, s.Re, cav)

        if duct is not None:
            tip_sev = sc.tip_factor * tvc_severity     # analytical tip-leakage vortex
            tip_idx = tvc_sigma
        else:
            tip_sev = sc.tip_severity                  # free-vortex McCormick
            tip_idx = sc.tip_index
        combined = max(sc.sheet_severity, cav.lambda_tip * tip_sev)
        area_w = s.chord * s.dr
        sum_sheet += sc.sheet_severity * area_w
        sum_tip += tip_sev * area_w
        sum_comb += combined * area_w
        sum_w += area_w
        tip_index_max = max(tip_index_max, tip_idx)

        section_results.append(SectionResult(
            r_over_R=s.r_over_R, r=s.r, chord=s.chord, thickness=s.thickness,
            pitch=s.pitch, camber=s.camber, beta_geom=s.beta_geom, beta_i=s.beta_i,
            alpha=s.alpha, alpha_eff=s.alpha_eff, CL=s.CL, CD=s.CD, Gamma=s.Gamma,
            dT=dT, dQ=dQ, Re=s.Re, q_dyn=s.q_dyn,
            sigma_local=sc.sigma_local, sigma_crit_sheet=sc.sigma_crit_sheet,
            sheet_severity=sc.sheet_severity, sigma_crit_tip=sc.sigma_i_tip,
            tip_region=sc.tip_factor, tip_severity=tip_sev,
            tip_vortex_index_i=tip_idx, combined_severity=combined,
            nozzle_u_local=0.0,
        ))

    sheet_pct = 100.0 * sum_sheet / max(sum_w, 1e-9)
    tip_pct = 100.0 * sum_tip / max(sum_w, 1e-9)
    comb_pct = 100.0 * sum_comb / max(sum_w, 1e-9)
    # Burrill is a blade-surface criterion: it uses the blade thrust (the duct's
    # own thrust is not carried by the blades) and the duct-augmented 0.7R
    # inflow, so a ducted propeller reads a lower back-cavitation number.
    burrill_pct, sigma_07 = burrill_back_cavitation(
        blade_thrust, cond.rho, Va + duct_u, 2.0 * math.pi * n, D,
        geom.expanded_area_ratio, PD, cond.p_atm, cond.pv, cond.g, cond.h)

    # 5. Static metrics + warnings -------------------------------------------
    static_eff, tpp, sw = _static_metrics(T_total, cond.rho, D, Pshaft_total)
    warnings.extend(sw)
    warnings.extend(open_res.warnings)

    return PerformanceResult(
        prop_geom=geom, conditions=cond, J=J,
        KT_total=KT_total, KQ_total=KQ_total, T_total=T_total, Q_total=Q_total,
        Pshaft_total=Pshaft_total, eta_total=eta_total,
        section_results=section_results, warnings=warnings,
        static_efficiency_est=static_eff, thrust_per_power_N_per_W=tpp,
        Sheet_Cavitation_Est_PCT=sheet_pct, Tip_Vortex_Cavitation_Est_PCT=tip_pct,
        Combined_Cavitation_Est_PCT=comb_pct, Tip_Vortex_Cav_Index=tip_index_max,
        Burrill_Back_Cavitation_PCT=burrill_pct, sigma_0_7R=sigma_07,
        KT_open=KT_open, KQ_open=KQ_open, T_open=T_open, Q_open=Q_open, eta_open=eta_open,
        T_duct=T_duct, duct_thrust_share=duct_share, duct_augmentation=A_duct,
        method=method, reference_series=series,
        KT_reference_poly=reference.KT, KQ_reference_poly=reference.KQ,
        reference_note=reference.note,
    )


def solve_bidirectional(geom: PropellerGeometry,
                        cond: OperatingConditions,
                        constants: Optional[ModelConstants] = None,
                        nozzle_selection: Optional[NozzleSelection] = None,
                        hydro_config: Optional[OpenWaterConstants] = None,
                        cav_config: Optional[CavitationConstants] = None,
                        series_hint: str = ""):
    """Ahead + astern + mean, for reversing (bidirectional) thrusters.

    Returns (ahead, astern, average) where ahead/astern are PerformanceResult and
    average is a dict of the key scalar metrics. Astern uses the reduced-blade /
    astern-duct engineering model in ``solve_performance(direction='astern')``.
    """
    kw = dict(constants=constants, nozzle_selection=nozzle_selection,
              hydro_config=hydro_config, cav_config=cav_config, series_hint=series_hint)
    ahead = solve_performance(geom, cond, direction="ahead", **kw)
    astern = solve_performance(geom, cond, direction="astern", **kw)

    def mean(a, b):
        if a is None or b is None:
            return None
        return 0.5 * (a + b)

    average = {
        "T_total": mean(ahead.T_total, astern.T_total),
        "Q_total": mean(ahead.Q_total, astern.Q_total),
        "Pshaft_total": mean(ahead.Pshaft_total, astern.Pshaft_total),
        "eta_total": mean(ahead.eta_total, astern.eta_total),
        "KT_total": mean(ahead.KT_total, astern.KT_total),
        "Sheet_Cavitation_Est_PCT": mean(ahead.Sheet_Cavitation_Est_PCT, astern.Sheet_Cavitation_Est_PCT),
        "Combined_Cavitation_Est_PCT": mean(ahead.Combined_Cavitation_Est_PCT, astern.Combined_Cavitation_Est_PCT),
        "Burrill_Back_Cavitation_PCT": mean(ahead.Burrill_Back_Cavitation_PCT, astern.Burrill_Back_Cavitation_PCT),
    }
    return ahead, astern, average
