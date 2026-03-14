import pandas as pd
import itertools
from typing import List
from .models import PropellerGeometry, OperatingConditions, ModelConstants, NozzleSelection
from .solver import solve_performance

def run_batch_analysis(geometries: List[PropellerGeometry], rpms: List[float], speeds: List[float], 
                       modes: List[str], base_cond: OperatingConditions, 
                       constants: ModelConstants, nozzle_eff: float = 1.0) -> pd.DataFrame:
    rows = []
    for geom, rpm, speed, mode in itertools.product(geometries, rpms, speeds, modes):
        c = OperatingConditions(rpm=rpm, Va_ship=speed, w=base_cond.w, rho=base_cond.rho, 
                                nu=base_cond.nu, pv=base_cond.pv, p_atm=base_cond.p_atm, 
                                h=base_cond.h, nozzle_mode=mode)
        ns = NozzleSelection(nozzle_id=mode, effectiveness=nozzle_eff)
        res = solve_performance(geom, c, constants, ns)
        rows.append({
            "Prop_ID": geom.propeller_id, "File": geom.file_name, "Mode": mode,
            "RPM": rpm, "Va_ship": speed, "D": geom.diameter, "B": geom.blade_count, "EAR": geom.expanded_area_ratio,
            "J": res.J, "Thrust_N": res.T_total, "Torque_Nm": res.Q_total, "Power_W": res.Pshaft_total,
            "KT": res.KT_total, "KQ": res.KQ_total, "Eta_prop": res.eta_total,
            "Static_Efficiency": res.static_efficiency_est, "Thrust_Per_Power_N_per_W": res.thrust_per_power_N_per_W,
            "Sheet_Cavitation_PCT": res.Sheet_Cavitation_Est_PCT, 
            "Tip_Vortex_Cavitation_PCT": res.Tip_Vortex_Cavitation_Est_PCT,
            "Combined_Cavitation_PCT": res.Combined_Cavitation_Est_PCT,
            "Tip_Vortex_Cav_Index": res.Tip_Vortex_Cav_Index, 
            "Warnings": " | ".join(res.warnings)
        })
    return pd.DataFrame(rows)
