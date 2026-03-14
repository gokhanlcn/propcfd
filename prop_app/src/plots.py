import plotly.graph_objects as go
import pandas as pd

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
