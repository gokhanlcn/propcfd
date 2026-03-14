import os, sys, math

project_dir = os.path.dirname(os.path.abspath('app.py'))
sys.path.append(project_dir)

from src.parser_hcpc import parse_hcpc_content
from src.models import OperatingConditions, ModelConstants, NozzleSelection
from src.solver import solve_performance

with open(os.path.join(os.path.dirname(project_dir), 'KA_HCPC', 'KA1.hcpc'), 'r') as f: 
    content = f.read()
    
geom = parse_hcpc_content(content, 'KA1.hcpc')
geom.diameter, geom.radius, geom.blade_count = 0.100, 0.050, 3
constants = ModelConstants()

modes = ['open', '19A', '37']
Js = [0.0, 0.2, 0.5, 0.8]

# 1. MACRO TABLE
print('\n' + '='*130)
print('          ARITHMETIC CONSISTENCY & FOM VALIDATION REPORT          ')
print('          Strict Identity: KT_total == KT_prop_with_nozzle + KTN  ')
print('='*130)

for J in Js:
    Va = J * (3000.0/60.0) * 0.100
    cond = OperatingConditions(rpm=3000.0, Va_ship=Va, w=0.0, rho=998.0, nu=1e-6, pv=2330.0, p_atm=101325.0, h=0.5)
    
    print(f'\n[ Advance Ratio J = {J:.1f} | Va = {Va:.2f} m/s ]')
    print(f"| {'Mode':<6} | {'KT_ope_ref':<10} | {'KT_prop(w)':<10} | {'KTN':<8} | {'KT_total':<9} | {'ChkSum':<8} | {'Err(1e-6)':<9} | {'KQ_ope_ref':<10} | {'KQ_prop(w)':<10} | {'KQ_total':<8} | {'Pshaft':<7} | {'FoM/ETA':<7} | {'Sheet':<5} | {'Tip':<5} | {'Comb':<4} |")
    print('-'*150)
    
    for mode in modes:
        ns = NozzleSelection(nozzle_id=mode, effectiveness=1.0)
        res = solve_performance(geom, cond, constants, ns)
        
        kt_ope = res.KT_open_reference
        kt_prop_noz = res.KT_prop_with_nozzle_flow
        kt_n = res.KTN
        kt_tot = res.KT_total
        kq_ope = res.KQ_open_reference
        kq_prop = res.KQ_prop_with_nozzle_flow
        kq_tot = res.KQ_total
        
        check_sum = kt_prop_noz + kt_n
        err = kt_tot - check_sum
        eta_fom = res.static_efficiency_est if J == 0.0 else res.eta_total
        
        warn_str = ""
        for w in res.warnings:
            if 'Guardrail' in w:
                warn_str = "(FoM Guardrail)"
                
        print(f"| {mode:<6} | {kt_ope:<10.4f} | {kt_prop_noz:<10.4f} | {kt_n:<8.4f} | {kt_tot:<9.4f} | {check_sum:<8.4f} | {err:<9.4f} | {kq_ope:<10.4f} | {kq_prop:<10.4f} | {kq_tot:<8.4f} | {res.Pshaft_total:<7.1f} | {eta_fom:<7.3f} | {res.Sheet_Cavitation_Est_PCT:<5.1f} | {res.Tip_Vortex_Cavitation_Est_PCT:<5.1f} | {res.Combined_Cavitation_Est_PCT:<4.1f} | {warn_str}")

# 2. SECTION TABLE
print('\n' + '='*130)
print('          SECTION LEVEL KINEMATICS & LOADING & CAVITATION          ')
print('='*130)

r_r_targets = [0.80, 0.90, 0.95, 0.975, 1.00]

for J in Js:
    Va = J * (3000.0/60.0) * 0.100
    cond = OperatingConditions(rpm=3000.0, Va_ship=Va, w=0.0, rho=998.0, nu=1e-6, pv=2330.0, p_atm=101325.0, h=0.5)
    print(f'\n[ Advance Ratio J = {J:.1f} | Va = {Va:.2f} m/s ]')
    print(f"| {'Mode':<6} | {'r/R':<5} | {'VaxBase':<7} | {'u_n':<6} | {'VaxTot':<7} | {'alpha':<6} | {'CL':<6} | {'CD':<6} | {'Gamma':<7} | {'dT':<6} | {'dQ':<6} | {'sigLoc':<6} | {'shtSev':<6} | {'tipSev':<6} |")
    print('-'*125)
    
    for mode in modes:
        ns = NozzleSelection(nozzle_id=mode, effectiveness=1.0)
        res = solve_performance(geom, cond, constants, ns)
        
        for tr in r_r_targets:
            # find closest section
            closest_sec = min(res.section_results, key=lambda s: abs(s.r_over_R - tr))
            vax_base = Va # (excluding vi approx for table clarity if needed, or we just print Va)
            # Actually we can calculate exactly: 
            vax_tot = Va + closest_sec.nozzle_u_local
            alpha_deg = math.degrees(closest_sec.alpha)
            
            print(f"| {mode:<6} | {closest_sec.r_over_R:<5.3f} | {Va:<7.3f} | {closest_sec.nozzle_u_local:<6.3f} | {vax_tot:<7.3f} | {alpha_deg:<6.2f} | {closest_sec.CL:<6.3f} | {closest_sec.CD:<6.3f} | {closest_sec.Gamma:<7.3f} | {closest_sec.dT:<6.1f} | {closest_sec.dQ:<6.3f} | {closest_sec.sigma_local:<6.2f} | {closest_sec.sheet_severity:<6.3f} | {closest_sec.tip_severity:<6.3f} |")

