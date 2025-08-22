from typing import Dict, Any
from app.utils import (
    propagate_positions,
    nearest_approach_km,
    generate_safe_tle,
    normalize_tle_block
)

LEO_CA_THRESHOLD_KM = 5.0
GEO_CA_THRESHOLD_KM = 25.0

def _mean_motion_from_tle(tle_text: str) -> float:
    _, _, L2 = normalize_tle_block(tle_text)
    return float(L2[52:63])

def _regime_from_mean_motion(mm_rev_per_day: float) -> str:
    if mm_rev_per_day > 10: return "LEO"
    if mm_rev_per_day < 2: return "GEO"
    return "MEO"

def predict_safe_path(satellite_tle, debris_tle, horizon_minutes=60, step_seconds=30):
    from app.utils import propagate_positions, nearest_approach_km, generate_safe_tle, validate_tle

    # 1) Validate TLEs first
    try:
        sat_name, sat_l1, sat_l2 = validate_tle(satellite_tle)
        deb_name, deb_l1, deb_l2 = validate_tle(debris_tle)
    except Exception as e:
        return {"error": f"TLE validation failed: {str(e)}"}

    # 2) Propagate positions safely
    try:
        sat_path = propagate_positions(f"{sat_name}\n{sat_l1}\n{sat_l2}",
                                      minutes=horizon_minutes,
                                      step_s=step_seconds)
    except Exception as e:
        return {"error": f"Satellite propagation failed: {str(e)}"}

    try:
        deb_path = propagate_positions(f"{deb_name}\n{deb_l1}\n{deb_l2}",
                                      minutes=horizon_minutes,
                                      step_s=step_seconds)
    except Exception as e:
        return {"error": f"Debris propagation failed: {str(e)}"}

    # 3) Closest approach
    try:
        dmin_km, meta = nearest_approach_km(sat_path, deb_path)
    except Exception as e:
        return {"error": f"Closest approach calculation failed: {str(e)}"}

    # 4) Regime and threshold
    mm = float(sat_l2[52:63])
    regime = "LEO" if mm > 10 else "GEO" if mm < 2 else "MEO"
    threshold = 5.0 if regime == "LEO" else 25.0
    risky = dmin_km <= threshold

    # 5) Maneuver
    if risky:
        maneuver = {
            "type": "retrograde_burn",
            "recommended_dv_mps": 1.0,
            "note": "Tiny along-track tweak to desynchronize the TCA."
        }
        safe_tle = generate_safe_tle(f"{sat_name}\n{sat_l1}\n{sat_l2}", dv_mps=maneuver["recommended_dv_mps"])
    else:
        maneuver = {"type": "no_action", "recommended_dv_mps": 0.0, "note": "Separation above threshold."}
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
        }
    },
        "paths": {
            "satellite_xyz_km": [p["r"] for p in sat_path],
            "debris_xyz_km": [p["r"] for p in deb_path]
        }
    }
