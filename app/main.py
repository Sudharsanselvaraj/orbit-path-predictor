from __future__ import annotations
import re
from typing import Tuple, List, Dict
from datetime import datetime, timedelta
import math

import numpy as np
from sgp4.api import Satrec, jday

# ------------------ TLE parsing/formatting ------------------

_TLE_PAIR_REGEX = re.compile(
    r"(1\s+\d{5}[U ]\s.*?)(2\s+\d{5}\s.*)",
    flags=re.IGNORECASE | re.DOTALL,
)

def normalize_tle_block(tle_text: str) -> Tuple[str, str, str]:
    """
    Accept TLE as:
      • 2 lines (L1, L2)
      • 3 lines (NAME, L1, L2)
      • 1 long line containing L1 ... L2 (your example)
    Return (name, L1, L2)
    """
    raw = tle_text.strip()

    # If already split by newlines
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if len(lines) >= 2 and lines[0].startswith("1 ") and lines[1].startswith("2 "):
        return "UNKNOWN", lines[0], lines[1]
    if len(lines) >= 3 and lines[1].startswith("1 ") and lines[2].startswith("2 "):
        return lines[0], lines[1], lines[2]

    # Single-line TLE: find L1 and L2 with regex
    m = _TLE_PAIR_REGEX.search(raw.replace("\n", " "))
    if not m:
        raise ValueError("Could not parse TLE. Provide 2-line or 3-line TLE, or a single line containing L1 and L2.")
    l1 = m.group(1).strip()
    l2 = m.group(2).strip()
    return "UNKNOWN", l1, l2

def tle_checksum(line: str) -> str:
    """Compute TLE checksum digit (last column)."""
    s = 0
    for c in line[:68]:
        if c.isdigit():
            s += int(c)
        elif c == '-':
            s += 1
    return str(s % 10)

def replace_col_span(s: str, start: int, end: int, value: str) -> str:
    """Replace 1-based inclusive [start,end] columns with value (len must match)."""
    start -= 1
    return s[:start] + value + s[end:]

def adjust_mean_motion_l2(line2: str, delta_rev_per_day: float) -> str:
    """
    Add a small delta to mean motion (rev/day) in L2 (cols 53-63).
    Return updated L2 with corrected checksum.
    """
    current_mm = float(line2[52:63])
    new_mm = current_mm + delta_rev_per_day
    mm_str = f"{new_mm:11.8f}"  # width 11 inc decimal

    l2 = replace_col_span(line2, 53, 63, mm_str)
    # reset & recompute checksum
    if len(l2) < 69:
        l2 = l2.ljust(68) + "0"
    l2 = l2[:68] + tle_checksum(l2)
    return l2

# ------------------ Propagation & geometry ------------------

def propagate_positions(tle_text: str, minutes: int = 180, step_s: int = 60) -> List[Dict]:
    """
    Propagate ECI positions over 'minutes' every 'step_s' sec.
    Returns [{'t': ISO, 'r':[x,y,z] km, 'v':[vx,vy,vz] km/s}, ...]
    """
    _, L1, L2 = normalize_tle_block(tle_text)
    sat = Satrec.twoline2rv(L1, L2)

    t0 = datetime.utcnow()
    out = []
    for k in range(0, minutes * 60 + 1, step_s):
        t = t0 + timedelta(seconds=k)
        jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond / 1e6)
        e, r, v = sat.sgp4(jd, fr)
        if e == 0:  # 0 == success
            out.append({
                "t": t.isoformat() + "Z",
                "r": [float(r[0]), float(r[1]), float(r[2])],
                "v": [float(v[0]), float(v[1]), float(v[2])]
            })
    return out

def nearest_approach_km(path_a: List[Dict], path_b: List[Dict]) -> tuple[float, Dict]:
    """Minimum distance (km) between two paths aligned by index."""
    n = min(len(path_a), len(path_b))
    dmin = float("inf")
    kmin = -1
    for i in range(n):
        ax, ay, az = path_a[i]["r"]
        bx, by, bz = path_b[i]["r"]
        d = math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)
        if d < dmin:
            dmin = d
            kmin = i
    meta = {}
    if kmin >= 0:
        meta = {
            "time": path_a[kmin]["t"],
            "sat_r": path_a[kmin]["r"],
            "deb_r": path_b[kmin]["r"],
            "index": kmin
        }
    return dmin, meta

# ------------------ Simple placeholder maneuver ------------------

def generate_safe_tle(original_tle: str, dv_mps: float) -> str:
    """
    Placeholder: retrograde tiny Δv -> increase mean motion slightly to de-sync TCA.
    1 m/s -> ~ 0.00005 rev/day (demo-friendly). Adjust as needed.
    """
    name, L1, L2 = normalize_tle_block(original_tle)
    delta_rev_per_day = dv_mps * 0.00005
    new_L2 = adjust_mean_motion_l2(L2, delta_rev_per_day)
    out_name = name if name != "UNKNOWN" else "SAFE"
    return f"{out_name}\n{L1}\n{new_L2}"
