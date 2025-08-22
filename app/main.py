from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.model import predict_safe_path

app = FastAPI(title="Satellite Trajectory Predictor")

class TLEInput(BaseModel):
    satellite_tle: str
    debris_tle: str

@app.get("/")
def home():
    return {"message": "🚀 Satellite Trajectory Predictor API is running!"}

@app.post("/predict")
def predict(input_data: TLEInput):
    try:
        result = predict_safe_path(input_data.satellite_tle, input_data.debris_tle)
        return {"status": "ok", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
