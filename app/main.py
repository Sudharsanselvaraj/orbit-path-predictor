from fastapi import FastAPI
from app.model import predict_safe_path

app = FastAPI(title="Satellite Trajectory API")

@app.get("/")
def root():
    return {"message": "🚀 Satellite Trajectory API is running", "endpoints": ["/predict"]}

@app.get("/predict")
def predict(satellite_tle: str, debris_tle: str):
    return predict_safe_path(satellite_tle, debris_tle)
