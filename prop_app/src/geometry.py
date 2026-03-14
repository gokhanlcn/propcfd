from typing import List
from .models import BladeSection

def compute_dr(sections: List[BladeSection]) -> None:
    # Sort just to be safe
    sections.sort(key=lambda x: x.r)
    n = len(sections)
    if n > 1:
        for i in range(n):
            if i == 0:
                dr = sections[1].r - sections[0].r
            elif i == n - 1:
                dr = sections[i].r - sections[i-1].r
            else:
                dr = (sections[i+1].r - sections[i-1].r) / 2.0
            sections[i].dr = max(dr, 1e-6)
