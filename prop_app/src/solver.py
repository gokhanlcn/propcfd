import math
from .models import PropellerGeometry, OperatingConditions, ModelConstants, SectionResult, PerformanceResult, NozzleSelection
from .cavitation import calculate_section_cavitation
from .nozzle_performance import get_nozzle_aerodynamics

def compute_shaft_power(rpm: float, torque_total_Nm: float) -> float:
    """Returns shaft power in watts."""
    n = rpm / 60.0
    omega = 2.0 * math.pi * n
    return omega * torque_total_Nm

def compute_static_efficiency(thrust_N: float, rho: float, diameter_m: float, shaft_power_W: float) -> float | None:
    """Computes approximate static efficiency based on actuator disk momentum theory."""
    if thrust_N <= 0 or shaft_power_W <= 0 or rho <= 0 or diameter_m <= 0:
        return None
    A = math.pi * (diameter_m**2) / 4.0
    v_i = math.sqrt(thrust_N / (2.0 * rho * A))
    p_ideal = thrust_N * v_i
    return p_ideal / shaft_power_W

def compute_static_metrics(thrust_N: float, torque_total_Nm: float, rpm: float, rho: float, diameter_m: float) -> dict:
    """
    Returns dict with:
    - shaft_power_W
    - static_efficiency
    - thrust_per_power_N_per_W
    - warnings
    """
    warnings = []
    shaft_power_W = compute_shaft_power(rpm, torque_total_Nm)
    
    A_disk_full = math.pi * (diameter_m ** 2) / 4.0
    static_eff = compute_static_efficiency(thrust_N, rho, diameter_m, shaft_power_W)
    
    if thrust_N > 0 and rho > 0 and A_disk_full > 0:
        P_ideal_min = (thrust_N ** 1.5) / math.sqrt(2 * rho * A_disk_full)
        if shaft_power_W > 0:
            if shaft_power_W < P_ideal_min:
                warnings.append(f"Sanity Check: Computed power ({shaft_power_W:.1f} W) is BELOW ideal actuator power ({P_ideal_min:.1f} W). Unphysical model state.")
            
            fom = P_ideal_min / shaft_power_W
            if fom > 1.0:
                warnings.append(f"Sanity Check: Figure of Merit bounds exceeded ({fom:.2f} > 1.0).")
                
    thrust_per_power = (thrust_N / shaft_power_W) if shaft_power_W > 0 else None
    
    if thrust_per_power is not None and thrust_per_power > 0.4:
        warnings.append(f"Sanity Check: Abnormally high thrust-to-power ratio ({thrust_per_power:.2f} N/W). Typical upper bound is < 0.4 N/W.")
    
    return {
        "shaft_power_W": shaft_power_W,
        "static_efficiency": static_eff,
        "thrust_per_power_N_per_W": thrust_per_power,
        "warnings": warnings
    }


def solve_performance(geom: PropellerGeometry, cond: OperatingConditions, 
                      constants: ModelConstants, nozzle_selection: NozzleSelection) -> PerformanceResult:
    warnings = []
    n = cond.rpm / 60.0
    omega = 2.0 * math.pi * n
    Va = cond.Va_ship * (1 - cond.w)
    
    D, R, Rh, B = geom.diameter, geom.radius, geom.hub_radius, geom.blade_count
    J = tuple([Va / (n * D)])[0] if n != 0 and D != 0 else 0.0
    
    # Extract decoupled nozzle performance geometric multipliers
    noz_aero = get_nozzle_aerodynamics(nozzle_selection, J, D, constants)
    active_nozzle = noz_aero.is_active
    u_nozzle_func = noz_aero.u_nozzle_func
    
    p_static_base = cond.p_atm + cond.rho * cond.g * cond.h
    p_local_static = p_static_base * noz_aero.pressure_recovery
    
    A_disk_effective = math.pi * (R**2 - Rh**2)
    if A_disk_effective <= 0:
        warnings.append("Effective disk area <= 0. Check R and Hub Radius.")
        A_disk_effective = 1e-6
        
    def run_bemt_loop(is_nozzle_active: bool, mass_flux_multiplier: float, u_noz_func):
        local_vi = 0.0
        max_iter = 15
        final_results = []
        for iteration in range(max_iter):
            T_iter, Q_iter = 0.0, 0.0
            temp_results = []
            Vax_base_iter = Va + local_vi
            
            for sec in geom.sections:
                if sec.r <= Rh + 1e-5: continue
                    
                Vtan = omega * sec.r
                u_n = u_noz_func(sec.r_over_R, Vax_base_iter) if is_nozzle_active else 0.0
                Vax_local = Vax_base_iter + u_n
                
                # Mass flux consistency mapping limits FoM
                mass_flux_ratio = mass_flux_multiplier * (Vax_local / max(Vax_base_iter, 1e-6) if Vax_base_iter > 0 else 1.0)
                
                Vrel = math.sqrt(Vax_local**2 + Vtan**2)
                if Vrel == 0.0: continue
                    
                phi_inflow = math.atan2(Vax_local, Vtan)
                beta_i = phi_inflow
                beta_geom = math.atan2(sec.pitch, 2 * math.pi * sec.r) if sec.r > 0 else 0.0
                alpha = beta_geom - beta_i
                
                tc_ratio = sec.thickness / sec.chord if sec.chord > 0 else 0.0
                camber_ratio = sec.camber / sec.chord if sec.chord > 0 else 0.0
                
                alpha_eff = alpha - (-1.2 * camber_ratio)
                
                CL_raw = constants.cl_slope_factor * alpha_eff
                CL_max = constants.cl_max_base + constants.cl_max_camber_multiplier * min(camber_ratio, 0.08)
                
                if CL_max > 0.001:
                    CL = CL_max * math.tanh(CL_raw / CL_max)
                else:
                    CL = 0.0
                
                CD0 = constants.cd0_base + constants.thickness_drag_multiplier * tc_ratio + constants.camber_drag_multiplier * abs(camber_ratio)
                Re = (Vrel * sec.chord / cond.nu) if cond.nu > 0 else 1e6
                Re_factor = (constants.reynolds_reference / max(Re, 5e4)) ** constants.reynolds_drag_exponent
                CD0_corr = CD0 * max(min(Re_factor, 1.25), 0.8)
                CD = CD0_corr + constants.k_induced * CL**2
                
                sin_phi = max(math.sin(beta_i), 1e-4) if beta_i > 0 else 1e-4
                
                f_tip = (B / 2.0) * (R - sec.r) / (sec.r * sin_phi)
                F_tip_raw = (2.0 / math.pi) * math.acos(math.exp(-f_tip)) if f_tip > 0 else 1.0
                F_tip = min(F_tip_raw + (1.0 - F_tip_raw) * (1.0 - noz_aero.tip_gap_relief_factor), 1.0) if is_nozzle_active else F_tip_raw
                
                f_hub = (B / 2.0) * (sec.r - Rh) / (sec.r * sin_phi)
                F_hub = (2.0 / math.pi) * math.acos(math.exp(-f_hub)) if f_hub > 0 else 1.0
                F = max(min(F_tip, 1.0), 0.05) * max(min(F_hub, 1.0), 0.05)
                
                q = 0.5 * cond.rho * Vrel**2
                dL = q * sec.chord * CL * sec.dr * mass_flux_ratio
                dD = q * sec.chord * CD * sec.dr * mass_flux_ratio
                
                dT = B * (dL * math.cos(beta_i) - dD * math.sin(beta_i)) * F
                dFt = B * (dL * math.sin(beta_i) + dD * math.cos(beta_i)) * F
                dQ = dFt * sec.r
                
                T_iter += dT
                Q_iter += dQ
                
                sec_gamma = 0.5 * Vrel * sec.chord * CL
                q_dyn = q
                
                temp_results.append(SectionResult(
                    sec.r_over_R, sec.r, sec.chord, sec.thickness, sec.pitch, sec.camber,
                    beta_geom, beta_i, alpha, alpha_eff, CL, CD, 
                    sec_gamma, dT, dQ, Re, q_dyn, 0.0, 0.0, 0.0,
                    0.0, 0.0, 0.0, 0.0, 0.0,
                    u_n
                ))
                
            if T_iter <= 0:
                vi_new = 0.0
                if iteration == 0 and len(geom.sections) > 0 and not is_nozzle_active:
                    warnings.append("Initial thrust is negative or zero (windmilling). Induced velocity set to 0.")
            else:
                term = (Va/2.0)**2 + T_iter / (2.0 * cond.rho * A_disk_effective)
                vi_new = max(0.0, -Va/2.0 + math.sqrt(term))
                
            diff = abs(vi_new - local_vi)
            local_vi = 0.6 * local_vi + 0.4 * vi_new
            
            final_results = temp_results
            if diff < 1e-4 or iteration == max_iter - 1:
                break
                
        return T_iter, Q_iter, final_results, local_vi

    # 1. OPEN PROP ÇÖZÜMÜ
    T_open, Q_open, open_results, vi_open = run_bemt_loop(False, 1.0, lambda r, v: 0.0)
    rho_n2_D4, rho_n2_D5 = cond.rho * n**2 * D**4, cond.rho * n**2 * D**5
    KT_open = T_open / rho_n2_D4 if rho_n2_D4 > 0 else 0.0
    KQ_open = Q_open / rho_n2_D5 if rho_n2_D5 > 0 else 0.0
    Pshaft_open = 2 * math.pi * n * Q_open
    eta_open = (T_open * Va) / Pshaft_open if Pshaft_open > 0 else 0.0
    
    # 2. NOZZLE SURROGATE & TORQUE CONSISTENCY
    if active_nozzle and KT_open > 0:
        camber_scale = min(noz_aero.camber_ratio / 0.15, 1.2)
        ld_scale = min(noz_aero.l_over_d / 0.5, 1.2)
        tau_base = 0.5 * (1.0 + camber_scale) * ld_scale * nozzle_selection.effectiveness
        
        # Continuous Regime Curves (Literature-informed Surrogate)
        if noz_aero.nozzle_id == "19A":
            # 19A: high bollard pull, sharp drop-off
            tau_ideal = tau_base * 0.95 * max(1.0 - (J / 0.8)**2, -0.2)
            c_flux = 0.30 * max(1.0 - (J / 0.5)**1.5, 0.0)
        elif noz_aero.nozzle_id == "37":
            # 37: balanced bollard pull, wider efficiency band
            tau_ideal = tau_base * 0.65 * max(1.0 - (J / 1.1)**2, -0.05)
            c_flux = 0.15 * max(1.0 - (J / 0.6)**1.5, 0.0)
        else:
            tau_ideal = tau_base * 0.70 * max(1.0 - (J / 0.9)**2, -0.1)
            c_flux = 0.20 * max(1.0 - (J / 0.5)**1.5, 0.0)
            
        gap_factor = max(1.0 - (noz_aero.clearance_ratio * 25.0), 0.5)
        tau_duct = tau_ideal * noz_aero.tip_gap_relief_factor * gap_factor
        
        # Ensure torque draws according to the mass flow required to pump KTN
        mass_flux_factor = 1.0 + c_flux
        
        # Calculate Propeller Thrust operating INSIDE the nozzle (Mass flux scaled)
        T_prop_with_nozzle_flow, Q_prop_with_nozzle_flow, noz_results, vi_noz = run_bemt_loop(True, mass_flux_factor, u_nozzle_func)
        KT_prop_with_nozzle_flow = T_prop_with_nozzle_flow / rho_n2_D4 if rho_n2_D4 > 0 else 0.0
        KQ_prop_with_nozzle_flow = Q_prop_with_nozzle_flow / rho_n2_D5 if rho_n2_D5 > 0 else 0.0
        
        # KTN is anchored physically to the thrust the prop relies upon to pull the system
        KTN_raw = KT_prop_with_nozzle_flow * tau_duct
        KTN = max(KTN_raw, -0.15 * KT_open)  # allow max 15% drag
        
        KT_total = KTN + KT_prop_with_nozzle_flow
        T_total = KT_total * rho_n2_D4
        Q_total = Q_prop_with_nozzle_flow
        
        # 4. FOM GUARDRAIL (Self-Limiting)
        if J < 0.1 and T_total > 0 and Q_total > 0:
            P_shaft = compute_shaft_power(cond.rpm, Q_total)
            A_disk_full = math.pi * (D ** 2) / 4.0
            P_ideal_min = (T_total ** 1.5) / math.sqrt(2 * cond.rho * A_disk_full)
            fom = P_ideal_min / P_shaft
            
            # Strict FoM limits for ducted applications
            if fom > 0.98:
                warnings.append(f"FoM Guardrail active. Self-limiting KTN to enforce FOM <= 0.98 (was {fom:.3f}).")
                max_T_total = (0.98 * P_shaft * math.sqrt(2 * cond.rho * A_disk_full)) ** (2.0/3.0)
                if max_T_total < T_prop_with_nozzle_flow:
                    KTN = 0.0
                else:
                    KTN = (max_T_total - T_prop_with_nozzle_flow) / rho_n2_D4
                KT_total = KT_prop_with_nozzle_flow + KTN
                T_total = KT_total * rho_n2_D4
                
        active_results = noz_results
        final_vi = vi_noz
    else:
        KTN = 0.0
        KT_prop_with_nozzle_flow = KT_open
        KQ_prop_with_nozzle_flow = KQ_open
        T_prop_with_nozzle_flow = T_open
        Q_prop_with_nozzle_flow = Q_open
        
        KT_total = KT_open
        T_total = T_open
        Q_total = Q_open
        active_results = open_results
        final_vi = vi_open
        
    KQ_total = Q_total / rho_n2_D5 if rho_n2_D5 > 0 else 0.0
    Pshaft_total = compute_shaft_power(cond.rpm, Q_total)
    T_nozzle = KTN * rho_n2_D4
    nozzle_share = (KTN / KT_total * 100.0) if KT_total > 1e-9 else 0.0
    eta_total = (T_total * Va) / Pshaft_total if (Pshaft_total > 0 and Va > 0) else 0.0
    
    # Internal Identity Assertion
    assert abs(KT_total - (KT_prop_with_nozzle_flow + KTN)) < 1e-6, "Arithmetic identity KT_total == KT_prop_with_nozzle + KTN compromised."
    assert abs(T_total - (T_prop_with_nozzle_flow + T_nozzle)) < 1e-4, "Arithmetic identity T_total == T_prop_with_nozzle + T_nozzle compromised."
    
    # 5. KAVİTASYON MODELİ (PHYSICALLY COUPLED, NO ARBITRARY SUPPRESSION)
    gammas = [res.Gamma for res in active_results]
    rs = [res.r for res in active_results]
    N = len(gammas)
    dGamma_dr_list = [0.0] * N
    
    for i in range(N):
        if N > 1:
            if i == 0:
                dGamma_dr_list[i] = (gammas[i+1] - gammas[i]) / max(rs[i+1] - rs[i], 1e-6)
            elif i == N - 1:
                dGamma_dr_list[i] = (gammas[i] - gammas[i-1]) / max(rs[i] - rs[i-1], 1e-6)
            else:
                dGamma_dr_list[i] = (gammas[i+1] - gammas[i-1]) / max(rs[i+1] - rs[i-1], 1e-6)
    
    sum_sheet_weighted = 0.0
    sum_tip_weighted = 0.0
    sum_combined_weighted = 0.0
    sum_weight = 0.0
    temp_tip_index_max = 0.0
    
    for i, res in enumerate(active_results):
        sec = geom.sections[i]
        u_n = u_nozzle_func(sec.r_over_R, Va + final_vi) if active_nozzle else 0.0
        Vrel = math.sqrt((Va + final_vi + u_n)**2 + (omega * sec.r)**2)
        
        (sigma_local, sigma_crit_sheet, sheet_severity, 
         sigma_crit_tip, tip_factor, tip_severity, 
         tip_vortex_index_i, combined_severity_i) = calculate_section_cavitation(
            p_inf=p_static_base,
            p_inf_noz=p_local_static,
            pv=cond.pv,
            q=res.q_dyn,
            CL=res.CL,
            alpha=res.alpha,
            Gamma=res.Gamma,
            dGamma_dr=dGamma_dr_list[i],
            Vrel=Vrel,
            c=sec.chord,
            t=sec.thickness,
            r_over_R=sec.r_over_R,
            active_nozzle=bool(active_nozzle),
            constants=constants
        )
        
        area_weight = sec.chord * sec.dr
        
        res.sigma_local = sigma_local
        res.sigma_crit_sheet = sigma_crit_sheet
        res.sheet_severity = sheet_severity
        res.sigma_crit_tip = sigma_crit_tip
        res.tip_region = tip_factor
        res.tip_severity = tip_severity
        res.tip_vortex_index_i = tip_vortex_index_i
        res.combined_severity = combined_severity_i
        
        sum_sheet_weighted += sheet_severity * area_weight
        sum_tip_weighted += tip_severity * area_weight
        sum_combined_weighted += combined_severity_i * area_weight
        sum_weight += area_weight
        temp_tip_index_max = max(temp_tip_index_max, tip_vortex_index_i)
    
    section_results = active_results
    
    Sheet_Cavitation_Est_PCT = 100.0 * sum_sheet_weighted / max(sum_weight, 1e-9)
    Tip_Vortex_Cavitation_Est_PCT = 100.0 * sum_tip_weighted / max(sum_weight, 1e-9)
    Combined_Cavitation_Est_PCT = 100.0 * sum_combined_weighted / max(sum_weight, 1e-9)
    Tip_Vortex_Cav_Index = temp_tip_index_max
    
    static_metrics = compute_static_metrics(T_total, Q_total, cond.rpm, cond.rho, D)
    warnings.extend(static_metrics["warnings"])
    
    return PerformanceResult(
        prop_geom=geom,
        conditions=cond,
        J=J,
        KT_open_reference=KT_open,
        KQ_open_reference=KQ_open,
        T_open_reference=T_open,
        Q_open_reference=Q_open,
        Pshaft_open_reference=Pshaft_open,
        eta_open_reference=eta_open,
        KT_prop_with_nozzle_flow=KT_prop_with_nozzle_flow,
        KQ_prop_with_nozzle_flow=KQ_prop_with_nozzle_flow,
        T_prop_with_nozzle_flow=T_prop_with_nozzle_flow,
        Q_prop_with_nozzle_flow=Q_prop_with_nozzle_flow,
        KTN=KTN,
        T_nozzle=T_nozzle,
        nozzle_share=nozzle_share,
        KT_total=KT_total,
        KQ_total=KQ_total,
        T_total=T_total,
        Q_total=Q_total,
        Pshaft_total=Pshaft_total,
        eta_total=eta_total,
        static_efficiency_est=static_metrics["static_efficiency"],
        thrust_per_power_N_per_W=static_metrics["thrust_per_power_N_per_W"],
        Sheet_Cavitation_Est_PCT=Sheet_Cavitation_Est_PCT,
        Tip_Vortex_Cavitation_Est_PCT=Tip_Vortex_Cavitation_Est_PCT,
        Combined_Cavitation_Est_PCT=Combined_Cavitation_Est_PCT,
        Tip_Vortex_Cav_Index=Tip_Vortex_Cav_Index,
        section_results=section_results,
        warnings=warnings
    )
