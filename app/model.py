from typing import Dict, Any, List
from datetime import datetime, timedelta
import math
from sgp4.api import Satrec, jday

from app.utils import (
    normalize_tle_block,
    validate_tle,
    generate_safe_tle
)

# Thresholds
LEO_CA_THRESHOLD_KM = 5.0
GEO_CA_THRESHOLD_KM = 25.0

def sanitize_vector(vec: List[float]) -> List[float]:
    """Replace invalid float values with 0.0"""
    return [0.0 if math.isinf(x) or math.isnan(x) else x for x in vec]

def regime_from_mean_motion(mm_rev_per_day: float) -> str:
    if mm_rev_per_day > 10:
        return "LEO"
    if mm_rev_per_day < 2:
        return "GEO"
    return "MEO"

def propagate_positions(tle_text: str, minutes: int, step_s: int) -> List[Dict]:
    """Propagate satellite positions with safe handling for GEO"""
    _, L1, L2 = normalize_tle_block(tle_text)
    sat = Satrec.twoline2rv(L1, L2)
    t0 = datetime.utcnow()
    out = []

    for k in range(0, minutes*60 + 1, step_s):
        t = t0 + timedelta(seconds=k)
        jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond/1e6)
        e, r, v = sat.sgp4(jd, fr)
        if e == 0:
            r = sanitize_vector(r)
            v = sanitize_vector(v)
            out.append({"t": t.isoformat()+"Z", "r": r, "v": v})
    return out

def nearest_approach_km(path_a: List[Dict], path_b: List[Dict]) -> (float, Dict):
    """Compute closest approach between two paths"""
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

def predict_safe_path(
    satellite_tle: str,
    debris_tle: str,
    horizon_minutes: int = 60,
    step_seconds: int = 30
) -> Dict[str, Any]:
    """Predict closest approach and safe TLE path for any regime"""

    # --- 1) Validate TLEs ---
    try:
        sat_name, sat_l1, sat_l2 = validate_tle(satellite_tle)
        deb_name, deb_l1, deb_l2 = validate_tle(debris_tle)
    except Exception as e:
        return {"error": f"TLE validation failed: {str(e)}"}

    # --- 2) Determine regime and adjust step size ---
    mm_sat = float(sat_l2[52:63])
    regime = regime_from_mean_motion(mm_sat)
    step_s_adjusted = step_seconds
    if regime == "GEO":
        step_s_adjusted = max(300, step_seconds)  # GEO needs larger steps

    # --- 3) Propagate ---
    try:
        sat_path = propagate_positions(f"{sat_name}\n{sat_l1}\n{sat_l2}",
                                      minutes=horizon_minutes,
                                      step_s=step_s_adjusted)
        deb_path = propagate_positions(f"{deb_name}\n{deb_l1}\n{deb_l2}",
                                      minutes=horizon_minutes,
                                      step_s=step_s_adjusted)
    except Exception as e:
        return {"error": f"Propagation failed: {str(e)}"}

    # --- 4) Closest approach ---
    try:
        dmin_km, meta = nearest_approach_km(sat_path, deb_path)
        if math.isinf(dmin_km) or math.isnan(dmin_km):
            dmin_km = -1.0
    except Exception as e:
        return {"error": f"Closest approach calculation failed: {str(e)}"}

    # --- 5) Risk assessment ---
    threshold = LEO_CA_THRESHOLD_KM if regime == "LEO" else GEO_CA_THRESHOLD_KM
    risky = dmin_km <= threshold and dmin_km >= 0

    # --- 6) Maneuver suggestion ---
    if risky:
        maneuver = {"type": "retrograde_burn", "recommended_dv_mps": 1.0,
                    "note": "Tiny along-track tweak to desynchronize the TCA."}
        safe_tle = generate_safe_tle(f"{sat_name}\n{sat_l1}\n{sat_l2}",
                                     dv_mps=maneuver["recommended_dv_mps"])
    else:
        maneuver = {"type": "no_action", "recommended_dv_mps": 0.0,
                    "note": "Separation above threshold."}
        safe_tle = f"{sat_name}\n{sat_l1}\n{sat_l2}"

    return {
        "risk": {
            "min_distance_km": round(dmin_km, 3),
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
        }
    }
