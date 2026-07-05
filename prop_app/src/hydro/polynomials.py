"""Validated open-water polynomial models from the literature.

These are the *ground truth* for the example geometries shipped with the app:
  - ``B_hcpc/B*.hcpc`` are Wageningen B-series propellers  -> use B-series KT/KQ.
  - ``KA_HCPC/KA*.hcpc`` are Ka-series ducted propellers   -> use Ka + 19A/37 KT/KTN/KQ.

Each polynomial has the regression form

    value = sum_n  C_n * J^s_n * (P/D)^t_n * (AE/AO)^u_n * Z^v_n

Sources:
  - Oosterveld, M.W.C. & van Oossanen, P. (1975), "Further Computer-Analyzed
    Data of the Wageningen B-Screw Series", ISP 22(251).
  - Oosterveld, M.W.C. (1970), "Wake Adapted Ducted Propellers", NSMB Pub. 345.
  - Carlton, J. (2018), "Marine Propellers and Propulsion", 4th ed., Ch. 6.

NOTE ON VALIDITY: The B-series regression is strictly valid for
Z = 2..7, AE/AO = 0.30..1.05, P/D = 0.5..1.4 and is referenced to a blade
Reynolds number of 2e6 (see ``b_series_reynolds_correction`` for scale effects).
"""
from __future__ import annotations
from typing import List, Tuple

# A polynomial term is (C, s, t, u, v) -> C * J^s * (P/D)^t * (AE/AO)^u * Z^v
PolyTerm = Tuple[float, int, int, int, int]


def evaluate_polynomial(coeffs: List[PolyTerm], J: float, PD: float,
                        AE_AO: float, Z: int) -> float:
    """Evaluate a Wageningen/Oosterveld-type regression polynomial."""
    total = 0.0
    for C, s, t, u, v in coeffs:
        total += C * (J ** s) * (PD ** t) * (AE_AO ** u) * (float(Z) ** v)
    return total


# ---------------------------------------------------------------------------
# WAGENINGEN B-SERIES  (Oosterveld & van Oossanen, 1975)
# KT : 39 terms, KQ : 47 terms.  KT and KQ are dimensionless (not 10*KQ).
# ---------------------------------------------------------------------------
WAGENINGEN_B_KT: List[PolyTerm] = [
    (+0.00880496, 0, 0, 0, 0),
    (-0.204554,   1, 0, 0, 0),
    (+0.166351,   0, 1, 0, 0),
    (+0.158114,   0, 2, 0, 0),
    (-0.147581,   2, 0, 1, 0),
    (-0.481497,   1, 1, 1, 0),
    (+0.415437,   0, 2, 1, 0),
    (+0.0144043,  0, 0, 0, 1),
    (-0.0530054,  2, 0, 0, 1),
    (+0.0143481,  0, 1, 0, 1),
    (+0.0606826,  1, 1, 0, 1),
    (-0.0125894,  0, 0, 1, 1),
    (+0.0109689,  1, 0, 1, 1),
    (-0.133698,   0, 3, 0, 0),
    (+0.00638407, 0, 6, 0, 0),
    (-0.00132718, 2, 6, 0, 0),
    (+0.168496,   3, 0, 1, 0),
    (-0.0507214,  0, 0, 2, 0),
    (+0.0854559,  2, 0, 2, 0),
    (-0.0504475,  3, 0, 2, 0),
    (+0.010465,   1, 6, 2, 0),
    (-0.00648272, 2, 6, 2, 0),
    (-0.00841728, 0, 3, 0, 1),
    (+0.0168424,  1, 3, 0, 1),
    (-0.00102296, 3, 3, 0, 1),
    (-0.0317791,  0, 3, 1, 1),
    (+0.018604,   1, 0, 2, 1),
    (-0.00410798, 0, 2, 2, 1),
    (-0.000606848, 0, 0, 0, 2),
    (-0.0049819,  1, 0, 0, 2),
    (+0.0025983,  2, 0, 0, 2),
    (-0.000560528, 3, 0, 0, 2),
    (-0.00163652, 1, 2, 0, 2),
    (-0.000328787, 1, 6, 0, 2),
    (+0.000116502, 2, 6, 0, 2),
    (+0.000690904, 0, 0, 1, 2),
    (+0.00421749, 0, 3, 1, 2),
    (+0.0000565229, 3, 6, 1, 2),
    (-0.00146564, 0, 3, 2, 2),
]

WAGENINGEN_B_KQ: List[PolyTerm] = [
    (+0.00379368, 0, 0, 0, 0),
    (+0.00886523, 2, 0, 0, 0),
    (-0.032241,   1, 1, 0, 0),
    (+0.00344778, 0, 2, 0, 0),
    (-0.0408811,  0, 1, 1, 0),
    (-0.108009,   1, 1, 1, 0),
    (-0.0885381,  2, 1, 1, 0),
    (+0.188561,   0, 2, 1, 0),
    (-0.00370871, 1, 0, 0, 1),
    (+0.00513696, 0, 1, 0, 1),
    (+0.0209449,  1, 1, 0, 1),
    (+0.00474319, 2, 1, 0, 1),
    (-0.00723408, 2, 0, 1, 1),
    (+0.00438388, 1, 1, 1, 1),
    (-0.0269403,  0, 2, 1, 1),
    (+0.0558082,  3, 0, 1, 0),
    (+0.0161886,  0, 3, 1, 0),
    (+0.00318086, 1, 3, 1, 0),
    (+0.015896,   0, 0, 2, 0),
    (+0.0471729,  1, 0, 2, 0),
    (+0.0196283,  3, 0, 2, 0),
    (-0.0502782,  0, 1, 2, 0),
    (-0.030055,   3, 1, 2, 0),
    (+0.0417122,  2, 2, 2, 0),
    (-0.0397722,  0, 3, 2, 0),
    (-0.00350024, 0, 6, 2, 0),
    (-0.0106854,  3, 0, 0, 1),
    (+0.00110903, 3, 3, 0, 1),
    (-0.000313912, 0, 6, 0, 1),
    (+0.0035985,  3, 0, 1, 1),
    (-0.00142121, 0, 6, 1, 1),
    (-0.00383637, 1, 0, 2, 1),
    (+0.0126803,  0, 2, 2, 1),
    (-0.00318278, 2, 3, 2, 1),
    (+0.00334268, 0, 6, 2, 1),
    (-0.00183491, 1, 1, 0, 2),
    (+0.000112451, 3, 2, 0, 2),
    (-0.0000297228, 3, 6, 0, 2),
    (+0.000269551, 1, 0, 1, 2),
    (+0.00083265, 2, 0, 1, 2),
    (+0.00155334, 0, 2, 1, 2),
    (+0.000302683, 0, 6, 1, 2),
    (-0.0001843,  0, 0, 2, 2),
    (-0.000425399, 0, 3, 2, 2),
    (+0.0000869243, 3, 3, 2, 2),
    (-0.0004659,  0, 6, 2, 2),
    (+0.0000554194, 1, 6, 2, 2),
]


def wageningen_b_kt(J: float, PD: float, AE_AO: float, Z: int) -> float:
    return evaluate_polynomial(WAGENINGEN_B_KT, J, PD, AE_AO, Z)


def wageningen_b_kq(J: float, PD: float, AE_AO: float, Z: int) -> float:
    """Returns KQ (NOT 10*KQ)."""
    return evaluate_polynomial(WAGENINGEN_B_KQ, J, PD, AE_AO, Z)


def b_series_reynolds_correction(J: float, PD: float, AE_AO: float, Z: int,
                                 Re: float) -> Tuple[float, float]:
    """Wageningen B Reynolds correction (Oosterveld & van Oossanen, 1975).

    Returns (dKT, dKQ) to be ADDED to the Re=2e6 baseline KT, KQ.
    Valid for Re > 2e6; below that the series does not formally extend, so we
    clamp to the 2e6 reference (dKT = dKQ = 0) and let the caller warn.
    """
    if Re <= 2.0e6:
        return 0.0, 0.0
    import math
    logRe = math.log10(Re) - 0.301  # log10(Re/2e6)

    dKT = (
        + 0.000353485
        - 0.00333758 * AE_AO * J ** 2
        - 0.00478125 * AE_AO * PD * J
        + 0.000257792 * logRe ** 2 * AE_AO * J ** 2
        + 0.0000643192 * logRe * PD ** 6 * J ** 2
        - 0.0000110636 * logRe ** 2 * PD ** 6 * J ** 2
        - 0.0000276305 * logRe ** 2 * Z * AE_AO * J ** 2
        + 0.0000954 * logRe * Z * AE_AO * PD * J
        + 0.0000032049 * logRe * Z ** 2 * AE_AO * PD ** 3 * J
    ) * logRe

    dKQ = (
        - 0.000591412
        + 0.00696898 * PD
        - 0.0000666654 * Z * PD ** 6
        + 0.0160818 * AE_AO ** 2
        - 0.000938091 * logRe * PD
        - 0.00059593 * logRe * PD ** 2
        + 0.0000782099 * logRe ** 2 * PD ** 2
        + 0.0000052199 * logRe * Z * AE_AO * J ** 2
        - 0.00000088528 * logRe ** 2 * Z * AE_AO * PD * J
        + 0.0000230171 * logRe * Z * PD ** 6
        - 0.00000184341 * logRe ** 2 * Z * PD ** 6
        - 0.00400252 * logRe * AE_AO ** 2
        + 0.000220915 * logRe ** 2 * AE_AO ** 2
    ) * logRe

    return dKT, dKQ


# ---------------------------------------------------------------------------
# KA-SERIES DUCTED PROPELLERS  (Oosterveld, 1970) -- INTENTIONALLY OMITTED
# ---------------------------------------------------------------------------
# The Ka 4-70 / Nozzle 19A & 37 KTP/KTN/KQ regression coefficients are NOT
# embedded here. The values previously shipped in src/nozzle_library.py, and
# every coefficient set we could recall or locate in open sources, evaluate to
# physically impossible curves (negative propeller/duct thrust over the whole J
# range) -- i.e. they are corrupt. Rather than ship fabricated numbers, the
# ducted model in ``ducted.py`` is built from first-principles ducted
# actuator-disk + ring-wing momentum theory, which needs no Ka regression.
#
# If a verified Oosterveld (1970) / Carlton Table 6.18 coefficient set becomes
# available, add it here and wire a polynomial cross-check into validation.py.
