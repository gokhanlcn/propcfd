import math
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

@dataclass
class NozzleGeometryDef:
    nozzle_id: str
    display_name: str
    standard_l_over_d: float
    default_tip_clearance_ratio: float
    default_te_thickness_ratio: float
    profile_source: str
    profile_notes: str
    geometry_definition_type: str
    x_over_l: List[float]
    y_inner_over_l: List[float]
    y_outer_over_l: List[float]
    interpolation_mode: str
    is_approximate_outer_profile: bool
    x_prop_plane_over_l: float  # <--- explicitly define where prop sits
    supports_3d_render: bool = True

@dataclass
class NozzlePerformanceDef:
    nozzle_id: str
    tn_a0: float
    tn_a1: float
    tn_a2: float
    pressure_recovery_factor: float
    cavitation_relief_factor: float
    inflow_gain: float
    tip_image_strength: float
    description: str

# ---------------------------------------------------------
# NOZZLE 19A (Based on MARIN/Wageningen Nozzle 19A)
# ---------------------------------------------------------
# Source: Oosterveld, M.W.C. (1970). "Wake Adapted Ducted Propellers." 
# x/L base
x_common = [
  0.0, 0.0125, 0.025, 0.050, 0.075, 0.100, 0.150, 0.200,
  0.25, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 1.00
]

# 19A Inner Ordinates (yi/L)
y_in_19A = [
  0.1825, 0.1466, 0.1280, 0.1087, 0.0800, 0.0634, 0.0387, 0.0217,
  0.0110, 0.0048, 0.0, 0.0, 0.0, 0.0029, 0.0082, 0.0145, 0.0186, 0.0236
]

# 19A Outer Ordinates (yu/L) via linear interpolation over control points
yu_19A_ctrl = [
  (0.0,    0.2072),
  (0.0125, 0.2107),
  (0.0250, 0.2080),
  (1.0000, 0.0636),
]
x_ctrl_19A = [cp[0] for cp in yu_19A_ctrl]
y_ctrl_19A = [cp[1] for cp in yu_19A_ctrl]
y_out_19A = np.interp(x_common, x_ctrl_19A, y_ctrl_19A).tolist()

nozzle_19A_geom = NozzleGeometryDef(
    nozzle_id="19A",
    display_name="MARIN / Wageningen 19A",
    standard_l_over_d=0.5,
    default_tip_clearance_ratio=0.01,
    default_te_thickness_ratio=0.02,
    profile_source="Oosterveld, M.W.C. (1970) Wake Adapted Ducted Propellers",
    profile_notes="Standard accelerating nozzle profile, inner exact, outer smoothed representation.",
    geometry_definition_type="tabulated",
    x_over_l=x_common,
    y_inner_over_l=y_in_19A,
    y_outer_over_l=y_out_19A,
    interpolation_mode="linear",
    is_approximate_outer_profile=True,
    x_prop_plane_over_l=0.5  # Typical for ducted propellers
)

nozzle_19A_perf = NozzlePerformanceDef(
    nozzle_id="19A",
    tn_a0=0.045,  # Thrust contribution parameters
    tn_a1=-0.02,
    tn_a2=-0.01,
    pressure_recovery_factor=1.05,
    cavitation_relief_factor=1.30,
    inflow_gain=0.15,  # 19A Accelerates flow strongly
    tip_image_strength=0.90, # Strongly reduces tip loss due to thick profile
    description="Accelerating nozzle, high static thrust, mitigates tip vortex."
)

# ---------------------------------------------------------
# NOZZLE 37 (Based on MARIN/Wageningen Nozzle 37)
# ---------------------------------------------------------
# 37 Inner Ordinates (yi/L)
y_in_37 = [
  0.1833, 0.1500, 0.1310, 0.1000, 0.0790, 0.0611, 0.0360, 0.0200,
  0.0100, 0.0040, 0.0, 0.0, 0.0, 0.0020, 0.0110, 0.0380, 0.0660, 0.1242
]

# 37 Outer Ordinates (yu/L) via linear interpolation over control points
yu_37_ctrl = [
  (0.0,    0.1833),
  (0.0125, 0.2130),
  (0.0250, 0.2170),
  (0.0500, 0.2160),
  (0.9500, 0.1600),
  (1.0000, 0.1242),
]
x_ctrl_37 = [cp[0] for cp in yu_37_ctrl]
y_ctrl_37 = [cp[1] for cp in yu_37_ctrl]
y_out_37 = np.interp(x_common, x_ctrl_37, y_ctrl_37).tolist()

nozzle_37_geom = NozzleGeometryDef(
    nozzle_id="37",
    display_name="MARIN / Wageningen 37",
    standard_l_over_d=0.5,
    default_tip_clearance_ratio=0.015,
    default_te_thickness_ratio=0.03,
    profile_source="Standard duct geometries",
    profile_notes="Accelerating nozzle with thicker sections. Outer contour is an interpolated engineering approximation.",
    geometry_definition_type="tabulated",
    x_over_l=x_common,
    y_inner_over_l=y_in_37,
    y_outer_over_l=y_out_37,
    interpolation_mode="linear",
    is_approximate_outer_profile=True,
    x_prop_plane_over_l=0.5
)

nozzle_37_perf = NozzlePerformanceDef(
    nozzle_id="37",
    tn_a0=0.038,
    tn_a1=-0.015,
    tn_a2=-0.01,
    pressure_recovery_factor=1.03,
    cavitation_relief_factor=1.20,
    inflow_gain=0.10, # 37 Accelerates flow less aggressively
    tip_image_strength=0.85, # Reduces tip loss slightly less
    description="Accelerating nozzle, slightly lower static thrust than 19A but better astern."
)

NOZZLE_GEOM_LIBRARY: Dict[str, NozzleGeometryDef] = {
    "19A": nozzle_19A_geom,
    "37": nozzle_37_geom
}

NOZZLE_PERF_LIBRARY: Dict[str, NozzlePerformanceDef] = {
    "19A": nozzle_19A_perf,
    "37": nozzle_37_perf
}

def get_nozzle_geometry(nozzle_id: str) -> Optional[NozzleGeometryDef]:
    return NOZZLE_GEOM_LIBRARY.get(nozzle_id)

def get_nozzle_performance(nozzle_id: str) -> Optional[NozzlePerformanceDef]:
    return NOZZLE_PERF_LIBRARY.get(nozzle_id)
