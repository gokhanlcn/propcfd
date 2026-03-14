from .models import NozzleParams

def apply_empirical_nozzle(KT_open: float, KQ_open: float, J: float, nozzle: NozzleParams):
    dKT = nozzle.dKT_a0 + nozzle.dKT_a1 * J + nozzle.dKT_a2 * J**2
    dKQ = nozzle.dKQ_b0 + nozzle.dKQ_b1 * J + nozzle.dKQ_b2 * J**2
    return KT_open + dKT, KQ_open + dKQ
