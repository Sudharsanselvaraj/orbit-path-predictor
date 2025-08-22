import re
import math
from datetime import datetime, timedelta
from typing import Tuple, List, Dict
from sgp4.api import Satrec, jday

_TLE_PAIR_REGEX = re.compile(
    r"(1\s+\d{5}[U ]\s.*?)(2\s+\d{5}\s.*)",
    flags=re.IGNORECASE | re.DOTALL
)

def normalize_tle_block(tle_text: str) -> Tuple[str, str, str]:
    raw = tle_text.strip()
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

    if len(lines) >= 2 and lines[0].startswith("1 ") and lines[1].startswith("2 "):
        return "UNKNOWN", lines[0], lines[1]
    if len(lines) >= 3 and lines[1].startswith("1 ") and lines[2].startswith("2 "):
        return lines[0], lines[1], lines[2]

    m = _TLE_PAIR_REGEX.search(raw.replace("\n", " "))
    if not m:
        raise ValueError("Invalid TLE format.")
    return "UNKNOWN", m.group(1).strip(), m.group(2).strip()

def tle_checksum(line: str) -> str:
    s = 0
    for c in line[:68]:
        if c.isdigit():
            s += int(c)
        elif c == '-':
            s += 1
    return str(s % 10)

def replace_col_span(s: str, start: int, end: int, value: str) -> str:
    start -= 1
    return s[:start] + value + s[end:]

def adjust_mean_motion_l2(line2: str, delta_rev_per_day: float) -> str:
    current_mm = float(line2[52:63])
    new_mm = current_mm + delta_rev_per_day
    mm_str = f"{new_mm:11.8f}"

    l2 = replace_col_span(line2, 53, 63, mm_str)
    if len(l2) < 69:
        l2 = l2.ljust(68) + "0"
    l2 = l2[:68] + tle_checksum(l2)
    return l2

def propagate_positions(tle_text: str, minutes: int = 180, step_s: int = 60) -> List[Dict]:
    _, L1, L2 = normalize_tle_block(tle_text)
    sat = Satrec.twoline2rv(L1, L2)

    t0 = datetime.utcnow()
    out = []
    for k in range(0, minutes * 60 + 1, step_s):
        t = t0 + timedelta(seconds=k)
        jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond / 1e6)
        e, r, v = sat.sgp4(jd, fr)
        if e == 0:
            out.append({"t": t.isoformat() + "Z", "r": [float(x) for x in r], "v": [float(x) for x in v]})
    return out

def nearest_approach_km(path_a: List[Dict], path_b: List[Dict]) -> Tuple[float, Dict]:
    n = min(len(path_a), len(path_b))
    dmin = float("inf")
    kmin = -1
    for i in range(n):
        ax, ay, az = path_a[i]["r"]
        bx, by, bz = path_b[i]["r"]
        d = math.sqrt((ax - bx)**2 + (ay - by)**2 + (az - bz)**2)
        if d < dmin:
            dmin = d
            kmin = i
    meta = {}
    if kmin >= 0:
        meta = {"time": path_a[kmin]["t"], "sat_r": path_a[kmin]["r"], "deb_r": path_b[kmin]["r"], "index": kmin}
    return dmin, meta

def generate_safe_tle(original_tle: str, dv_mps: float) -> str:
    name, L1, L2 = normalize_tle_block(original_tle)
    delta_rev_per_day = dv_mps * 0.00005
    new_L2 = adjust_mean_motion_l2(L2, delta_rev_per_day)
    out_name = name if name != "UNKNOWN" else "SAFE"
    return f"{out_name}\n{L1}\n{new_L2}"
