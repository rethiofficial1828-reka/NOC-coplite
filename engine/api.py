from fastapi import FastAPI, HTTPException, Query
import sqlite3
import pandas as pd
import os
from .model import RiskPredictor

app = FastAPI(title="NOC Copilot Predictive Engine API")

# Initialize the predictor
predictor = RiskPredictor()

from config.settings import DB_PATH, DEVICE_REGISTRY, DEVICE_NAMES


@app.get("/devices")
def list_devices():
    """Return the full device registry."""
    return {"devices": DEVICE_REGISTRY}


@app.get("/predict")
def predict_endpoint(interface: str = Query("Branch3-Uplink", description="Interface name to analyze")):
    if not os.path.exists(DB_PATH):
        # Database does not exist yet; return default healthy values
        return {
            "interface": interface,
            "risk_score": 0.0,
            "time_to_impact": -1.0,
            "contributing_signals": [],
            "status": "waiting_for_telemetry",
            "metrics": {
                "utilization": 0.0,
                "latency": 0.0,
                "jitter": 0.0,
                "drops": 0.0,
                "routing_flaps": 0
            }
        }
        
    try:
        conn = sqlite3.connect(DB_PATH)
        try:
            # Fetch the last 30 samples of telemetry
            df = pd.read_sql_query("""
                SELECT timestamp, utilization, latency, jitter, drops, routing_flaps 
                FROM metrics 
                WHERE interface = ? 
                ORDER BY timestamp DESC LIMIT 30
            """, conn, params=(interface,))
        finally:
            conn.close()
        
        if df.empty:
            return {
                "interface": interface,
                "risk_score": 0.0,
                "time_to_impact": -1.0,
                "contributing_signals": [],
                "status": "no_telemetry_found",
                "metrics": {
                    "utilization": 0.0,
                    "latency": 0.0,
                    "jitter": 0.0,
                    "drops": 0.0,
                    "routing_flaps": 0
                }
            }
            
        # Reverse the df to make it chronological (oldest to newest)
        df = df.iloc[::-1].reset_index(drop=True)
        
        # Latest metrics for display
        latest_row = df.iloc[-1]
        latest_metrics = {
            "utilization": float(latest_row["utilization"]),
            "latency": float(latest_row["latency"]),
            "jitter": float(latest_row["jitter"]),
            "drops": float(latest_row["drops"]),
            "routing_flaps": int(latest_row["routing_flaps"])
        }
        
        # Run prediction
        result = predictor.predict(df)
        
        return {
            "interface": interface,
            "risk_score": result["risk_score"],
            "time_to_impact": result["time_to_impact"],
            "contributing_signals": result["contributing_signals"],
            "status": "active",
            "metrics": latest_metrics
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction error: {str(e)}")

@app.get("/health")
def health():
    return {"status": "ok"}
