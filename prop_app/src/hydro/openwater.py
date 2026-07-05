"""Open-water blade-element momentum (BEMT) solver.

A physics-first rewrite of the loop that used to live in
``solver.run_bemt_loop``. The decisive correction is structural: the original
solved a *single global* axial induced velocity and ignored swirl entirely,
which over-predicts thrust by ~60% against the Wageningen B-series. This solver
instead solves, per blade annulus, both the axial induction factor ``a`` and the
tangential (swirl) induction factor ``a'`` from the local momentum balance --
the standard Glauert propeller BEMT.

Per annulus at radius r (solidity sigma = B*c / (2*pi*r), Prandtl loss F):

    phi   = atan2( Va(1+a) ,  Omega*r(1-a') )        inflow angle
    alpha = theta - phi                              angle of attack
    Cx    = CL cos(phi) - CD sin(phi)                axial force coeff
    Cy    = CL sin(phi) + CD cos(phi)                tangential force coeff
    a     = 1 / ( 4 F sin^2(phi) / (sigma Cx) - 1 )
    a'    = 1 / ( 4 F sin(phi)cos(phi) / (sigma Cy) + 1 )

Other physics corrections vs. the original:
  * Induced drag is not added as ``k*CL^2`` -- it emerges from resolving the
    tilted lift vector along the axis (the ``-CD sin(phi)`` etc. terms).
  * Profile drag uses an ITTC friction line with a thickness form factor, so
    model-scale low-Re (D=100 mm -> Re~1e5) is represented.
  * Section zero-lift angle from thin-aerofoil theory (alpha_0 = -k*f/c).

The duct solver reuses this by passing a uniform ``va_augment`` (duct-induced
axial inflow) and disabling the tip loss (the duct suppresses tip-vortex
roll-up); the duct *thrust* is added separately in ``ducted.py`` from momentum
theory, so nothing is double counted.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import List, Optional, Callable

from ..models import PropellerGeometry, OperatingConditions


@dataclass
class OpenWaterConstants:
    """Physically-motivated constants, globally calibrated to the B-series."""
    cl_slope: float = 2.0 * math.pi          # 2D lift-curve slope (thin aerofoil, 1/rad)
    cl_slope_efficiency: float = 0.50        # effective slope reduction (viscous decambering,
                                             # finite Re, blade cascade); calibrated to B-series
    zero_lift_camber_factor: float = 1.8     # alpha_0 = -k*(f/c); ~1.8 for marine mean lines
    cl_max: float = 1.30                     # static stall ceiling
    cl_max_camber_gain: float = 1.5          # cl_max grows mildly with camber
    form_drag_factor: float = 2.0            # (1 + k*t/c) thickness form factor
    cf_floor: float = 4.0e-3
    cf_ceiling: float = 4.0e-2


@dataclass
class SectionState:
    r_over_R: float
    r: float
    chord: float
    thickness: float
    pitch: float
    camber: float
    dr: float
    beta_geom: float        # blade pitch angle theta
    beta_i: float           # inflow angle phi
    alpha: float
    alpha_eff: float
    CL: float
    CD: float
    Gamma: float
    dT: float
    dQ: float
    Re: float
    q_dyn: float
    Vrel: float
    Vax_local: float
    a: float
    a_prime: float


@dataclass
class BemtResult:
    T: float
    Q: float
    sections: List[SectionState]
    warnings: List[str]


def _friction_coefficient(Re: float, c: OpenWaterConstants) -> float:
    """ITTC-1957 correlation line, clamped for model-scale Reynolds numbers."""
    Re = max(Re, 1.0e3)
    cf = 0.075 / (math.log10(Re) - 2.0) ** 2
    return min(max(cf, c.cf_floor), c.cf_ceiling)


def _section_cl_cd(alpha_eff: float, fc: float, tc: float, Re: float,
                   consts: OpenWaterConstants):
    slope = consts.cl_slope * consts.cl_slope_efficiency
    cl_lin = slope * alpha_eff
    cl_max = consts.cl_max + consts.cl_max_camber_gain * min(abs(fc), 0.08)
    CL = cl_max * math.tanh(cl_lin / cl_max) if cl_max > 1e-6 else 0.0
    cf = _friction_coefficient(Re, consts)
    CD = 2.0 * cf * (1.0 + consts.form_drag_factor * tc)
    return CL, CD, cl_max


def solve_bemt(geom: PropellerGeometry,
               cond: OperatingConditions,
               consts: OpenWaterConstants,
               va_augment: float = 0.0,
               va_augment_radial: Optional[Callable[[float], float]] = None,
               apply_tip_loss: bool = True,
               max_iter: int = 80,
               tol: float = 1e-6) -> BemtResult:
    """Glauert blade-element momentum solution with axial+swirl induction.

    ``va_augment`` is a uniform axial inflow increment (m/s) added to the
    free-stream advance velocity; the open-water solver leaves it at 0, the
    ducted momentum solver supplies the duct-induced inflow there.
    ``va_augment_radial(r_over_R) -> m/s`` optionally supplies a *radially
    varying* increment (e.g. the panel-method duct field u_a(r)); when given it
    overrides the uniform ``va_augment`` per section. Both default to no change,
    so existing callers are unaffected.
    """
    warnings: List[str] = []
    n = cond.rpm / 60.0
    omega = 2.0 * math.pi * n
    # Regularise the bollard / very-low-advance state: the a-factor momentum
    # form (Vax = Va*(1+a)) is singular at Va = 0, so floor the base advance to
    # a small fraction of the rev-speed*diameter (J ~ 0.03) before adding the
    # duct inflow. This keeps near-bollard cases finite without affecting J>=0.1.
    v_floor = 0.03 * n * geom.diameter
    Va_base = max(cond.Va_ship * (1.0 - cond.w), v_floor)

    R, Rh, B = geom.radius, geom.hub_radius, geom.blade_count
    rho, nu = cond.rho, cond.nu

    T_total = 0.0
    Q_total = 0.0
    sections: List[SectionState] = []

    for sec in geom.sections:
        if sec.r <= Rh + 1e-5 or sec.chord <= 0:
            continue
        r = sec.r
        Vt0 = omega * r
        theta = math.atan2(sec.pitch, 2.0 * math.pi * r) if r > 0 else 0.0
        tc = sec.thickness / sec.chord if sec.chord > 0 else 0.0
        fc = sec.camber / sec.chord if sec.chord > 0 else 0.0
        alpha_0 = -consts.zero_lift_camber_factor * fc
        sigma = B * sec.chord / (2.0 * math.pi * r)

        # Per-section axial inflow: uniform duct augmentation, or a radially
        # varying field (e.g. the panel-method u_a(r)) when supplied.
        if va_augment_radial is not None:
            Va = Va_base + va_augment_radial(sec.r_over_R)
        else:
            Va = Va_base + va_augment

        # Axial induction is solved as an ABSOLUTE velocity v_i (not the ratio
        # a = v_i/Va), so the static / bollard case Va -> 0 stays finite:
        #   (Va + v_i) * v_i = Vrel^2 * sigma * Cx / (4 F)   (annulus momentum)
        # At Va = 0 this gives v_i = Vrel*sqrt(sigma*Cx/(4F)) (the static
        # actuator-annulus slipstream), so torque and figure of merit stay
        # physical. At high advance it reduces to the usual a = v_i/Va form.
        v_i = 0.15 * Vt0
        ap = 0.01
        CL = CD = Vrel = phi = alpha = alpha_eff = 0.0
        for _ in range(max_iter):
            Vax = Va + v_i
            Vtan = max(Vt0 * (1.0 - ap), 1e-6)
            phi = math.atan2(Vax, Vtan)
            sin_phi = max(math.sin(phi), 1e-3)
            cos_phi = math.cos(phi)
            Vrel = math.hypot(Vax, Vtan)

            alpha = theta - phi
            alpha_eff = alpha - alpha_0
            Re = Vrel * sec.chord / nu if nu > 0 else 1e6
            CL, CD, _ = _section_cl_cd(alpha_eff, fc, tc, Re, consts)

            # Prandtl tip + hub loss.
            if apply_tip_loss:
                ftip = (B / 2.0) * (R - r) / (r * sin_phi)
                Ftip = (2.0 / math.pi) * math.acos(min(math.exp(-ftip), 1.0)) if ftip > 0 else 1.0
            else:
                Ftip = 1.0
            fhub = (B / 2.0) * (r - Rh) / (r * sin_phi)
            Fhub = (2.0 / math.pi) * math.acos(min(math.exp(-fhub), 1.0)) if fhub > 0 else 1.0
            F = max(Ftip * Fhub, 1e-3)

            Cx = CL * cos_phi - CD * sin_phi
            Cy = CL * sin_phi + CD * cos_phi

            # Axial: solve the quadratic (Va + v_i) v_i = Vrel^2 sigma Cx/(4F).
            rhs = Vrel * Vrel * sigma * Cx / (4.0 * F)
            disc = Va * Va + 4.0 * rhs
            if disc > 0 and Cx > 0:
                v_i_new = 0.5 * (-Va + math.sqrt(disc))
            else:
                v_i_new = 0.0
            # Swirl: a' = Vrel^2 sigma Cy / (4 r (Va+v_i) Omega F).
            denom_ap = 4.0 * r * max(Va + v_i, 1e-6) * omega * F
            ap_new = (Vrel * Vrel * sigma * Cy / denom_ap) if (Cy > 1e-6 and denom_ap > 0) else 0.0

            v_i_new = min(max(v_i_new, -0.5 * Va), 3.0 * Vt0)
            ap_new = min(max(ap_new, 0.0), 0.9)
            dchg = abs(v_i_new - v_i) / max(Vt0, 1e-6) + abs(ap_new - ap)
            v_i = 0.6 * v_i + 0.4 * v_i_new
            ap = 0.6 * ap + 0.4 * ap_new
            if dchg < tol:
                break

        a = v_i / Va if Va > 1e-3 else 0.0
        # Final element loads at converged induction.
        Vax = Va + v_i
        Vtan = max(Vt0 * (1.0 - ap), 1e-6)
        phi = math.atan2(Vax, Vtan)
        Vrel = math.hypot(Vax, Vtan)
        q = 0.5 * rho * Vrel ** 2
        dL = q * sec.chord * CL * sec.dr
        dD = q * sec.chord * CD * sec.dr
        dT = B * (dL * math.cos(phi) - dD * math.sin(phi))
        dFt = B * (dL * math.sin(phi) + dD * math.cos(phi))
        dQ = dFt * r
        T_total += dT
        Q_total += dQ

        sections.append(SectionState(
            r_over_R=sec.r_over_R, r=r, chord=sec.chord, thickness=sec.thickness,
            pitch=sec.pitch, camber=sec.camber, dr=sec.dr,
            beta_geom=theta, beta_i=phi, alpha=alpha, alpha_eff=alpha_eff,
            CL=CL, CD=CD, Gamma=0.5 * Vrel * sec.chord * CL, dT=dT, dQ=dQ,
            Re=Vrel * sec.chord / nu if nu > 0 else 1e6, q_dyn=q,
            Vrel=Vrel, Vax_local=Vax, a=a, a_prime=ap,
        ))

    if T_total <= 0:
        warnings.append("Net blade thrust <= 0 (windmilling / very high advance ratio).")
    return BemtResult(T=T_total, Q=Q_total, sections=sections, warnings=warnings)
