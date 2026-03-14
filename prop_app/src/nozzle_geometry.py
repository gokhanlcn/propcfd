import numpy as np
from scipy.interpolate import interp1d
from typing import Tuple, List, Optional
from .models import PropellerGeometry
from .nozzle_library import NozzleGeometryDef

class ScaledNozzleGeometry:
    def __init__(self, D: float, L: float, clearance: float, 
                 x_m: np.ndarray, r_in_m: np.ndarray, r_out_m: np.ndarray, def_info: NozzleGeometryDef,
                 x_start: float, x_end: float, x_prop_plane: float,
                 min_r_inner: float, clearance_prop_plane: float, min_clearance: float):
        self.D = D
        self.L = L
        self.clearance = clearance
        
        # Geometry arrays in common reference frame
        self.x_m = x_m
        self.r_in_m = r_in_m
        self.r_out_m = r_out_m
        self.def_info = def_info
        
        # Explicit placement markers in common reference frame
        self.x_start = x_start
        self.x_end = x_end
        self.x_prop_plane = x_prop_plane
        
        # Debug/Clearance metrics
        self.min_r_inner = min_r_inner
        self.clearance_prop_plane = clearance_prop_plane
        self.min_clearance = min_clearance

def generate_scaled_nozzle(prop_geom: PropellerGeometry, nozzle_def: Optional[NozzleGeometryDef], 
                           clearance_m_override: Optional[float] = None) -> Optional[ScaledNozzleGeometry]:
    """
    Scales non-dimensional nozzle ordinates to metric coordinates based on the propeller's
    Diameter (D) and specified Tip Clearance.
    """
    if not nozzle_def:
        return None
        
    D = prop_geom.diameter
    R_prop = prop_geom.radius
    L = D * nozzle_def.standard_l_over_d
    
    clearance = clearance_m_override if clearance_m_override is not None else (D * nozzle_def.default_tip_clearance_ratio)
    
    # --- 1. REFERENCE FRAME ALIGNMENT ---
    # User's Explicit Request: Propeller rotation plane = x=0.
    # The normalized x vector ranges from 0 to 1.
    x_prop_plane_nd = nozzle_def.x_prop_plane_over_l
    
    # --- 2. EXACT DIMENSIONAL MAPPING ---
    # L_mm = standard_l_over_d * D
    # tip_clearance_mm = clearance_override OR default_tip_clearance_ratio * D
    # r_inner_m = R_prop + clearance + (yi_nd * L)
    # r_outer_m = R_prop + clearance + (yu_nd * L)
    
    x_nd = np.array(nozzle_def.x_over_l)
    y_in_nd = np.array(nozzle_def.y_inner_over_l)
    y_out_nd = np.array(nozzle_def.y_outer_over_l)
    
    # We interpolate onto a smoother normalized domain
    num_pts = 200
    x_smooth_nd = np.linspace(0.0, 1.0, num_pts)
    
    kind = 'cubic' if nozzle_def.interpolation_mode == 'cubic' else 'linear'
    try:
        f_in = interp1d(x_nd, y_in_nd, kind=kind)
        f_out = interp1d(x_nd, y_out_nd, kind=kind)
        y_in_smooth_nd = f_in(x_smooth_nd)
        y_out_smooth_nd = f_out(x_smooth_nd)
    except Exception:
        f_in = interp1d(x_nd, y_in_nd, kind='linear')
        f_out = interp1d(x_nd, y_out_nd, kind='linear')
        y_in_smooth_nd = f_in(x_smooth_nd)
        y_out_smooth_nd = f_out(x_smooth_nd)
        
    # --- 3. DIMENSIONAL CONVERSION & SHIFTING ---
    # X shifts mathematically so x_prop_plane_nd -> 0
    x_m = (x_smooth_nd - x_prop_plane_nd) * L 
    
    # Radius explicitly sums Prop Radius + Radial Clearance + Geometry Thickness
    r_in_m = R_prop + clearance + (y_in_smooth_nd * L)
    r_out_m = R_prop + clearance + (y_out_smooth_nd * L)
    
    # --- 4. PLACEMENT METRICS & DEBUG VARS ---
    x_start = -x_prop_plane_nd * L
    x_end = (1.0 - x_prop_plane_nd) * L
    x_prop_plane = 0.0
    
    min_r_inner = float(np.min(r_in_m))
    
    # Exact interpolation for r_inner at X=0
    try:
        r_inner_at_prop = float(interp1d(x_m, r_in_m)(0.0))
    except ValueError:
        r_inner_at_prop = float(r_in_m[np.argmin(np.abs(x_m))])
        
    clearance_prop_plane = r_inner_at_prop - R_prop
    min_clearance = min_r_inner - R_prop
    
    return ScaledNozzleGeometry(
        D=D, L=L, clearance=clearance,
        x_m=x_m, r_in_m=r_in_m, r_out_m=r_out_m,
        def_info=nozzle_def,
        x_start=x_start, x_end=x_end, x_prop_plane=x_prop_plane,
        min_r_inner=min_r_inner, clearance_prop_plane=clearance_prop_plane, min_clearance=min_clearance
    )
