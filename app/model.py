from typing import Dict, Any
from app.utils import (
    propagate_positions,
    nearest_approach_km,
    generate_safe_tle,
    normalize_tle_block
)

DEFAULT_HORIZON_MIN = 180
DEFAULT_STEP_SEC = 60
LEO_CA_THRESHOLD_KM = 5.0
GEO_CA_THRESHOLD_KM = 25.0

def _mean_motion_from_tle(tle_text: str) -> float:
    _, _, L2 = normalize_tle_block(tle_text)
    return float(L2[52:63])

def _regime_from_mean_motion(mm_rev_per_day: float) -> str:
    if mm_rev_per_day > 10: return "LEO"
    if mm_rev_per_day < 2:  return "GEO"
    return "MEO"

def predict_safe_path(satellite_tle: str,
                      debris_tle: str,
                      horizon_minutes: int = DEFAULT_HORIZON_MIN,
                      step_seconds: int = DEFAULT_STEP_SEC) -> Dict[str, Any]:
    # 1) Propagate both TLEs
    sat_path = propagate_positions(satellite_tle, minutes=horizon_minutes, step_s=step_seconds)
    deb_path = propagate_positions(debris_tle, minutes=horizon_minutes, step_s=step_seconds)

    # 2) Closest approach
    dmin_km, meta = nearest_approach_km(sat_path, deb_path)

    # 3) Threshold by regime
    mm = _mean_motion_from_tle(satellite_tle)
    regime = _regime_from_mean_motion(mm)
    threshold = LEO_CA_THRESHOLD_KM if regime == "LEO" else GEO_CA_THRESHOLD_KM
    risky = dmin_km <= threshold

    # 4) Maneuver -> new TLE
    if risky:
        maneuver = {
            "type": "retrograde_burn",
            "recommended_dv_mps": 1.0,
            "note": "Tiny along-track tweak to desynchronize the TCA."
        }
        safe_tle = generate_safe_tle(satellite_tle, dv_mps=maneuver["recommended_dv_mps"])
    else:
        maneuver = {
            "type": "no_action",
            "recommended_dv_mps": 0.0,
            "note": "Separation above threshold."
        }
        safe_tle = satellite_tle

    # 5) Return three TLEs
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
            "satellite_tle": satellite_tle,
            "debris_tle": debris_tle,
            "predicted_safe_tle": safe_tle
        },
        "paths": {
            "satellite_xyz_km": [p["r"] for p in sat_path],
            "debris_xyz_km": [p["r"] for p in deb_path]
        }
    }
