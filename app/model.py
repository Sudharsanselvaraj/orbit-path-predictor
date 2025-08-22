import math
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple
from sgp4.api import Satrec, jday

# -------------------------------
# Thresholds
# -------------------------------
LEO_CA_THRESHOLD_KM = 5.0
GEO_CA_THRESHOLD_KM = 25.0

# -------------------------------
# Helpers
# -------------------------------
def sanitize_vector(vec: List[float]) -> List[float]:
    """Replace invalid float values with 0.0"""
    return [0.0 if math.isinf(x) or math.isnan(x) else x for x in vec]

def regime_from_mean_motion(mm_rev_per_day: float) -> str:
    if mm_rev_per_day > 10:
        return "LEO"
    if mm_rev_per_day < 2:
        return "GEO"
    return "MEO"

def normalize_tle_block(tle_text: str) -> Tuple[str, str, str]:
    """Normalize TLE block, return (name, line1, line2)"""
    lines = [l.strip() for l in tle_text.strip().splitlines() if l.strip()]
    if len(lines) == 3 and lines[1].startswith("1 ") and lines[2].startswith("2 "):
        return lines[0], lines[1], lines[2]
    if len(lines) == 2 and lines[0].startswith("1 ") and lines[1].startswith("2 "):
        return "UNKNOWN", lines[0], lines[1]
    raise ValueError("Invalid TLE format")

def validate_tle(tle_text: str) -> Tuple[str, str, str]:
    """Validate TLE lines"""
    name, L1, L2 = normalize_tle_block(tle_text)
    if len(L1) < 68 or len(L2) < 68:
        raise ValueError("TLE lines too short")
    return name, L1, L2

def propagate_positions(tle_text: str, minutes: int = 60, step_s: int = 30) -> List[Dict]:
    """Propagate positions for a TLE"""
    try:
        name, L1, L2 = validate_tle(tle_text)
        sat = Satrec.twoline2rv(L1, L2)
    except Exception:
        return []

    out = []
    t0 = datetime.utcnow()
    for k in range(0, minutes*60 + 1, step_s):
        t = t0 + timedelta(seconds=k)
        jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond/1e6)
        e, r, v = sat.sgp4(jd, fr)
        if e == 0:
            out.append({"t": t.isoformat()+"Z", "r": sanitize_vector(r), "v": sanitize_vector(v)})
    return out

def nearest_approach_km(path_a: List[Dict], path_b: List[Dict]) -> Tuple[float, Dict]:
    """Compute closest approach"""
    n = min(len(path_a), len(path_b))
    dmin = float("inf")
    kmin = -1
    for i in range(n):
        ax, ay, az = path_a[i]["r"]
        bx, by, bz = path_b[i]["r"]
        d = math.sqrt((ax-bx)**2 + (ay-by)**2 + (az-bz)**2)
        if d < dmin:
            dmin = d
            kmin = i
    meta = {}
    if kmin >= 0:
        meta = {"time": path_a[kmin]["t"], "sat_r": path_a[kmin]["r"], "deb_r": path_b[kmin]["r"], "index": kmin}
    return dmin, meta

def generate_safe_tle(original_tle: str, dv_mps: float) -> str:
    """Adjust TLE mean motion slightly"""
    try:
        name, L1, L2 = normalize_tle_block(original_tle)
        current_mm = float(L2[52:63])
        new_mm = current_mm + dv_mps * 0.00005
        mm_str = f"{new_mm:11.8f}"
        L2 = L2[:52] + mm_str + L2[63:]
        return f"{name}\n{L1}\n{L2}"
    except Exception:
        return original_tle

# -------------------------------
# Main function
# -------------------------------
def predict_safe_path(
    satellite_tle: str,
    debris_tle: str,
    horizon_minutes: int = 60,
    step_seconds: int = 30
) -> Dict[str, Any]:
    """Predict closest approach and safe TLE path"""

    debug_info = {"errors": []}

    # 1) Validate
    try:
        sat_name, sat_l1, sat_l2 = validate_tle(satellite_tle)
        deb_name, deb_l1, deb_l2 = validate_tle(debris_tle)
    except Exception as e:
        return {"error": f"TLE validation failed: {e}"}

    # 2) Regime
    try:
        mm_sat = float(sat_l2[52:63])
        regime = regime_from_mean_motion(mm_sat)
    except Exception:
        regime = "UNKNOWN"
        debug_info["errors"].append("Mean motion parsing failed")

    step_s_adjusted = step_seconds if regime != "GEO" else max(300, step_seconds)

    # 3) Propagate
    sat_path = propagate_positions(f"{sat_name}\n{sat_l1}\n{sat_l2}", minutes=horizon_minutes, step_s=step_s_adjusted)
    deb_path = propagate_positions(f"{deb_name}\n{deb_l1}\n{deb_l2}", minutes=horizon_minutes, step_s=step_s_adjusted)
    if not sat_path:
        debug_info["errors"].append("Satellite propagation returned 0 points")
    if not deb_path:
        debug_info["errors"].append("Debris propagation returned 0 points")

    # 4) Closest approach
    dmin_km, meta = nearest_approach_km(sat_path, deb_path)
    risky = False
    threshold = LEO_CA_THRESHOLD_KM if regime == "LEO" else GEO_CA_THRESHOLD_KM
    if dmin_km != float("inf"):
        risky = dmin_km <= threshold

    # 5) Maneuver suggestion
    if risky:
        maneuver = {"type": "retrograde_burn", "recommended_dv_mps": 1.0,
                    "note": "Small along-track tweak to desynchronize TCA."}
        safe_tle = generate_safe_tle(f"{sat_name}\n{sat_l1}\n{sat_l2}", maneuver["recommended_dv_mps"])
    else:
        maneuver = {"type": "no_action", "recommended_dv_mps": 0.0,
                    "note": "Separation above threshold."}
        safe_tle = f"{sat_name}\n{sat_l1}\n{sat_l2}"

    return {
        "risk": {
            "min_distance_km": round(dmin_km, 3) if dmin_km != float("inf") else None,
            "tca": meta.get("time"),
            "regime": regime,
            "threshold_km": threshold,
            "risky": risky
        },
        "maneuver": maneuver,
        "tle_output": {
            "satellite_tle": f"{sat_name}\n{sat_l1}\n{sat_l2}",
            "debris_tle": f"{deb_name}\n{deb_l1}\n{deb_l2}",
            "predicted_safe_tle": safe_tle
        },
        "paths": {
            "satellite_xyz_km": [p["r"] for p in sat_path],
            "debris_xyz_km": [p["r"] for p in deb_path]
        },
        "debug": debug_info
    }
