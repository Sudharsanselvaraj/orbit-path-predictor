from fastapi import FastAPI, Body
from pydantic import BaseModel
from typing import Optional

from app.model import predict_safe_path

app = FastAPI(title="AI Path Trajectory Predictor", version="0.2.0")

class PredictRequest(BaseModel):
    satellite_tle: str
    debris_tle: str
    horizon_minutes: Optional[int] = 180
    step_seconds: Optional[int] = 60

@app.get("/")
def root():
    return {"status": "ok", "service": "ai-path-trajectory-predictor", "post": "/predict"}

@app.post("/predict")
def predict(req: PredictRequest = Body(...)):
    return predict_safe_path(
        satellite_tle=req.satellite_tle,
        debris_tle=req.debris_tle,
        horizon_minutes=req.horizon_minutes,
        step_seconds=req.step_seconds
    )
