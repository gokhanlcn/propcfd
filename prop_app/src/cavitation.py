import math
from .models import ModelConstants

def calculate_section_cavitation(
    p_ref: float,
    pv: float,
    q: float,
    CL: float,
    alpha: float,
    Gamma: float,
    dGamma_dr: float,
    Vrel: float,
    c: float,
    t: float,
    r_over_R: float,
    nu: float,
    constants: ModelConstants
) -> tuple[float, float, float, float, float, float, float, float]:

    sigma_local = (p_ref - pv) / max(q, 1e-6)
    
    eps = 1e-6
    tc_ratio = t / max(c, eps)
    
    # ----------------------------------------------------
    # SHEET CAVITATION (Brockett -Cp_min based inception)
    # ----------------------------------------------------
    # Baseline: suction peak from thickness alone
    cpmin_thickness = constants.sheet_cpmin_thickness_k * (tc_ratio + 0.5 * tc_ratio**2)
    # Loading contribution: suction peak grows with |CL - CL_ideal|
    delta_CL = CL - constants.sheet_cpmin_ideal_cl
    cpmin_loading = constants.sheet_cpmin_loading_k * delta_CL**2 / max(tc_ratio, 0.02)
    # Critical sigma for sheet inception = -Cp_min
    sigma_crit_sheet = cpmin_thickness + cpmin_loading

    # Inception when sigma_local < sigma_crit_sheet
    sheet_margin = (sigma_crit_sheet - sigma_local) / max(sigma_crit_sheet, eps)
    sheet_severity = max(min(sheet_margin * constants.sheet_severity_scale, 1.0), 0.0)
    
    # ----------------------------------------------------
    # TIP VORTEX CAVITATION (McCormick 1962)
    # sigma_tv = K * (Gamma / (Vrel * r_core))^m * (Re / Re_ref)^n
    # ----------------------------------------------------
    r_core = constants.tip_core_radius_coeff * c
    if r_core > eps and Vrel > eps:
        circulation_ratio = abs(Gamma) / (Vrel * r_core)
        Re_section = Vrel * c / max(nu, 1e-8)
        Re_ratio = (Re_section / constants.tip_mccormick_Re_ref) ** constants.tip_mccormick_n
        sigma_crit_tip = constants.tip_mccormick_K * (circulation_ratio ** constants.tip_mccormick_m) * Re_ratio
    else:
        sigma_crit_tip = 0.0

    # Tip region blending (fade in from tip_start_rR to tip_end_rR)
    tip_range = max(constants.tip_end_rR - constants.tip_start_rR, 1e-3)
    tip_factor = max(min((r_over_R - constants.tip_start_rR) / tip_range, 1.0), 0.0)

    tip_severity_raw = (sigma_crit_tip - sigma_local) / max(sigma_crit_tip, eps)
    tip_severity = tip_factor * max(min(tip_severity_raw, 1.0), 0.0)

    tip_vortex_index_i = sigma_crit_tip / max(sigma_local, eps)
    
    # ----------------------------------------------------
    # COMBINED CAVITATION
    # ----------------------------------------------------
    combined_severity_i = max(sheet_severity, constants.lambda_tip * tip_severity)
    
    return sigma_local, sigma_crit_sheet, sheet_severity, sigma_crit_tip, tip_factor, tip_severity, tip_vortex_index_i, combined_severity_i
