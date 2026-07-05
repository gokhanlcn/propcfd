import pandas as pd
import itertools
from typing import List, Optional
from .models import PropellerGeometry, OperatingConditions, NozzleSelection
from .solver import solve_performance
from .hydro.openwater import OpenWaterConstants
from .hydro.cavitation import CavitationConstants


def run_batch_analysis(geometries: List[PropellerGeometry], rpms: List[float], speeds: List[float],
                       modes: List[str], base_cond: OperatingConditions,
                       ow_consts: Optional[OpenWaterConstants] = None,
                       cav_consts: Optional[CavitationConstants] = None,
                       nozzle_eff: float = 1.0) -> pd.DataFrame:
    ow_consts = ow_consts or OpenWaterConstants()
    cav_consts = cav_consts or CavitationConstants()
    rows = []
    for geom, rpm, speed, mode in itertools.product(geometries, rpms, speeds, modes):
        c = OperatingConditions(rpm=rpm, Va_ship=speed, w=base_cond.w, rho=base_cond.rho,
                                nu=base_cond.nu, pv=base_cond.pv, p_atm=base_cond.p_atm,
                                h=base_cond.h, nozzle_mode=mode)
        ns = NozzleSelection(nozzle_id=mode, effectiveness=nozzle_eff)
        res = solve_performance(geom, c, nozzle_selection=ns, hydro_config=ow_consts,
                                cav_config=cav_consts, series_hint=geom.file_name)
        rows.append({
            "Prop_ID": geom.propeller_id, "File": geom.file_name, "Mode": mode,
            "RPM": rpm, "Va_ship": speed, "D": geom.diameter, "B": geom.blade_count, "EAR": geom.expanded_area_ratio,
            "J": res.J, "Thrust_N": res.T_total, "Torque_Nm": res.Q_total, "Power_W": res.Pshaft_total,
            "KT": res.KT_total, "KQ": res.KQ_total, "KT_ref_poly": res.KT_reference_poly,
            "Eta_prop": res.eta_total, "Duct_Thrust_N": res.T_duct, "Duct_Share": res.duct_thrust_share,
            "Static_Efficiency": res.static_efficiency_est, "Thrust_Per_Power_N_per_W": res.thrust_per_power_N_per_W,
            "Sheet_Cavitation_PCT": res.Sheet_Cavitation_Est_PCT,
            "Tip_Vortex_Cavitation_PCT": res.Tip_Vortex_Cavitation_Est_PCT,
            "Combined_Cavitation_PCT": res.Combined_Cavitation_Est_PCT,
            "Burrill_Back_Cavitation_PCT": res.Burrill_Back_Cavitation_PCT,
            "Method": res.method, "Warnings": " | ".join(res.warnings)
        })
    return pd.DataFrame(rows)
