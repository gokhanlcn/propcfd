def length_to_meters(val: float, unit: str) -> float:
    if val is None: return 0.0
    unit = unit.lower()
    if unit == "mm": return val / 1000.0
    if unit == "cm": return val / 100.0
    if unit == "in": return val * 0.0254
    return float(val)

def pressure_to_pa(val: float, unit: str) -> float:
    if val is None: return 0.0
    unit = unit.lower()
    if unit == "kpa": return val * 1000.0
    if unit == "bar": return val * 100000.0
    return float(val)
