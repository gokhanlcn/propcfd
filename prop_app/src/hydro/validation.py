"""Validation harness: model vs. literature polynomials.

This module is the project's *definition of done*. It runs the physics solvers
across the bundled example geometries and reports the deviation from the
authoritative Wageningen B-series polynomial (open water). It is also the
instrument used to globally calibrate the handful of free constants -- never to
a single case, always across all B-series files and a J sweep.

Run from the project root:  python -m src.hydro.validation
"""
from __future__ import annotations
import glob
import math
import os
from dataclasses import dataclass
from typing import List

from ..parser_hcpc import parse_hcpc_content
from ..models import OperatingConditions
from .openwater import OpenWaterConstants, solve_bemt
from . import polynomials as poly


@dataclass
class SweepPoint:
    J: float
    KT_model: float
    KQ_model: float
    KT_ref: float
    KQ_ref: float


def _representative_PD(geom) -> float:
    """P/D taken at the 0.7R section (marine convention)."""
    best = None
    for s in geom.sections:
        if best is None or abs(s.r_over_R - 0.7) < abs(best.r_over_R - 0.7):
            best = s
    return (best.pitch / geom.diameter) if (best and geom.diameter > 0) else 1.0


def sweep_open_water(geom, consts: OpenWaterConstants, rho=1025.0, nu=1.19e-6,
                     n_rps=20.0, J_values=None) -> List[SweepPoint]:
    """Sweep J for one geometry: BEMT KT/KQ vs Wageningen B polynomial."""
    if J_values is None:
        J_values = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    D = geom.diameter
    PD = _representative_PD(geom)
    EAR = geom.expanded_area_ratio
    Z = geom.blade_count

    out: List[SweepPoint] = []
    for J in J_values:
        Va = J * n_rps * D
        cond = OperatingConditions(rpm=n_rps * 60.0, Va_ship=Va, w=0.0,
                                   rho=rho, nu=nu, pv=2338.0, p_atm=101325.0, h=2.0)
        res = solve_bemt(geom, cond, consts)
        denom_T = rho * n_rps ** 2 * D ** 4
        denom_Q = rho * n_rps ** 2 * D ** 5
        KT = res.T / denom_T if denom_T > 0 else 0.0
        KQ = res.Q / denom_Q if denom_Q > 0 else 0.0
        out.append(SweepPoint(
            J=J, KT_model=KT, KQ_model=KQ,
            KT_ref=poly.wageningen_b_kt(J, PD, EAR, Z),
            KQ_ref=poly.wageningen_b_kq(J, PD, EAR, Z),
        ))
    return out


def _rms_pct(points: List[SweepPoint]) -> tuple:
    """RMS percentage error of KT and 10KQ over the points where ref > 0.02."""
    et, eq, nt, nq = 0.0, 0.0, 0, 0
    for p in points:
        if p.KT_ref > 0.02:
            et += ((p.KT_model - p.KT_ref) / p.KT_ref) ** 2
            nt += 1
        if p.KQ_ref > 0.002:
            eq += ((p.KQ_model - p.KQ_ref) / p.KQ_ref) ** 2
            nq += 1
    rt = math.sqrt(et / nt) * 100.0 if nt else float('nan')
    rq = math.sqrt(eq / nq) * 100.0 if nq else float('nan')
    return rt, rq


def run_b_series_report(b_glob: str, consts: OpenWaterConstants = None) -> None:
    consts = consts or OpenWaterConstants()
    files = sorted(glob.glob(b_glob))
    if not files:
        print(f"No files matched {b_glob}")
        return
    print("=" * 78)
    print("OPEN-WATER BEMT  vs  WAGENINGEN B-SERIES POLYNOMIAL")
    print("=" * 78)
    print(f"{'file':<16}{'P/D':>6}{'EAR':>6}{'Z':>3}{'KT rms%':>10}{'10KQ rms%':>11}")
    all_t, all_q = [], []
    for f in files:
        with open(f, encoding="utf-8", errors="replace") as fh:
            geom = parse_hcpc_content(fh.read(), os.path.basename(f))
        pts = sweep_open_water(geom, consts)
        rt, rq = _rms_pct(pts)
        all_t.append(rt)
        all_q.append(rq)
        print(f"{os.path.basename(f):<16}{_representative_PD(geom):>6.2f}"
              f"{geom.expanded_area_ratio:>6.2f}{geom.blade_count:>3}{rt:>10.1f}{rq:>11.1f}")
    valid_t = [x for x in all_t if x == x]
    valid_q = [x for x in all_q if x == x]
    print("-" * 78)
    print(f"{'MEAN':<31}{sum(valid_t)/len(valid_t):>10.1f}"
          f"{sum(valid_q)/len(valid_q):>11.1f}")


def print_detail(file_path: str, consts: OpenWaterConstants = None) -> None:
    consts = consts or OpenWaterConstants()
    with open(file_path, encoding="utf-8", errors="replace") as fh:
        geom = parse_hcpc_content(fh.read(), os.path.basename(file_path))
    pts = sweep_open_water(geom, consts)
    print(f"\nDETAIL: {os.path.basename(file_path)}  "
          f"P/D={_representative_PD(geom):.2f} EAR={geom.expanded_area_ratio:.2f} Z={geom.blade_count}")
    print(f"{'J':>5}{'KT_mdl':>9}{'KT_ref':>9}{'10KQ_mdl':>10}{'10KQ_ref':>10}"
          f"{'eta_mdl':>9}{'eta_ref':>9}")
    for p in pts:
        em = (p.J / (2 * math.pi)) * p.KT_model / p.KQ_model if p.KQ_model > 0 else 0
        er = (p.J / (2 * math.pi)) * p.KT_ref / p.KQ_ref if p.KQ_ref > 0 else 0
        print(f"{p.J:>5.2f}{p.KT_model:>9.4f}{p.KT_ref:>9.4f}"
              f"{10*p.KQ_model:>10.4f}{10*p.KQ_ref:>10.4f}{em:>9.3f}{er:>9.3f}")


def run_ducted_sanity(ka_glob: str, ow=None) -> None:
    """Physical-sanity report for ducted modes (no Ka polynomial available).

    Checks the qualitative facts that MUST hold for an accelerating duct:
    bollard thrust augmentation in the documented ~1.3-1.5x band, efficiency
    below 1, and monotone (non-oscillating) open-water thrust.
    """
    from ..models import OperatingConditions, NozzleSelection
    from ..solver import solve_performance
    ow = ow or OpenWaterConstants()
    files = sorted(glob.glob(ka_glob))
    if not files:
        print(f"No files matched {ka_glob}")
        return
    print("\n" + "=" * 78)
    print("DUCTED-MODE PHYSICAL SANITY (19A) -- no polynomial reference exists")
    print("=" * 78)
    print(f"{'file':<14}{'bollard T/To':>13}{'eta<1':>7}{'monotone T':>12}{'maxCav%':>9}")
    for f in files:
        with open(f, encoding="utf-8", errors="replace") as fh:
            geom = parse_hcpc_content(fh.read(), os.path.basename(f))
        D = geom.diameter
        n = 20.0
        # bollard augmentation (the solver reads the duct mode from nozzle_mode)
        cond_open = OperatingConditions(rpm=n * 60, Va_ship=0.0, w=0, rho=1025, nu=1.19e-6,
                                        pv=2338, p_atm=101325, h=2, nozzle_mode="open")
        cond_19a = OperatingConditions(rpm=n * 60, Va_ship=0.0, w=0, rho=1025, nu=1.19e-6,
                                       pv=2338, p_atm=101325, h=2, nozzle_mode="19A")
        r_open = solve_performance(geom, cond_open, nozzle_selection=NozzleSelection("open"),
                                   hydro_config=ow)
        r_19a = solve_performance(geom, cond_19a, nozzle_selection=NozzleSelection("19A"),
                                  hydro_config=ow)
        aug = r_19a.T_total / r_open.T_total if r_open.T_total > 0 else 0.0
        # monotonicity + eta + cavitation across J
        prevT = None
        mono = True
        eta_ok = True
        maxcav = 0.0
        for J in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]:
            Va = J * n * D
            cond = OperatingConditions(rpm=n * 60, Va_ship=Va, w=0, rho=1025, nu=1.19e-6,
                                       pv=2338, p_atm=101325, h=0.3, nozzle_mode="19A")
            r = solve_performance(geom, cond, nozzle_selection=NozzleSelection("19A"), hydro_config=ow)
            if prevT is not None and r.T_total > prevT + 1e-6:
                mono = False
            prevT = r.T_total
            if r.eta_total >= 1.0:
                eta_ok = False
            maxcav = max(maxcav, r.Combined_Cavitation_Est_PCT)
        print(f"{os.path.basename(f):<14}{aug:>13.2f}{'yes' if eta_ok else 'NO':>7}"
              f"{'yes' if mono else 'NO':>12}{maxcav:>9.1f}")


if __name__ == "__main__":
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    b_glob = os.path.join(here, "B_hcpc", "B*.hcpc")
    ka_glob = os.path.join(here, "KA_HCPC", "KA*.hcpc")
    run_b_series_report(b_glob)
    first = sorted(glob.glob(b_glob))
    if first:
        print_detail(first[0])
    run_ducted_sanity(ka_glob)
