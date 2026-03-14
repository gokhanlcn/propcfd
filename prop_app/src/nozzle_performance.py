from dataclasses import dataclass
from typing import Tuple, Optional, Callable
import math
import numpy as np
from .models import NozzleSelection, ModelConstants
from .nozzle_library import get_nozzle_performance, get_nozzle_geometry, NozzlePerformanceDef

@dataclass
class NozzleAerodynamics:
    is_active: bool
    nozzle_id: str
    l_over_d: float
    camber_ratio: float
    thickness_ratio: float
    clearance_ratio: float
    pressure_recovery: float
    cavitation_relief: float
    tip_gap_relief_factor: float
    u_nozzle_func: Callable[[float, float], float]

def get_nozzle_aerodynamics(selection: NozzleSelection, J: float, D: float, constants: ModelConstants) -> NozzleAerodynamics:
    """
    Extracts nondimensional descriptors (L/D, clearance, camber, type) for Wageningen Ka-Series mapping.
    """
    if selection.nozzle_id == "open":
        return NozzleAerodynamics(False, "open", 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, lambda r, v: 0.0)
        
    perf: Optional[NozzlePerformanceDef] = get_nozzle_performance(selection.nozzle_id)
    geom_def = get_nozzle_geometry(selection.nozzle_id)
    if not perf or not geom_def:
        return NozzleAerodynamics(False, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, lambda r, v: 0.0)
        
    eff = selection.effectiveness
    
    # --- NONDIMENSIONAL DESCRIPTOR EXTRACTION ---
    clearance_m = selection.tip_clearance_m_override if selection.tip_clearance_m_override is not None else 0.01 * D
    clearance_ratio_val = clearance_m / max(D, 1e-6)
    l_over_d_val = geom_def.standard_l_over_d

    y_in_nd = np.array(geom_def.y_inner_over_l)
    y_out_nd = np.array(geom_def.y_outer_over_l)
    
    # Camber Drop (detects accelerating capacity)
    y_camber = (y_in_nd + y_out_nd) / 2.0
    camber_ratio_val = float(y_camber[0] - y_camber[-1])
    
    # Thickness Peak (correlates to boundary layer width and form drag)
    thickness = y_out_nd - y_in_nd
    thickness_ratio_val = float(np.max(thickness))
    
    # --- CLEARANCE INTERACTION MODIFIER ---
    gap_penalty = constants.tip_gap_sensitivity * clearance_ratio_val
    image_strength_base = perf.tip_image_strength if hasattr(perf, 'tip_image_strength') else constants.tip_image_strength_base
    tip_gap_relief_factor = 1.0 - (image_strength_base * eff * math.exp(-gap_penalty))
    tip_gap_relief_factor = max(min(tip_gap_relief_factor, 1.0), 0.1) 
    
    # --- CAVITATION/PRESSURE RELIEF SECUREMENTS ---
    pressure_recovery = 1.0 + (perf.pressure_recovery_factor - 1.0) * eff
    cavitation_relief = 1.0 + (perf.cavitation_relief_factor - 1.0) * eff
    
    # --- SURROGATE-COUPLED RADIAL INFLOW (u_nozzle) ---
    def u_nozzle_func(r_over_R: float, V_inflow: float) -> float:
        """
        Published-Data Informed Inflow bound: Strongly scaled down to prevent free-thrust torque starvation. 
        Acceleration only realistically modifies the bounding annulus 5-15% ahead of the prop plane.
        """
        bl_exponent = 1.0 / max(thickness_ratio_val * 8.0, 0.5) 
        amplitude = max(min(camber_ratio_val * 0.4 * eff, 0.15), 0.02)
        return V_inflow * amplitude * (r_over_R ** bl_exponent)
    
    return NozzleAerodynamics(
        is_active=True,
        nozzle_id=selection.nozzle_id,
        l_over_d=l_over_d_val,
        camber_ratio=camber_ratio_val,
        thickness_ratio=thickness_ratio_val,
        clearance_ratio=clearance_ratio_val,
        pressure_recovery=pressure_recovery,
        cavitation_relief=cavitation_relief,
        tip_gap_relief_factor=tip_gap_relief_factor,
        u_nozzle_func=u_nozzle_func
    )
