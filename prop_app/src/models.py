from dataclasses import dataclass, field
from typing import List
from typing import List, Optional

@dataclass
class FoilContour:
    x_upper: List[float]
    y_upper: List[float]
    x_lower: List[float]
    y_lower: List[float]

@dataclass
class BladeSection:
    r_over_R: float
    r: float
    chord: float
    thickness: float
    pitch: float
    camber: float
    skew_deg: float
    rake: float
    foil_contour: Optional[FoilContour] = None
    dr: float = 0.0

@dataclass
class PropellerGeometry:
    propeller_id: str
    file_name: str
    description: str
    blade_count: int
    diameter: float
    radius: float
    hub_radius: float
    expanded_area_ratio: float
    sections: List[BladeSection]

@dataclass
class OperatingConditions:
    rpm: float
    Va_ship: float
    w: float
    rho: float
    nu: float
    pv: float
    p_atm: float
    h: float
    g: float = 9.81
    nozzle_mode: str = "open"  

@dataclass
class NozzleSelection:
    nozzle_id: str = "open"
    effectiveness: float = 1.0
    tip_clearance_m_override: float | None = None

@dataclass
class ModelConstants:
    suction_factor_k: float = 1.35
    k_induced: float = 0.02
    cd0_base: float = 0.008
    thickness_drag_multiplier: float = 0.12
    camber_drag_multiplier: float = 0.01
    cl_slope_factor: float = 6.283185  # 2 * pi
    cl_max_base: float = 1.1
    cl_max_camber_multiplier: float = 2.0
    reynolds_reference: float = 2e5
    reynolds_drag_exponent: float = 0.1
    
    # New Sheet Cavitation Constants
    sheet_sigma_a0: float = 0.35
    sheet_sigma_a1_cl: float = 1.20
    sheet_sigma_a2_alpha: float = 0.08
    sheet_sigma_a3_tc: float = 0.02
    sheet_softening_exp: float = 1.15
    
    # New Tip Vortex Cavitation Constants
    tip_sigma_b0: float = 0.55
    tip_sigma_b1_gamma: float = 2.00
    tip_sigma_b2_dgamma: float = 0.50
    tip_sigma_b3_tip_factor: float = 0.60
    tip_start_rR: float = 0.85
    tip_end_rR: float = 1.00
    nozzle_tip_vortex_suppression: float = 0.35
    
    # New Physical Nozzle Constants
    nozzle_19a_inflow_gain: float = 0.15
    nozzle_37_inflow_gain: float = 0.10
    nozzle_thrust_tn_a0: float = 0.04
    nozzle_thrust_tn_a1: float = -0.02
    nozzle_thrust_tn_a2: float = -0.01
    tip_gap_sensitivity: float = 20.0
    tip_image_strength_base: float = 0.85
    
    # Combined Constants
    lambda_tip: float = 1.0

@dataclass
class SectionResult:
    r_over_R: float
    r: float
    chord: float
    thickness: float
    pitch: float
    camber: float
    beta_geom: float
    beta_i: float
    alpha: float
    alpha_eff: float
    CL: float
    CD: float
    Gamma: float
    dT: float
    dQ: float
    Re: float
    q_dyn: float
    sigma_local: float
    sigma_crit_sheet: float
    sheet_severity: float
    sigma_crit_tip: float
    tip_region: float
    tip_severity: float
    tip_vortex_index_i: float
    combined_severity: float = 0.0
    nozzle_u_local: float = 0.0

@dataclass
class PerformanceResult:
    prop_geom: PropellerGeometry
    conditions: OperatingConditions
    J: float
    
    # Explicit Open-Water Reference
    KT_open_reference: float
    KQ_open_reference: float
    T_open_reference: float
    Q_open_reference: float
    Pshaft_open_reference: float
    eta_open_reference: float
    
    # Explicit Propeller inside Nozzle (Mass flux affected, but excludes KTN itself)
    KT_prop_with_nozzle_flow: float
    KQ_prop_with_nozzle_flow: float
    T_prop_with_nozzle_flow: float
    Q_prop_with_nozzle_flow: float
    
    # Pure Nozzle Contribution
    KTN: float
    T_nozzle: float
    nozzle_share: float
    
    # Total System (Strictly: prop_with_nozzle + nozzle)
    KT_total: float
    KQ_total: float
    T_total: float
    Q_total: float
    Pshaft_total: float
    eta_total: float
    
    static_efficiency_est: float | None
    thrust_per_power_N_per_W: float | None
    Sheet_Cavitation_Est_PCT: float
    Tip_Vortex_Cavitation_Est_PCT: float
    Combined_Cavitation_Est_PCT: float
    Tip_Vortex_Cav_Index: float
    section_results: List[SectionResult]
    warnings: List[str]

