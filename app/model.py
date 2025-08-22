import pickle
from app.utils import propagate_orbit, generate_safe_tle

# Load the trained model
with open("models/maneuver_model.pkl", "rb") as f:
    model = pickle.load(f)

def predict_safe_path(satellite_tle, debris_tle):
    """Predict safe trajectory maneuver."""
    # Step 1: Propagate original orbits
    sat_path = propagate_orbit(satellite_tle)
    debris_path = propagate_orbit(debris_tle)

    # Step 2: Prepare features (replace with real feature engineering)
    features = [len(sat_path), len(debris_path)]

    # Step 3: Predict safe maneuver
    safe_path = model.predict([features])[0]

    # Step 4: Generate safe TLE
    new_tle = generate_safe_tle(satellite_tle, safe_path)

    return {
        "satellite_tle": satellite_tle,
        "debris_tle": debris_tle,
        "predicted_safe_tle": new_tle
    }
