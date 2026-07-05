import streamlit as st
import pandas as pd
import re
import io
from src.parser_hcpc import parse_hcpc_content
from src.models import OperatingConditions, ModelConstants, NozzleSelection
from src.solver import solve_performance, solve_bidirectional
from src.hydro.openwater import OpenWaterConstants
from src.hydro.cavitation import CavitationConstants
from src.hydro.duct_bem import solve_duct_bem_cavitation
import plotly.graph_objects as go
from src.utils import export_section_table, generate_csv
from src.batch import run_batch_analysis
from src.plots import plot_performance_curves, plot_section_metrics
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

# Initialize session state configuration
if 'ow_consts' not in st.session_state:
    st.session_state.ow_consts = OpenWaterConstants()
if 'cav_consts' not in st.session_state:
    st.session_state.cav_consts = CavitationConstants()

if 'saved_results' not in st.session_state:
    st.session_state.saved_results = []

if 'current_res' not in st.session_state:
    st.session_state.current_res = None

if 'current_geom' not in st.session_state:
    st.session_state.current_geom = None

if 'test_results' not in st.session_state:
    st.session_state.test_results = []
if 'test_current' not in st.session_state:
    st.session_state.test_current = None


def _extract_ka_pitch(geom):
    """Real EAR, pitch [mm] and P/D from the PARSED GEOMETRY (authoritative).

    The .hcpc 'description' text is NOT used: in the bundled KA files it is a
    copy-paste error (every file tags '0.8pitch', and KA7-9 tag '0.75ka' while
    their real EAR is 0.50). The geometry (ExpAreaRatio, section pitch) is
    correct, so we read from there.
    """
    ka = geom.expanded_area_ratio
    pitch_mm = pd = None
    if geom.sections and geom.diameter > 0:
        s07 = min(geom.sections, key=lambda s: abs(s.r_over_R - 0.7))
        pitch_mm = s07.pitch * 1000.0
        pd = s07.pitch / geom.diameter
    return ka, pitch_mm, pd

tab_single, tab_batch, tab_test, tab_geometry, tab_saved, tab_settings = st.tabs([
    "Single Analysis", "Batch Analysis", "Test Scenario", "Geometry Inspector", "Saved Data", "Settings / Constants"
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
    nozzle_effectiveness = st.number_input(
        "Nozzle Effectiveness", value=1.0, min_value=0.0, max_value=1.2, step=0.05,
        help="Fraction of the documented duct augmentation that is realised. The "
             "base augmentation (19A ~1.40x, 37 ~1.30x bollard thrust) already "
             "matches published Ka 4-70 / van Manen-Oosterveld data, so 1.0 "
             "reproduces literature performance. Lower it (~0.85-0.95) to derate "
             "for a worn duct, large tip gap, fouling, or a heavy wake.")
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

        modes_to_run = ["open", "19A", "37"] if op_mode == "All Comparer" else [op_mode]
        res_list = []
        for m in modes_to_run:
            # A fresh conditions object per mode -- the result stores this
            # reference, so a shared/mutated object would mislabel every row.
            cond = OperatingConditions(rpm=rpm_sin, Va_ship=va_sin, w=w, rho=rho, nu=nu,
                                       pv=pv, p_atm=p_atm, h=h, nozzle_mode=m)
            ns = NozzleSelection(nozzle_id=m, effectiveness=nozzle_effectiveness, tip_clearance_m_override=tip_clearance_m_override)
            res_list.append(solve_performance(
                geom, cond, nozzle_selection=ns,
                hydro_config=st.session_state.ow_consts,
                cav_config=st.session_state.cav_consts,
                series_hint=upload_single.name))
        
        st.session_state.current_res = res_list
        st.session_state.current_geom = geom

    if st.session_state.current_res:
        res_list = st.session_state.current_res
        geom = st.session_state.current_geom
        
        st.subheader(f"Parsed Propeller: {geom.diameter:.3f}m Diameter, {geom.blade_count} Blades")
        _ear, _pmm, _pd = _extract_ka_pitch(geom)
        st.info(f"**EAR (BAR):** {_ear:.2f}  |  **Pitch:** {_pmm:.0f} mm  |  "
                f"**P/D:** {_pd:.2f}  (read from geometry)")
        if geom.description:
            st.caption(f"File description tag: `{geom.description}` — note: this text "
                       f"field is unreliable in the bundled KA files (copy-paste "
                       f"errors); the values above are read from the actual geometry.")
        
        df_comp = pd.DataFrame([{
            "Mode": r.conditions.nozzle_mode, "J": r.J, "Thrust [N]": r.T_total,
            "Torque [Nm]": r.Q_total, "Shaft Power [W]": r.Pshaft_total, "eta": r.eta_total,
            "KT": r.KT_total, "KT (ref. poly)": r.KT_reference_poly,
            "Duct Thrust [N]": r.T_duct, "Duct Share": r.duct_thrust_share,
            "Duct Augmentation": r.duct_augmentation,
            "Static Efficiency": r.static_efficiency_est,
            "Thrust per Power [N/W]": r.thrust_per_power_N_per_W,
            "Sheet Cav [%]": r.Sheet_Cavitation_Est_PCT,
            "Tip Vortex Cav [%]": r.Tip_Vortex_Cavitation_Est_PCT,
            "Combined Cav [%]": r.Combined_Cavitation_Est_PCT,
            "Burrill Back Cav [%]": r.Burrill_Back_Cavitation_PCT,
        } for r in res_list])
        st.dataframe(df_comp)
        st.caption(f"Method: {res_list[0].method}  |  Series detected: {res_list[0].reference_series}  |  {res_list[0].reference_note}")
        
        if st.button("💾 Save Results to History"):
            for r in res_list:
                entry = {
                    "Timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Propeller": geom.file_name,
                    "RPM": r.conditions.rpm,
                    "Ship Speed": r.conditions.Va_ship,
                    "Mode": r.conditions.nozzle_mode,
                    "J": r.J,
                    "Thrust [N]": r.T_total,
                    "Torque [Nm]": r.Q_total,
                    "Power [W]": r.Pshaft_total,
                    "eta": r.eta_total,
                    "Static Efficiency": r.static_efficiency_est,
                    "Thrust/Power [N/W]": r.thrust_per_power_N_per_W,
                    "Sheet Cav. [%]": r.Sheet_Cavitation_Est_PCT,
                    "Tip Cav. [%]": r.Tip_Vortex_Cavitation_Est_PCT,
                    "Combined Cav. [%]": r.Combined_Cavitation_Est_PCT,
                    "Tip Vortex Index": r.Tip_Vortex_Cav_Index,
                    "_full_res": r 
                }
                st.session_state.saved_results.append(entry)
            st.success(f"Saved {len(res_list)} results to history!")

        st.subheader("Section Metrics (First Mode)")
        df_sec = export_section_table(res_list[0])
        st.dataframe(df_sec)

    # ---- Bidirectional (ahead / astern / average) analysis ------------------
    st.markdown("---")
    st.subheader("↔️ Bidirectional Analysis (Ahead / Astern / Average)")
    st.caption("Reversing thrusters run in both directions. Astern uses a "
               "reduced-blade + astern-duct model: nozzle 19A loses most of its "
               "duct benefit in reverse, while 37's rounded trailing edge keeps "
               "it — which is exactly why 37 exists. The average lets you compare "
               "nozzles fairly for two-way operation.")
    if upload_single and st.button("Run Bidirectional Analysis"):
        geom_bi = parse_hcpc_content(upload_single.getvalue().decode("utf-8", errors="replace"), upload_single.name)
        modes_bi = ["open", "19A", "37"] if op_mode == "All Comparer" else [op_mode]
        bi_rows = []
        for m in modes_bi:
            cond_bi = OperatingConditions(rpm=rpm_sin, Va_ship=va_sin, w=w, rho=rho, nu=nu,
                                          pv=pv, p_atm=p_atm, h=h, nozzle_mode=m)
            ns_bi = NozzleSelection(nozzle_id=m, effectiveness=nozzle_effectiveness,
                                    tip_clearance_m_override=tip_clearance_m_override)
            ah, ast, avg = solve_bidirectional(geom_bi, cond_bi, nozzle_selection=ns_bi,
                                               hydro_config=st.session_state.ow_consts,
                                               cav_config=st.session_state.cav_consts,
                                               series_hint=upload_single.name)
            for lbl, r in [("Ahead", ah), ("Astern", ast)]:
                bi_rows.append({
                    "Mode": m, "Direction": lbl, "Thrust [N]": r.T_total,
                    "Torque [Nm]": r.Q_total, "eta": r.eta_total,
                    "Combined Cav [%]": r.Combined_Cavitation_Est_PCT,
                    "Burrill Back Cav [%]": r.Burrill_Back_Cavitation_PCT,
                })
            bi_rows.append({
                "Mode": m, "Direction": "AVERAGE", "Thrust [N]": avg["T_total"],
                "Torque [Nm]": avg["Q_total"], "eta": avg["eta_total"],
                "Combined Cav [%]": avg["Combined_Cavitation_Est_PCT"],
                "Burrill Back Cav [%]": avg["Burrill_Back_Cavitation_PCT"],
            })
        st.dataframe(pd.DataFrame(bi_rows))
        st.info("Astern is an engineering reduced-performance model (not a full "
                "four-quadrant BEMT). It captures the ahead/astern trend and the "
                "19A-vs-37 astern difference; absolute astern numbers are indicative.")

    # ---- Experimental alternative solver: axisymmetric duct panel method -----
    st.markdown("---")
    st.subheader("🔬 Duct BEM — Axisymmetric Panel Method (experimental)")
    st.caption("Alternative, higher-fidelity duct model. Distributes ring "
               "vortices on the real nozzle camber line, solves flow tangency, "
               "and evaluates the duct-induced axial velocity u_a(r) at the "
               "propeller plane by Biot-Savart. The local V_A(r) then drives the "
               "cavitation directly (no KT/KQ regression). Does not affect the "
               "main solver above.")
    if upload_single and st.button("Solve with Duct BEM (Panel Method)"):
        geom_b = parse_hcpc_content(upload_single.getvalue().decode("utf-8", errors="replace"), upload_single.name)
        rows = []
        fig_ua = go.Figure()
        for nz in ["19A", "37"]:
            cond_b = OperatingConditions(rpm=rpm_sin, Va_ship=va_sin, w=w, rho=rho, nu=nu,
                                         pv=pv, p_atm=p_atm, h=h, nozzle_mode=nz)
            rb = solve_duct_bem_cavitation(geom_b, cond_b, nz,
                                           ow=st.session_state.ow_consts,
                                           cav=st.session_state.cav_consts,
                                           clearance_override=tip_clearance_m_override)
            if rb is None:
                st.warning(f"Panel method could not build geometry for {nz}.")
                continue
            t = rb.tvc
            rows.append({
                "Nozzle": nz,
                "mean u_a [m/s]": rb.bem.mean_u_a,
                "Duct type": "ACCELERATING" if rb.bem.accelerating else "DECELERATING",
                "Blade Thrust [N]": rb.T_blade,
                "V_leak [m/s]": t.V_leak if t else None,
                "P_core [kPa]": (t.P_core / 1000.0) if t else None,
                "sigma_TVC": t.sigma_tvc if t else None,
                "Tip Leakage Cav [%]": rb.tip_pct,
                "Sheet Cav [%]": rb.sheet_pct,
                "Combined Cav [%]": rb.combined_pct,
                "Burrill Back Cav [%]": rb.burrill_back_pct,
            })
            fig_ua.add_trace(go.Scatter(x=list(rb.bem.r_over_R), y=list(rb.bem.u_a),
                                        mode="lines+markers", name=f"{nz}  u_a(r)"))
        if rows:
            st.dataframe(pd.DataFrame(rows))
            fig_ua.update_layout(title="Duct-induced axial velocity u_a(r) at the propeller plane",
                                 xaxis_title="r/R", yaxis_title="u_a [m/s]  (>0 = accelerating)")
            st.plotly_chart(fig_ua, use_container_width=True)
            st.info("Sign of u_a(r) is computed from the geometry, not assumed. "
                    "Both 19A and 37 come out accelerating (u_a > 0), consistent "
                    "with the standard MARIN classification.")
            st.caption("Tip-vortex cavitation uses the analytical tip-leakage / "
                       "Rankine-core model (no empirical suppression multiplier): "
                       "dP_tip -> V_leak -> Gamma_L -> P_core -> sigma_TVC, driven by "
                       "the physical tip clearance. The core radius is taken as "
                       "core_factor x tip clearance; the literal a_c = clearance "
                       "assumption over-concentrates the vortex for sub-mm gaps "
                       "(giving unphysical P_core), so a physical core_factor ~ 5 is used.")

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
        
        df_batch = run_batch_analysis(geoms, rpms, speeds, batch_modes, b_cond,
                                      st.session_state.ow_consts, st.session_state.cav_consts,
                                      nozzle_effectiveness)
        st.dataframe(df_batch)
        
        csv_data = generate_csv(df_batch)
        st.download_button("Download CSV", data=csv_data, file_name="batch_results.csv", mime="text/csv")
        
        if len(df_batch) > 1:
            df_plot = df_batch.rename(columns={"Thrust_N": "Thrust[N]", "Power_W": "Power[W]", "Combined_Cavitation_PCT": "Cavitation[%]"})
            f1, f2, f3 = plot_performance_curves(df_plot)
            st.plotly_chart(f1)
            st.plotly_chart(f2)
            st.plotly_chart(f3)

with tab_test:
    st.header("Test Scenario — Bollard RPM Sweep")
    st.caption("Fixed scenario: RPM = 2000 / 2500 / 3000 / 3500, ship speed = 0 "
               "(bollard), All Comparer (open / 19A / 37), and both directions "
               "(Ahead / Astern / Average). Upload an .hcpc and run; 'Save to Test "
               "Data' accumulates a separate dataset (independent of the Saved Data "
               "tab). Fluid properties and nozzle overrides are taken from the sidebar.")
    TEST_RPMS = [2000.0, 2500.0, 3000.0, 3500.0]
    TEST_MODES = ["open", "19A", "37"]
    test_upload = st.file_uploader("Upload .hcpc for the test scenario", type=['hcpc'], key="test_ul")

    if test_upload and st.button("Run Test Scenario"):
        geom_t = parse_hcpc_content(test_upload.getvalue().decode("utf-8", errors="replace"), test_upload.name)
        ka_val, pitch_mm_val, pd_val = _extract_ka_pitch(geom_t)
        ts = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

        def _metrics(res):
            return {
                "Thrust [N]": res.T_total, "Torque [Nm]": res.Q_total,
                "Power [W]": res.Pshaft_total, "Static Efficiency": res.static_efficiency_est,
                "Thrust/Power [N/W]": res.thrust_per_power_N_per_W, "KT": res.KT_total,
                "Duct Thrust [N]": res.T_duct, "Duct Share": res.duct_thrust_share,
                "Duct Augmentation": res.duct_augmentation,
                "Sheet Cav [%]": res.Sheet_Cavitation_Est_PCT,
                "Tip Cav [%]": res.Tip_Vortex_Cavitation_Est_PCT,
                "Combined Cav [%]": res.Combined_Cavitation_Est_PCT,
                "Burrill Back Cav [%]": res.Burrill_Back_Cavitation_PCT,
            }

        def _avg(a, b):
            out = {}
            for k in a:
                if isinstance(a[k], (int, float)) and isinstance(b[k], (int, float)):
                    out[k] = 0.5 * (a[k] + b[k])
                else:
                    out[k] = None
            return out

        rows = []
        for rpm_t in TEST_RPMS:
            for m in TEST_MODES:
                cond_t = OperatingConditions(rpm=rpm_t, Va_ship=0.0, w=w, rho=rho, nu=nu,
                                             pv=pv, p_atm=p_atm, h=h, nozzle_mode=m)
                ns_t = NozzleSelection(nozzle_id=m, effectiveness=nozzle_effectiveness,
                                       tip_clearance_m_override=tip_clearance_m_override)
                ah, ast, _avgdict = solve_bidirectional(
                    geom_t, cond_t, nozzle_selection=ns_t,
                    hydro_config=st.session_state.ow_consts,
                    cav_config=st.session_state.cav_consts, series_hint=test_upload.name)
                m_ah, m_as = _metrics(ah), _metrics(ast)
                # Astern/Ahead thrust ratio (bidirectional suitability), shared
                # across the group's three direction rows.
                ratio = (ast.T_total / ah.T_total) if abs(ah.T_total) > 1e-9 else None
                base = {"Timestamp": ts, "File": geom_t.file_name, "EAR (BAR)": ka_val,
                        "Pitch (mm)": pitch_mm_val, "P/D": pd_val, "RPM": rpm_t, "Mode": m,
                        "Astern/Ahead Thrust": ratio}
                rows.append({**base, "Direction": "Ahead", **m_ah})
                rows.append({**base, "Direction": "Astern", **m_as})
                rows.append({**base, "Direction": "Average", **_avg(m_ah, m_as)})
        st.session_state.test_current = rows
        st.success(f"Computed {len(rows)} rows ({len(TEST_RPMS)} RPM x {len(TEST_MODES)} modes "
                   f"x 3 directions) for {geom_t.file_name}  "
                   f"(EAR={ka_val:.2f}, Pitch={pitch_mm_val:.0f}mm, P/D={pd_val:.2f}).")

    if st.session_state.test_current:
        st.subheader("Latest run")
        st.dataframe(pd.DataFrame(st.session_state.test_current))
        if st.button("💾 Save to Test Data"):
            st.session_state.test_results.extend(st.session_state.test_current)
            st.session_state.test_current = None
            st.success("Appended to Test Data.")
            st.rerun()

    st.markdown("---")
    st.subheader("Accumulated Test Data")
    if not st.session_state.test_results:
        st.info("No test data saved yet. Run a scenario and click 'Save to Test Data'.")
    else:
        df_test = pd.DataFrame(st.session_state.test_results)
        st.dataframe(df_test, use_container_width=True)

        def _to_excel_bytes(df):
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="TestData")
            return buf.getvalue()

        cta, ctb, ctc = st.columns(3)
        cta.download_button("📥 Download (Excel)", data=_to_excel_bytes(df_test),
                            file_name="test_scenario_data.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        ctb.download_button("📥 Download (CSV)", data=generate_csv(df_test),
                            file_name="test_scenario_data.csv", mime="text/csv")
        if ctc.button("🗑️ Clear Test Data"):
            st.session_state.test_results = []
            st.rerun()

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

with tab_saved:
    st.header("Saved Analysis History")
    if not st.session_state.saved_results:
        st.info("No saved results yet. Run a single analysis and click 'Save to History'.")
    else:
        # Create a display dataframe without the hidden full result object
        df_display = pd.DataFrame([{k: v for k, v in r.items() if k != "_full_res"} for r in st.session_state.saved_results])
        st.dataframe(df_display, use_container_width=True)
        
        col_s1, col_s2 = st.columns(2)
        csv_history = generate_csv(df_display)
        col_s1.download_button("📥 Download All Saved Data (CSV)", data=csv_history, file_name="analysis_history.csv", mime="text/csv")
        
        if col_s2.button("🗑️ Clear History"):
            st.session_state.saved_results = []
            st.rerun()

        st.markdown("---")
        st.subheader("Detailed Section Metrics Graphics")
        
        # Selection for which saved result to visualize
        result_labels = [f"{r['Timestamp']} - {r['Propeller']} ({r['Mode']} @ {r['RPM']} RPM)" for r in st.session_state.saved_results]
        selected_idx = st.selectbox("Select a result to view distributions:", range(len(result_labels)), format_func=lambda i: result_labels[i])
        
        if selected_idx is not None:
            full_res = st.session_state.saved_results[selected_idx]["_full_res"]
            f_dt, f_cl = plot_section_metrics(full_res)
            
            c_p1, c_p2 = st.columns(2)
            c_p1.plotly_chart(f_dt, use_container_width=True)
            c_p2.plotly_chart(f_cl, use_container_width=True)

with tab_settings:
    st.header("Physics Constants")
    st.caption("All constants are documented with their source/range in the "
               "`src/hydro` modules. Open-water lift constants are globally "
               "calibrated to the Wageningen B-series polynomial; cavitation "
               "constants are cross-checked against the Burrill criterion.")

    ow = st.session_state.ow_consts
    cav = st.session_state.cav_consts

    st.markdown("### Blade section hydrodynamics (BEMT)")
    o1, o2 = st.columns(2)
    ow.cl_slope_efficiency = o1.number_input(
        "Lift-slope efficiency", value=ow.cl_slope_efficiency, min_value=0.1, max_value=1.0,
        help="Effective reduction of the 2*pi lift slope (viscous decambering, "
             "finite-Re, cascade). Calibrated to the B-series.")
    ow.zero_lift_camber_factor = o2.number_input(
        "Zero-lift camber factor", value=ow.zero_lift_camber_factor,
        help="alpha_0 = -k*(f/c); ~1.8 for marine mean lines.")
    ow.cl_max = o1.number_input("CL max (stall ceiling)", value=ow.cl_max)
    ow.form_drag_factor = o2.number_input("Drag thickness form factor", value=ow.form_drag_factor)

    st.markdown("### Sheet cavitation (-Cp_min)")
    s1, s2 = st.columns(2)
    cav.sheet_thickness_k = s1.number_input("Thickness peak weight", value=cav.sheet_thickness_k)
    cav.sheet_loading_k = s2.number_input(
        "Loading peak weight (CL^2)", value=cav.sheet_loading_k,
        help="2.5 makes the section -Cp_min model agree with the Burrill criterion.")
    cav.sheet_severity_scale = s1.number_input("Severity scale", value=cav.sheet_severity_scale)

    st.markdown("### Tip vortex — open (McCormick 1962)")
    t1, t2 = st.columns(2)
    cav.tip_K = t1.number_input("McCormick K", value=cav.tip_K)
    cav.tip_Re_exp = t2.number_input("Reynolds exponent", value=cav.tip_Re_exp)
    cav.tip_start_rR = t1.number_input("Tip region start r/R", value=cav.tip_start_rR)
    cav.tip_end_rR = t2.number_input("Tip region end r/R", value=cav.tip_end_rR)
    cav.lambda_tip = st.number_input("Lambda tip (weight in combined)", value=cav.lambda_tip)

    st.markdown("### Tip-leakage vortex — ducted (analytical, replaces 0.15)")
    l1, l2 = st.columns(2)
    cav.tvc_C_D = l1.number_input(
        "Gap discharge coefficient C_D", value=cav.tvc_C_D, min_value=0.3, max_value=1.0,
        help="Bernoulli discharge coefficient for the tip gap (0.6-0.8 by geometry).")
    cav.tvc_core_factor = l2.number_input(
        "Core radius / tip gap (a_c/delta)", value=cav.tvc_core_factor, min_value=1.0,
        help="Rankine core radius as a multiple of the tip clearance. a_c=delta (=1) "
             "over-concentrates the vortex for sub-mm gaps; ~5 (a_c~0.1-0.2 c_tip) is physical.")

    if st.button("Reset to defaults"):
        st.session_state.ow_consts = OpenWaterConstants()
        st.session_state.cav_consts = CavitationConstants()
        st.rerun()
