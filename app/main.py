from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from app.model import predict_safe_path

app = FastAPI(title="AI Path Trajectory Predictor", version="0.3.0")

# Enable CORS for all origins (adjust for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class PredictRequest(BaseModel):
    satellite_tle: str
    debris_tle: str
    horizon_minutes: Optional[int] = 60
    step_seconds: Optional[int] = 30

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
