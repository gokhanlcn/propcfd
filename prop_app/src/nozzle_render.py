import plotly.graph_objects as go
import numpy as np
from typing import Optional
from .nozzle_geometry import ScaledNozzleGeometry
from .models import PropellerGeometry

def plot_nozzle_2d(nozzle_geom: Optional[ScaledNozzleGeometry], prop_geom: Optional[PropellerGeometry] = None) -> go.Figure:
    fig = go.Figure()
    if not nozzle_geom:
        fig.add_annotation(text="Nozzle type 'open' - No nozzle geometry to display", showarrow=False)
        fig.update_layout(xaxis_visible=False, yaxis_visible=False)
        return fig
    
    # Standard 2D upper half profile
    x = nozzle_geom.x_m
    y_in = nozzle_geom.r_in_m
    y_out = nozzle_geom.r_out_m
    
    fig.add_trace(go.Scatter(x=x, y=y_in, mode='lines', name='Inner Profile', line=dict(color='blue')))
    fig.add_trace(go.Scatter(x=x, y=y_out, mode='lines', name='Outer Profile', line=dict(color='orange')))
    
    # Close the leading and trailing edges
    fig.add_trace(go.Scatter(x=[x[0], x[0]], y=[y_in[0], y_out[0]], mode='lines', showlegend=False, line=dict(color='gray')))
    fig.add_trace(go.Scatter(x=[x[-1], x[-1]], y=[y_in[-1], y_out[-1]], mode='lines', showlegend=False, line=dict(color='gray')))
    
    # Also plot lower half for a complete cross section view
    fig.add_trace(go.Scatter(x=x, y=-y_in, mode='lines', name='Inner Profile (BTM)', line=dict(color='blue', dash='dot')))
    fig.add_trace(go.Scatter(x=x, y=-y_out, mode='lines', name='Outer Profile (BTM)', line=dict(color='orange', dash='dot')))
    
    # Plot Propeller Overlays if provided
    if prop_geom:
        R_prop = prop_geom.radius
        R_hub = prop_geom.hub_radius
        
        # Propeller Tip limits
        fig.add_trace(go.Scatter(x=[0, 0], y=[-R_prop, R_prop], mode='lines', name='Propeller Blade Plane (X=0)', line=dict(color='red', width=3)))
        
        # Propeller Hub limits
        fig.add_trace(go.Scatter(x=[0, 0], y=[-R_hub, R_hub], mode='lines', name='Propeller Hub Plane', line=dict(color='black', width=6)))
        
        # Axial swept tip lines (Visual limit across duct)
        fig.add_trace(go.Scatter(x=[x[0], x[-1]], y=[R_prop, R_prop], mode='lines', name='Prop Tip Radius', line=dict(color='green', width=1, dash='dot')))
        fig.add_trace(go.Scatter(x=[x[0], x[-1]], y=[-R_prop, -R_prop], mode='lines', showlegend=False, line=dict(color='green', width=1, dash='dot')))
        
        title_text = f"2D Meridional Section - {nozzle_geom.def_info.display_name} with Propeller Overlay<br><sup>Tip Clearance @ Prop Plane: {nozzle_geom.clearance_prop_plane*1000.0:.3f} mm | Min Clearance: {nozzle_geom.min_clearance*1000.0:.3f} mm</sup>"
    else:
        # Fallback if no prop geom (should not happen based on new pipeline)
        title_text = f"2D Meridional Section - {nozzle_geom.def_info.display_name}<br><sup>Tip Clearance @ Prop Plane: {nozzle_geom.clearance_prop_plane*1000.0:.3f} mm | Min Clearance: {nozzle_geom.min_clearance*1000.0:.3f} mm</sup>"
        
    fig.update_layout(
        title=title_text,
        xaxis_title="Axial Position X [m]",
        yaxis_title="Radius R [m]",
        yaxis=dict(scaleanchor="x", scaleratio=1),  # True aspect ratio
        template="plotly_white"
    )
    return fig

def plot_nozzle_3d(nozzle_geom: Optional[ScaledNozzleGeometry]) -> go.Figure:
    fig = go.Figure()
    if not nozzle_geom:
        fig.add_annotation(text="Nozzle type 'open' - No 3D geometry to display", showarrow=False)
        fig.update_layout(scene=dict(xaxis_visible=False, yaxis_visible=False, zaxis_visible=False))
        return fig
    
    # Revolve inner and outer profiles
    theta = np.linspace(0, 2 * np.pi, 60)
    theta_grid, x_grid = np.meshgrid(theta, nozzle_geom.x_m)
    
    # Inner surface
    _, r_in_grid = np.meshgrid(theta, nozzle_geom.r_in_m)
    y_in_3d = r_in_grid * np.cos(theta_grid)
    z_in_3d = r_in_grid * np.sin(theta_grid)
    
    # Outer surface
    _, r_out_grid = np.meshgrid(theta, nozzle_geom.r_out_m)
    y_out_3d = r_out_grid * np.cos(theta_grid)
    z_out_3d = r_out_grid * np.sin(theta_grid)
    
    fig.add_trace(go.Surface(x=x_grid, y=y_in_3d, z=z_in_3d, colorscale='Blues', opacity=0.8, showscale=False, name="Inner Surface"))
    fig.add_trace(go.Surface(x=x_grid, y=y_out_3d, z=z_out_3d, colorscale='Oranges', opacity=0.4, showscale=False, name="Outer Surface"))
    
    fig.update_layout(
        title=f"3D Surface View - {nozzle_geom.def_info.display_name}",
        scene=dict(
            xaxis_title="X [m]", yaxis_title="Y [m]", zaxis_title="Z [m]",
            aspectmode='data'
        ),
        margin=dict(l=0, r=0, b=0, t=40)
    )
    return fig

def plot_prop_nozzle_combined(prop_geom: PropellerGeometry, nozzle_geom: Optional[ScaledNozzleGeometry]) -> go.Figure:
    """
    Visual overlay of the propeller disk and blades inside the duct.
    This is an engineering approximation preview, not exact hydro-CAD.
    """
    fig = plot_nozzle_3d(nozzle_geom)
    fig.layout.title = "Visual Geometry Preview: Propeller + Nozzle Overlay"
    
    B = prop_geom.blade_count
    angles = np.linspace(0, 2*np.pi, B, endpoint=False)
    
    # Propeller center hub visualization
    hub_len = prop_geom.radius * 0.4
    hub_x = np.linspace(-hub_len/2, hub_len/2, 10)
    theta_hub = np.linspace(0, 2*np.pi, 20)
    th_grid, hx_grid = np.meshgrid(theta_hub, hub_x)
    y_hub = prop_geom.hub_radius * np.cos(th_grid)
    z_hub = prop_geom.hub_radius * np.sin(th_grid)
    fig.add_trace(go.Surface(x=hx_grid, y=y_hub, z=z_hub, colorscale='Greys', showscale=False, opacity=1.0))
    
    # Build authentic 3D blade surfaces if foil data is present, otherwise fallback to thin plates
    has_foils = all(s.foil_contour is not None for s in prop_geom.sections)
    
    # Pre-calculate surface grids for one blade
    r_coords = []
    x_coords = []
    y_coords = []
    z_coords = []
    
    # We will interpolate each section to a fixed number of points around the foil (e.g. 60 points)
    # from TE lower -> LE -> TE upper
    num_profile_pts = 60
    
    for s in prop_geom.sections:
        r_val = s.r
        c_val = s.chord
        pitch_angle = np.arctan2(s.pitch, 2 * np.pi * r_val)
        skew_rad = np.radians(s.skew_deg)
        rake = s.rake
        
        if has_foils and s.foil_contour:
            # Reconstruct profile wrapping from TE (lower) to LE to TE (upper)
            x_low = np.array(s.foil_contour.x_lower)
            y_low = np.array(s.foil_contour.y_lower)
            x_up = np.array(s.foil_contour.x_upper)
            y_up = np.array(s.foil_contour.y_upper)
            
            # Combine: reverse lower (TE to LE), then append upper (LE to TE) without duplicate LE
            x_prof_raw = np.concatenate((x_low[::-1], x_up[1:]))
            y_prof_raw = np.concatenate((y_low[::-1], y_up[1:]))
            
            # Interpolate to uniform arc-length or index distribution
            idx_raw = np.linspace(0, 1, len(x_prof_raw))
            idx_uniform = np.linspace(0, 1, num_profile_pts)
            
            x_prof = np.interp(idx_uniform, idx_raw, x_prof_raw)
            y_prof = np.interp(idx_uniform, idx_raw, y_prof_raw)
        else:
            # Fallback thin plate if no foil contours
            x_prof = np.linspace(0, c_val, num_profile_pts)
            y_prof = np.zeros(num_profile_pts)
            
        # Transform local (x_prof, y_prof) at radius r to cylindrical, then to Cartesian
        # x_prof=0 is LE. Let's center at mid-chord: x_c in [-c/2, c/2]
        # Actually HC foil x=0 is LE. TE is at x=c.
        # Flow is positive axial. TE is downstream. So positive X_global maps to positive x_prof.
        x_c = x_prof - c_val/2.0
        
        # Axial offset (x is positive downstream)
        X_cyl = rake + x_c * np.sin(pitch_angle) - y_prof * np.cos(pitch_angle)
        
        # Tangential offset (x_c positive means downstream TE, which goes AGAINST rotation, so negative theta)
        # Assuming right-handed rotation (positive theta)
        tan_dist = -x_c * np.cos(pitch_angle) - y_prof * np.sin(pitch_angle)
        theta_cyl = skew_rad + tan_dist / r_val
        
        r_coords.append(np.full_like(x_prof, r_val))
        x_coords.append(X_cyl)
        y_coords.append(r_val * np.cos(theta_cyl))
        z_coords.append(r_val * np.sin(theta_cyl))
        
    X_grid_base = np.array(x_coords)
    Y_grid_base = np.array(y_coords)
    Z_grid_base = np.array(z_coords)
    
    surface_name_prefix = "Realistic Blade Surface" if has_foils else "Thin Plate Preview"

    for i in range(B):
        base_angle = angles[i]
        
        # Rotate global Y/Z coordinates by base_angle
        Y_rot = Y_grid_base * np.cos(base_angle) - Z_grid_base * np.sin(base_angle)
        Z_rot = Y_grid_base * np.sin(base_angle) + Z_grid_base * np.cos(base_angle)
        
        # Plot 3D lofted surface
        fig.add_trace(go.Surface(
            x=X_grid_base, y=Y_rot, z=Z_rot, 
            colorscale='Viridis', showscale=False, opacity=0.9,
            name=f"{surface_name_prefix} {i+1}"
        ))
        
    fig.update_layout(scene_aspectmode='data')
    return fig
