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
    
    # Sheet Cavitation Constants (Brockett -Cp_min based)
    sheet_cpmin_thickness_k: float = 1.0     # thickness contribution factor
    sheet_cpmin_loading_k: float = 0.25      # loading-dependent suction peak factor
    sheet_cpmin_ideal_cl: float = 0.0        # CL at ideal incidence (zero LE loading)
    sheet_severity_scale: float = 1.0        # calibration multiplier for severity output
    
    # Tip Vortex Cavitation Constants (McCormick model)
    tip_mccormick_K: float = 0.55            # proportionality constant
    tip_mccormick_m: float = 2.0             # circulation exponent (theoretical = 2)
    tip_mccormick_n: float = 0.35            # Reynolds number exponent
    tip_mccormick_Re_ref: float = 2e6        # reference Reynolds number
    tip_core_radius_coeff: float = 0.10      # r_c / c proportionality
    tip_start_rR: float = 0.85
    tip_end_rR: float = 1.00
    
    # Nozzle Interaction Constants
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

