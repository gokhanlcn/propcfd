import json
from .models import PropellerGeometry, BladeSection, FoilContour
from .units import length_to_meters
from .geometry import compute_dr

def parse_hcpc_content(file_content: str, filename: str) -> PropellerGeometry:
    try:
        data = json.loads(file_content)
    except Exception as e:
        raise ValueError(f"Failed to parse JSON for {filename}: {str(e)}")
        
    project = data.get("Project", {})
    prop_id = project.get("ID", filename)
    description = project.get("Description", "")
    
    units = data.get("Units", {})
    len_unit = units.get("PropLength", "mm")
    
    prop_data = data.get("Propeller", {})
    blade_count = prop_data.get("BladeCount", 3)
    diameter = length_to_meters(prop_data.get("Diameter", 0.0), len_unit)
    radius = diameter / 2.0
    ear = prop_data.get("ExpAreaRatio", 0.5)
    
    hub_data = data.get("PropellerHub", {})
    hub_diam = length_to_meters(hub_data.get("MidDiameter", diameter * 0.2), len_unit)
    hub_radius = hub_diam / 2.0
    
    sections_data = prop_data.get("BladeSections", {})
    sections = []
    
    # In newer hcpc, BladeSections is a dictionary where individual sections are keyed by '0', '1', etc.
    # It might also be a list. Let's make it robust.
    if isinstance(sections_data, dict):
        section_items = [v for k, v in sections_data.items() if k.isdigit()]
    elif isinstance(sections_data, list):
        section_items = sections_data
    else:
        section_items = []

    for sec in section_items:
        r_over_R = float(sec.get("RadialPos", 0.0))
        chord = length_to_meters(sec.get("Chord", 0.0), len_unit)
        thickness = length_to_meters(sec.get("Thickness", 0.0), len_unit)
        
        pitch = sec.get("Pitch", None)
        if pitch is None:
            pitch = prop_data.get("PitchMean", 0.0)
        pitch = length_to_meters(pitch, len_unit)
        
        foil = sec.get("FinalFoil", sec.get("RawFoil", {}))
        camber = length_to_meters(foil.get("Camber", sec.get("Camber", 0.0)), len_unit)
        
        skew_deg = float(sec.get("SkewAngleDeg", 0.0))
        rake = length_to_meters(sec.get("RakeAft", 0.0), len_unit)
        
        # Parse foil contour coordinates and ensure they are floats natively scaled to meters
        foil_contour = None
        if foil:
            x_up = foil.get("UpperOffsetX", [])
            y_up = foil.get("UpperOffsetY", [])
            x_low = foil.get("LowerOffsetX", [])
            y_low = foil.get("LowerOffsetY", [])
            
            if x_up and y_up and x_low and y_low:
                try:
                    foil_contour = FoilContour(
                        x_upper=[length_to_meters(float(x), len_unit) for x in x_up],
                        y_upper=[length_to_meters(float(y), len_unit) for y in y_up],
                        x_lower=[length_to_meters(float(x), len_unit) for x in x_low],
                        y_lower=[length_to_meters(float(y), len_unit) for y in y_low]
                    )
                except (ValueError, TypeError):
                    foil_contour = None
        
        r_val = r_over_R * radius
        
        bs = BladeSection(
            r_over_R=r_over_R, r=r_val, chord=chord, thickness=thickness,
            pitch=pitch, camber=camber, skew_deg=skew_deg, rake=rake,
            foil_contour=foil_contour
        )
        sections.append(bs)
        
    compute_dr(sections)
    
    return PropellerGeometry(
        propeller_id=prop_id, file_name=filename, description=description, blade_count=blade_count,
        diameter=diameter, radius=radius, hub_radius=hub_radius,
        expanded_area_ratio=ear, sections=sections
    )
