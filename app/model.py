# model.py
from typing import Dict, Any
from app.utils import propagate_positions, nearest_approach_km, generate_safe_tle, validate_tle

LEO_CA_THRESHOLD_KM = 5.0
GEO_CA_THRESHOLD_KM = 25.0

def predict_safe_path(
    satellite_tle: str,
    debris_tle: str,
    horizon_minutes: int = 60,
    step_seconds: int = 30
) -> Dict[str, Any]:

    # --- Validate TLEs ---
    try:
        sat_name, sat_l1, sat_l2 = validate_tle(satellite_tle)
        deb_name, deb_l1, deb_l2 = validate_tle(debris_tle)
    except Exception as e:
        return {"error": f"TLE validation failed: {str(e)}", "risk": {}, "maneuver": {}, "tle_output": {}, "paths": {}}

    # --- Propagate paths ---
    try:
        sat_path = propagate_positions(f"{sat_name}\n{sat_l1}\n{sat_l2}", minutes=horizon_minutes, step_s=step_seconds)
        deb_path = propagate_positions(f"{deb_name}\n{deb_l1}\n{deb_l2}", minutes=horizon_minutes, step_s=step_seconds)
    except Exception as e:
        return {"error": f"Propagation failed: {str(e)}", "risk": {}, "maneuver": {}, "tle_output": {}, "paths": {}}

    # --- Closest approach ---
    try:
        dmin_km, meta = nearest_approach_km(sat_path, deb_path)
        if dmin_km < 0 or dmin_km == float("inf") or dmin_km != dmin_km:  # NaN
            dmin_km = -1.0
            meta = {}
    except Exception as e:
        return {"error": f"Closest approach failed: {str(e)}", "risk": {}, "maneuver": {}, "tle_output": {}, "paths": {}}

    # --- Regime & threshold ---
    try:
        mm = float(sat_l2[52:63])
        regime = "LEO" if mm > 10 else "GEO" if mm < 2 else "MEO"
        threshold = LEO_CA_THRESHOLD_KM if regime == "LEO" else GEO_CA_THRESHOLD_KM
        risky = dmin_km >= 0 and dmin_km <= threshold
    except Exception as e:
        return {"error": f"Regime calculation failed: {str(e)}", "risk": {}, "maneuver": {}, "tle_output": {}, "paths": {}}

    # --- Maneuver & safe TLE ---
    if risky:
        maneuver = {
            "type": "retrograde_burn",
            "recommended_dv_mps": 1.0,
            "note": "Tiny along-track tweak to desynchronize the TCA."
        }
        safe_tle = generate_safe_tle(f"{sat_name}\n{sat_l1}\n{sat_l2}", dv_mps=maneuver["recommended_dv_mps"])
    else:
        maneuver = {
            "type": "no_action",
            "recommended_dv_mps": 0.0,
            "note": "Separation above threshold."
        }
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
