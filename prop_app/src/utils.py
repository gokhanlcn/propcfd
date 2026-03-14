import pandas as pd
from typing import List
from .models import PerformanceResult

def export_section_table(res: PerformanceResult) -> pd.DataFrame:
    data = []
    for s in res.section_results:
        data.append({
            "r/R": s.r_over_R, "Chord[m]": s.chord, "Thickness[m]": s.thickness,
            "Pitch[m]": s.pitch, "Camber[m]": s.camber, "beta_i[rad]": s.beta_i,
            "alpha[rad]": s.alpha, "CL": s.CL, "CD": s.CD, "Gamma": s.Gamma,
            "dT[N]": s.dT, "dQ[Nm]": s.dQ, "Re": s.Re, "q_dyn": s.q_dyn,
            "sigma_local": s.sigma_local, "sigma_crit_sheet": s.sigma_crit_sheet, "sheet_severity": s.sheet_severity,
            "sigma_crit_tip": s.sigma_crit_tip, "tip_region": s.tip_region, "tip_severity": s.tip_severity,
            "tip_vortex_index_i": s.tip_vortex_index_i
        })
    return pd.DataFrame(data)

def generate_csv(df: pd.DataFrame) -> str:
    return df.to_csv(index=False)
