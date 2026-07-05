"""Open-water reference (validated polynomial) + BEMT calibration.

For the propellers shipped with this project the *correct* open-water KT/KQ are
known analytically: B-series files follow the Wageningen B regression exactly.
This module:

  1. Detects the propeller series (filename hint + geometry sanity).
  2. Evaluates the validated open-water reference KT/KQ at a given J.
  3. Produces multiplicative calibration factors that scale the BEMT section
     loads so the integrated thrust/torque match the reference. The BEMT then
     supplies the *radial distribution* (for cavitation) while the *level* comes
     from the validated polynomial -- the standard preliminary-design hybrid.

For a 'generic' propeller no reference exists, the factors are 1.0, and the raw
(calibrated-slope) BEMT result stands on its own with a documented uncertainty.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from ..models import PropellerGeometry
from . import polynomials as poly


@dataclass
class OpenWaterReference:
    series: str            # "B", "Ka", or "generic"
    KT: Optional[float]    # reference open-water thrust coeff (None if generic)
    KQ: Optional[float]    # reference open-water torque coeff (None if generic)
    valid: bool            # within the regression's parameter range
    note: str


def representative_PD(geom: PropellerGeometry) -> float:
    best = None
    for s in geom.sections:
        if best is None or abs(s.r_over_R - 0.7) < abs(best.r_over_R - 0.7):
            best = s
    return (best.pitch / geom.diameter) if (best and geom.diameter > 0) else 1.0


def detect_series(geom: PropellerGeometry, hint: str = "") -> str:
    """Best-effort series detection from the filename and id."""
    text = f"{hint} {geom.file_name} {geom.propeller_id}".lower()
    if "ka" in text or "kaplan" in text or "19a" in text or "37" in text:
        return "Ka"
    if "wageningen" in text or text.strip().startswith("b") or "/b" in text or "\\b" in text:
        return "B"
    # Fallback: filenames like "B3.hcpc"
    base = geom.file_name.lower()
    if base.startswith("b") and any(ch.isdigit() for ch in base[:3]):
        return "B"
    if base.startswith("ka"):
        return "Ka"
    return "generic"


def open_water_reference(geom: PropellerGeometry, J: float, series: str) -> OpenWaterReference:
    PD = representative_PD(geom)
    EAR = geom.expanded_area_ratio
    Z = geom.blade_count

    if series == "B":
        in_range = (2 <= Z <= 7 and 0.30 <= EAR <= 1.05 and 0.5 <= PD <= 1.4)
        KT = poly.wageningen_b_kt(J, PD, EAR, Z)
        KQ = poly.wageningen_b_kq(J, PD, EAR, Z)
        note = "Wageningen B-series (Oosterveld & van Oossanen 1975)"
        if not in_range:
            note += " [outside regression range -- extrapolated]"
        return OpenWaterReference("B", KT, KQ, in_range, note)

    # Ka open-water and any generic geometry: no validated polynomial available.
    note = ("Ka-series open-water polynomial not bundled (see polynomials.py); "
            if series == "Ka" else "Generic geometry; ")
    note += "BEMT used without polynomial calibration."
    return OpenWaterReference(series, None, None, False, note)


def calibration_factors(reference: OpenWaterReference,
                        KT_bemt: float, KQ_bemt: float) -> tuple:
    """Return (fT, fQ) so that fT*KT_bemt == KT_ref (when a reference exists)."""
    fT = fQ = 1.0
    if reference.KT is not None and KT_bemt > 1e-6 and reference.KT > 0:
        fT = reference.KT / KT_bemt
    if reference.KQ is not None and KQ_bemt > 1e-9 and reference.KQ > 0:
        fQ = reference.KQ / KQ_bemt
    # Guard against pathological factors from near-zero BEMT loads.
    fT = min(max(fT, 0.2), 5.0)
    fQ = min(max(fQ, 0.2), 5.0)
    return fT, fQ
