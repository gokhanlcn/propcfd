import math
from .models import ModelConstants

def calculate_section_cavitation(
    p_inf: float, 
    p_inf_noz: float,
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
    active_nozzle: bool,
    constants: ModelConstants
) -> tuple[float, float, float, float, float, float, float, float]:
    
    # Base local pressure
    p_ref = p_inf_noz if active_nozzle else p_inf
    sigma_local = (p_ref - pv) / max(q, 1e-6)
    
    eps = 1e-6
    tc_ratio = t / max(c, eps)
    alpha_deg = abs(alpha) * 180.0 / math.pi
    
    # ----------------------------------------------------
    # SHEET CAVITATION
    # ----------------------------------------------------
    sigma_crit_sheet = (
        constants.sheet_sigma_a0
        + constants.sheet_sigma_a1_cl * abs(CL)
        + constants.sheet_sigma_a2_alpha * alpha_deg
        + constants.sheet_sigma_a3_tc / (tc_ratio + eps)
    )
    
    sheet_severity_raw = (sigma_crit_sheet - sigma_local) / max(sigma_crit_sheet, eps)
    sheet_severity = max(min(sheet_severity_raw, 1.0), 0.0)
    sheet_severity = sheet_severity ** constants.sheet_softening_exp
    
    # ----------------------------------------------------
    # TIP VORTEX CAVITATION
    # ----------------------------------------------------
    gamma_norm = Gamma / max(Vrel * c, eps)
    dGamma_dr_norm = dGamma_dr / max(Vrel, eps)
    
    tip_range = max(constants.tip_end_rR - constants.tip_start_rR, 1e-3)
    tip_factor = max(min((r_over_R - constants.tip_start_rR) / tip_range, 1.0), 0.0)
    
    sigma_crit_tip = (
        constants.tip_sigma_b0
        + constants.tip_sigma_b1_gamma * abs(gamma_norm)
        + constants.tip_sigma_b2_dgamma * abs(dGamma_dr_norm)
        + constants.tip_sigma_b3_tip_factor * tip_factor
    )
    
    tip_severity_raw = (sigma_crit_tip - sigma_local) / max(sigma_crit_tip, eps)
    tip_severity = tip_factor * max(min(tip_severity_raw, 1.0), 0.0)
    
    # Duct suppression is naturally handled by lower local alpha and constrained Gamma distributions.
    # We no longer apply an arbitrary `suppression` multiplier.
        
    tip_vortex_index_i = sigma_crit_tip / max(sigma_local, eps)
    
    # ----------------------------------------------------
    # COMBINED CAVITATION
    # ----------------------------------------------------
    combined_severity_i = max(sheet_severity, constants.lambda_tip * tip_severity)
    
    return sigma_local, sigma_crit_sheet, sheet_severity, sigma_crit_tip, tip_factor, tip_severity, tip_vortex_index_i, combined_severity_i
