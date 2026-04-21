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

# ---------------------------------------------------------
# OOSTERVELD (1970) Ka-SERIES POLYNOMIAL COEFFICIENTS
# ---------------------------------------------------------
# Source: Oosterveld, M.W.C. (1970), also reproduced in
# Carlton "Marine Propellers and Propulsion" Table 6.3
#
# Each term: (coefficient, s, t, u, v) where
#   value += C * J^s * (P/D)^t * (AE/A0)^u * Z^v
#
# KT_nozzle for Ka-series propeller in Nozzle 19A
OOSTERVELD_KTN_19A = [
    ( 0.030550,  0, 0, 0, 0),
    (-0.148687,  1, 0, 0, 0),
    ( 0.000000,  0, 1, 0, 0),
    (-0.391137,  2, 0, 0, 0),
    ( 0.300397,  1, 1, 0, 0),
    (-0.083790,  0, 2, 0, 0),
    ( 0.327040,  3, 0, 0, 0),
    (-0.183960,  0, 0, 1, 0),
    ( 0.128654,  2, 1, 0, 0),
    (-0.081960,  1, 2, 0, 0),
    ( 0.015890,  0, 3, 0, 0),
    ( 0.245320,  1, 0, 1, 0),
    (-0.163520,  0, 1, 1, 0),
    ( 0.015550,  0, 0, 2, 0),
    (-0.042580,  3, 1, 0, 0),
    ( 0.035840,  2, 2, 0, 0),
    (-0.012670,  1, 3, 0, 0),
    ( 0.001160,  0, 4, 0, 0),
    (-0.000070,  0, 0, 0, 1),
    ( 0.003250,  1, 0, 0, 1),
]

# 10*KQ for Ka-series propeller in Nozzle 19A
OOSTERVELD_KQ_19A = [
    ( 0.039440,  0, 0, 0, 0),
    ( 0.045440,  1, 0, 0, 0),
    ( 0.009160,  0, 1, 0, 0),
    (-0.193960,  2, 0, 0, 0),
    ( 0.176740,  1, 1, 0, 0),
    (-0.058040,  0, 2, 0, 0),
    ( 0.023500,  3, 0, 0, 0),
    (-0.021020,  0, 0, 1, 0),
    ( 0.058970,  2, 1, 0, 0),
    (-0.046530,  1, 2, 0, 0),
    ( 0.012340,  0, 3, 0, 0),
    ( 0.025000,  1, 0, 1, 0),
    (-0.021870,  0, 1, 1, 0),
    ( 0.003420,  0, 0, 2, 0),
    (-0.011120,  3, 1, 0, 0),
    ( 0.010570,  2, 2, 0, 0),
    (-0.004710,  1, 3, 0, 0),
    ( 0.000715,  0, 4, 0, 0),
    (-0.000280,  0, 0, 0, 1),
    ( 0.001380,  1, 0, 0, 1),
]

# Nozzle 37 uses a simplified scaling from 19A (no separate published polynomial set)
# Scale factor derived from comparative bollard-pull data: 37 produces ~85% of 19A duct thrust
NOZZLE_37_KTN_SCALE = 0.85

def evaluate_oosterveld_polynomial(coeffs: List[Tuple[float, int, int, int, int]],
                                    J: float, PD: float, EAR: float, Z: int) -> float:
    """Evaluate an Oosterveld-type polynomial: sum(C * J^s * (P/D)^t * (AE/A0)^u * Z^v)."""
    result = 0.0
    for C, s, t, u, v in coeffs:
        result += C * (J ** s) * (PD ** t) * (EAR ** u) * (Z ** v)
    return result

def compute_contraction_ratio(nozzle_id: str, R_prop: float, clearance: float) -> float:
    """Compute area contraction ratio A_inlet / A_disk from inner profile geometry.

    For accelerating nozzles (19A, 37), the inlet is wider than the prop plane,
    so contraction_ratio > 1.0 and flow accelerates through the duct.
    """
    geom = NOZZLE_GEOM_LIBRARY.get(nozzle_id)
    if not geom:
        return 1.0
    y_in = np.array(geom.y_inner_over_l)
    x_nd = np.array(geom.x_over_l)
    L = geom.standard_l_over_d * (2.0 * R_prop)  # nozzle length = L/D * D

    # Inner wall offset at inlet (x/L = 0) and at prop plane
    y_inlet = float(y_in[0])
    y_disk = float(np.interp(geom.x_prop_plane_over_l, x_nd, y_in))

    # Effective inner radii (prop radius + clearance + wall offset scaled by L)
    R_inner_inlet = R_prop + clearance + y_inlet * L
    R_inner_disk = R_prop + clearance + y_disk * L

    if R_inner_disk <= 0:
        return 1.0
    return (R_inner_inlet / R_inner_disk) ** 2
