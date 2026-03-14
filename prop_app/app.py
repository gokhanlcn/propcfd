import streamlit as st
import pandas as pd
from src.parser_hcpc import parse_hcpc_content
from src.models import OperatingConditions, ModelConstants, NozzleSelection
from src.solver import solve_performance
from src.utils import export_section_table, generate_csv
from src.batch import run_batch_analysis
from src.plots import plot_performance_curves
from src.nozzle_library import get_nozzle_geometry
from src.nozzle_geometry import generate_scaled_nozzle
from src.nozzle_render import plot_nozzle_2d, plot_nozzle_3d, plot_prop_nozzle_combined

import os

st.set_page_config(page_title="GkhnCFD", page_icon="🚢", layout="wide")

logo_path = os.path.join("assets", "aimlab_logo.png")
if os.path.exists(logo_path):
    st.logo(logo_path, link=None, icon_image=None)
else:
    st.logo("https://img.shields.io/badge/AIMLAB-gray?style=for-the-badge", link=None)

st.title("GkhnCFD")

if os.path.exists(logo_path):
    st.logo(logo_path, link=None, icon_image=None)
else:
    st.logo("https://img.shields.io/badge/AIMLAB-gray?style=for-the-badge", link=None)

# Ana Başlık
st.title("GkhnCFD")

# Initialize session state configuration
if 'constants' not in st.session_state:
    st.session_state.constants = ModelConstants()

tab_single, tab_batch, tab_geometry, tab_settings = st.tabs([
    "Single Analysis", "Batch Analysis", "Geometry Inspector", "Settings / Constants"
])

with st.sidebar:
    st.markdown("---")
    
    st.header("Fluid Properties")
    rho = st.number_input("Fluid density (rho) [kg/m^3]", value=1025.0)
    nu = st.number_input("Kinematic viscosity (nu) [m^2/s]", value=1.19e-6, format="%.2e")
    pv = st.number_input("Vapor pressure (pv) [Pa]", value=2338.0)
    p_atm = st.number_input("Ambient pressure (p_atm) [Pa]", value=101325.0)
    h = st.number_input("Submergence depth (h) [m]", value=2.0)
    w = st.number_input("Wake factor (w)", value=0.0)
    
    st.header("Advanced Nozzle Overrides")
    nozzle_effectiveness = st.number_input("Effectiveness Multiplier", value=1.0, min_value=0.0, max_value=2.0, help="Scales non-dimensional hydrodynamic contributions 0-1+")
    tip_clearance_mm_override = st.number_input(
        "Tip Clearance [mm]", 
        value=0.825, 
        min_value=0.0, 
        step=0.001, 
        format="%.3f", 
        help="Radial clearance between propeller tip and inner nozzle surface, entered in millimeters. 0.0 to use standard scaled ratio."
    )
    if tip_clearance_mm_override <= 0.0:
        tip_clearance_m_override = None
    else:
        tip_clearance_m_override = tip_clearance_mm_override / 1000.0

with tab_single:
    upload_single = st.file_uploader("Upload Single .hcpc File", type=['hcpc'], key="single_ul")
    col1, col2 = st.columns(2)
    rpm_sin = col1.number_input("RPM", value=1000.0)
    va_sin = col2.number_input("Ship Speed (m/s)", value=10.0)
    op_mode = st.selectbox("Operation Mode", ["open", "19A", "37", "All Comparer"])
    
    if upload_single and st.button("Run Single Analysis"):
        geom = parse_hcpc_content(upload_single.getvalue().decode("utf-8", errors="replace"), upload_single.name)
        cond = OperatingConditions(rpm=rpm_sin, Va_ship=va_sin, w=w, rho=rho, nu=nu, pv=pv, p_atm=p_atm, h=h, nozzle_mode=op_mode)
        
        modes_to_run = ["open", "19A", "37"] if op_mode == "All Comparer" else [op_mode]
        res_list = []
        for m in modes_to_run:
            cond.nozzle_mode = m
            ns = NozzleSelection(nozzle_id=m, effectiveness=nozzle_effectiveness, tip_clearance_m_override=tip_clearance_m_override)
            res_list.append(solve_performance(geom, cond, st.session_state.constants, ns))
        
        st.subheader(f"Parsed Propeller: {geom.diameter:.3f}m Diameter, {geom.blade_count} Blades")
        if geom.description:
            st.info(f"**Description:** {geom.description}")
        
        df_comp = pd.DataFrame([{
            "Mode": r.conditions.nozzle_mode, "J": r.J, "Thrust [N]": r.T_total, 
            "Total Torque [Nm]": r.Q_total, "Shaft Power [W]": r.Pshaft_total, "eta": r.eta_total, 
            "Static Efficiency (Approx.)": r.static_efficiency_est,
            "Thrust per Power [N/W]": r.thrust_per_power_N_per_W,
            "Sheet Cavitation Est [%]": r.Sheet_Cavitation_Est_PCT,
            "Tip Vortex Cav. Est [%]": r.Tip_Vortex_Cavitation_Est_PCT,
            "Combined Cavitation Est [%]": r.Combined_Cavitation_Est_PCT,
            "Tip Vortex Cav. Index": r.Tip_Vortex_Cav_Index
        } for r in res_list])
        st.dataframe(df_comp)
        
        st.subheader("Section Metrics (First Mode)")
        df_sec = export_section_table(res_list[0])
        st.dataframe(df_sec)

with tab_batch:
    files = st.file_uploader("Upload Multiple .hcpc Files", type=["hcpc"], accept_multiple_files=True)
    c1, c2 = st.columns(2)
    rpm_txt = c1.text_input("RPM List (comma separated)", "1000, 1500, 2000")
    speed_txt = c2.text_input("Speed List [m/s] (comma separated)", "5, 10, 15")
    batch_modes = st.multiselect("Modes to output", ["open", "19A", "37"], default=["open"])
    
    if files and st.button("Run Batch"):
        rpms = [float(x.strip()) for x in rpm_txt.split(",") if x.strip()]
        speeds = [float(x.strip()) for x in speed_txt.split(",") if x.strip()]
        geoms = [parse_hcpc_content(f.getvalue().decode("utf-8", errors="replace"), f.name) for f in files]
        b_cond = OperatingConditions(rpm=0, Va_ship=0, w=w, rho=rho, nu=nu, pv=pv, p_atm=p_atm, h=h)
        
        df_batch = run_batch_analysis(geoms, rpms, speeds, batch_modes, b_cond, st.session_state.constants, nozzle_effectiveness)
        st.dataframe(df_batch)
        
        csv_data = generate_csv(df_batch)
        st.download_button("Download CSV", data=csv_data, file_name="batch_results.csv", mime="text/csv")
        
        if len(df_batch) > 1:
            df_plot = df_batch.rename(columns={"Thrust_N": "Thrust[N]", "Power_W": "Power[W]", "Combined_Cavitation_PCT": "Cavitation[%]"})
            f1, f2, f3 = plot_performance_curves(df_plot)
            st.plotly_chart(f1)
            st.plotly_chart(f2)
            st.plotly_chart(f3)

with tab_geometry:
    st.header("Geometry Inspector & Nozzle Preview")
    
    if 'upload_single' in locals() and upload_single:
        g = parse_hcpc_content(upload_single.getvalue().decode("utf-8", errors="replace"), upload_single.name)
        
        col_g1, col_g2 = st.columns([1, 2])
        col_g1.subheader("Blade Sections")
        df_g = pd.DataFrame([{"r/R": s.r_over_R, "Chord": s.chord, "Pitch": s.pitch, "Camber": s.camber} for s in g.sections])
        col_g1.dataframe(df_g)
        
        preview_nozzle_id = col_g1.selectbox("Preview Duct Geometry", ["open", "19A", "37"], index=1)
        
        if preview_nozzle_id != "open":
            ndef = get_nozzle_geometry(preview_nozzle_id)
            nz_geom = generate_scaled_nozzle(g, ndef, clearance_m_override=tip_clearance_m_override)
            
            # Diagnostic and Warning Block
            clearance_at_prop_plane_mm = nz_geom.clearance_prop_plane * 1000.0
            min_clearance_mm = nz_geom.min_clearance * 1000.0
            
            if nz_geom.clearance_prop_plane <= 0:
                st.error(f"Collision Warning: Propeller tip breaches the duct wall at rotation plane! (Clearance = {clearance_at_prop_plane_mm:.3f} mm)")
            elif nz_geom.min_clearance <= 0:
                st.warning(f"Geometry Warning: Propeller clears at rotation plane, but clashes at duct minimum radius! (Min Clearance = {min_clearance_mm:.3f} mm)")
            elif nz_geom.x_prop_plane < nz_geom.x_start or nz_geom.x_prop_plane > nz_geom.x_end:
                st.warning(f"Placement Warning: Propeller rotation plane (X={nz_geom.x_prop_plane}) is outside the duct bounds [{nz_geom.x_start:.3f}, {nz_geom.x_end:.3f}]!")
            
            if clearance_at_prop_plane_mm > 5.0 and nz_geom.D < 0.2:
                st.warning(f"Unusually large clearance ({clearance_at_prop_plane_mm:.3f} mm) for this small propeller diameter ({nz_geom.D * 1000.0:.3f} mm).")
            if nz_geom.min_r_inner > 0.2 and nz_geom.D < 0.2:
                st.warning("Scaling Warning: nozzle inner radius > 0.2 m found for small propeller.")
            
            st.subheader("2D Meridional Cross-Section")
            st.plotly_chart(plot_nozzle_2d(nz_geom, g), use_container_width=True)
            
            st.subheader("3D Integrated Preview")
            st.plotly_chart(plot_prop_nozzle_combined(g, nz_geom), use_container_width=True)
            
            with st.expander("Geometry & Dimensional Notes", expanded=True):
                st.write(f"**nozzle type:** {ndef.display_name}")
                st.write(f"**prop diameter [mm]:** {g.diameter * 1000.0:.3f}")
                st.write(f"**prop radius [mm]:** {g.radius * 1000.0:.3f}")
                st.write(f"**hub radius [mm]:** {g.hub_radius * 1000.0:.3f}")
                st.write(f"**tip clearance input [mm]:** {tip_clearance_mm_override}")
                st.write(f"**tip clearance internal [m]:** {nz_geom.clearance}")
                st.write(f"**nozzle length [mm]:** {nz_geom.L * 1000.0:.3f}")
                st.write(f"**nozzle inner radius at prop plane [mm]:** {(nz_geom.clearance_prop_plane + g.radius) * 1000.0:.3f}")
                st.write(f"**clearance at prop plane [mm]:** {clearance_at_prop_plane_mm:.3f}")
                st.write(f"**minimum inner radius [mm]:** {nz_geom.min_r_inner * 1000.0:.3f}")
                st.write(f"**Source:** {ndef.profile_source}")
                st.write(f"**Notes:** {ndef.profile_notes}")
        else:
            st.info("Select a nozzle type (19A, 37) to render the duct geometry.")

with tab_settings:
    st.header("Physics Constants Override")
    c = st.session_state.constants
    c.suction_factor_k = st.number_input("Suction Filter K", value=c.suction_factor_k)
    
    st.markdown("### Sheet Cavitation Calibration")
    s1, s2 = st.columns(2)
    c.sheet_sigma_a0 = s1.number_input("Sheet A0 (Base)", value=c.sheet_sigma_a0)
    c.sheet_sigma_a1_cl = s2.number_input("Sheet A1 (CL)", value=c.sheet_sigma_a1_cl)
    c.sheet_sigma_a3_tc = s1.number_input("Sheet A3 (t/c inv)", value=c.sheet_sigma_a3_tc)
    c.sheet_sigma_a2_alpha = s2.number_input("Sheet A2 (Alpha)", value=c.sheet_sigma_a2_alpha)
    c.sheet_softening_exp = s1.number_input("Sheet Softening Exp", value=c.sheet_softening_exp)
    
    st.markdown("### Tip Vortex Calibration")
    cc1, cc2 = st.columns(2)
    c.tip_sigma_b0 = cc1.number_input("Tip B0 (Base)", value=c.tip_sigma_b0)
    c.tip_sigma_b1_gamma = cc2.number_input("Tip B1 (Gamma)", value=c.tip_sigma_b1_gamma)
    c.tip_sigma_b2_dgamma = cc1.number_input("Tip B2 (dGamma/dr)", value=c.tip_sigma_b2_dgamma)
    c.tip_sigma_b3_tip_factor = cc2.number_input("Tip B3 (Region Bonus)", value=c.tip_sigma_b3_tip_factor)
    c.tip_start_rR = cc1.number_input("Tip Setup r/R Start", value=c.tip_start_rR)
    c.tip_end_rR = cc2.number_input("Tip Setup r/R End", value=c.tip_end_rR)
    c.nozzle_tip_vortex_suppression = st.number_input("Nozzle Tip Suppression", value=c.nozzle_tip_vortex_suppression)
    
    st.markdown("### Combined Setup")
    c.lambda_tip = st.number_input("Lambda Tip (Weight in Combined)", value=c.lambda_tip)
    
    st.markdown("### Aerodynamics")
    c.cl_max_base = st.number_input("CL Max Base", value=c.cl_max_base)
    c.k_induced = st.number_input("K Induced Drag", value=c.k_induced, format="%.3f")
