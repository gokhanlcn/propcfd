import plotly.graph_objects as go
import pandas as pd
from .models import PerformanceResult

def plot_performance_curves(df_results: pd.DataFrame):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_results['RPM'], y=df_results['Thrust[N]'], mode='lines+markers', name='Thrust'))
    fig.update_layout(title='Thrust vs RPM', xaxis_title='RPM', yaxis_title='Thrust [N]')
    
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=df_results['RPM'], y=df_results['Power[W]'], mode='lines+markers', name='Power'))
    fig2.update_layout(title='Shaft Power vs RPM', xaxis_title='RPM', yaxis_title='Power [W]')
    
    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(x=df_results['J'], y=df_results['Cavitation[%]'], mode='lines+markers', name='Cavitation'))
    fig3.update_layout(title='Cavitation vs Advance Coeff (J)', xaxis_title='J', yaxis_title='Cavitation Estimate [%]')
    return fig, fig2, fig3
def plot_section_metrics(res: PerformanceResult):
    """Returns figures for Thrust distribution and Axial Velocity distribution vs r/R."""
    df = pd.DataFrame([{
        "r/R": s.r_over_R,
        "dT [N]": s.dT,
        "Vax_local [m/s]": s.beta_i  # beta_i is roughly related to axial inflow angle, but let's use the actual velocity if available
    } for s in res.section_results])
    
    # Actually, solver.py stores u_n (nozzle induced) in SectionResult but beta_i is the inflow angle.
    # Let's use dT and CL for "meaningful" distributions as discussed.
    df = pd.DataFrame([{
        "r/R": s.r_over_R,
        "dT [N]": s.dT,
        "CL": s.CL,
        "Vax_local": s.nozzle_u_local # This is the nozzle induced part, we can add Va+vi to it
    } for s in res.section_results])
    
    Va = res.conditions.Va_ship * (1 - res.conditions.w)
    # Note: vi (induced velocity) is constant across disk in this simple BEMT. 
    # Let's just plot dT and CL as they are the most descriptive of the "debi" (output/work).
    
    fig_dt = go.Figure()
    fig_dt.add_trace(go.Scatter(x=df['r/R'], y=df['dT [N]'], mode='lines+markers', name='Thrust Distribution'))
    fig_dt.update_layout(title='Thrust Distribution (dT) vs r/R', xaxis_title='r/R', yaxis_title='dT [N]')
    
    fig_cl = go.Figure()
    fig_cl.add_trace(go.Scatter(x=df['r/R'], y=df['CL'], mode='lines+markers', name='Lift Coefficient'))
    fig_cl.update_layout(title='Lift Coefficient (CL) vs r/R', xaxis_title='r/R', yaxis_title='CL')
    
    return fig_dt, fig_cl
