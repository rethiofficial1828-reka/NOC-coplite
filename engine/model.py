import os
import sqlite3
import pandas as pd
import numpy as np
import xgboost as xgb
from .features import extract_features_from_df

MODEL_PATH = "noc-copilot/data/xgboost_model.json"
DATA_PATH = "noc-copilot/data/synthetic_telemetry.csv"

def preprocess_training_data():
    """
    Loads the synthetic dataset, computes rolling window features for each timestamp
    within each scenario, and builds the training matrix.
    """
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"Training dataset not found at {DATA_PATH}. Run generate_dataset.py first.")
        
    df = pd.read_csv(DATA_PATH)
    
    # Each scenario has 450 samples
    scenario_len = 450
    num_scenarios = len(df) // scenario_len
    
    X_list = []
    y_list = []
    
    for s_idx in range(num_scenarios):
        sc_df = df.iloc[s_idx * scenario_len : (s_idx + 1) * scenario_len].copy().reset_index(drop=True)
        # We need a history window of at least 30 samples to compute features
        for i in range(30, scenario_len):
            window_df = sc_df.iloc[i-30 : i]
            features = extract_features_from_df(window_df)
            X_list.append(features)
            y_list.append(sc_df.loc[i, "label"])
            
    X = pd.DataFrame(X_list)
    y = np.array(y_list)
    return X, y

def train_model():
    print("Preprocessing synthetic data for model training...")
    X, y = preprocess_training_data()
    
    print(f"Training XGBoost classifier on {len(X)} samples...")
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        random_state=42,
        eval_metric="logloss"
    )
    model.fit(X, y)
    
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    model.save_model(MODEL_PATH)
    print(f"Model trained and saved to {MODEL_PATH}")
    
    # Print evaluation metrics
    preds = model.predict(X)
    accuracy = np.mean(preds == y)
    print(f"Training Accuracy: {accuracy:.4f}")

class RiskPredictor:
    def __init__(self):
        self.model = None
        if os.path.exists(MODEL_PATH):
            try:
                self.model = xgb.XGBClassifier()
                self.model.load_model(MODEL_PATH)
                print("Loaded trained XGBoost model.")
            except Exception as e:
                print(f"Failed to load XGBoost model: {e}. Falling back to trend-based heuristics.")

    def predict(self, recent_df):
        """
        Predicts the risk score and time-to-impact.
        recent_df: DataFrame containing the last 30 samples of telemetry.
        """
        features = extract_features_from_df(recent_df)
        
        # Calculate individual signals for explainability
        util_curr = features["utilization_current"]
        util_slope = features["utilization_slope_60s"]
        lat_curr = features["latency_current"]
        lat_slope = features["latency_slope_60s"]
        drp_curr = features["drops_current"]
        flaps_sum = features["routing_flaps_sum_60s"]
        
        # Explainable signal calculations (normalized between 0 and 1)
        congestion_signal = np.clip((util_curr - 45.0) / 50.0 + 3.0 * max(0, util_slope), 0.0, 1.0)
        latency_signal = np.clip((lat_curr - 20.0) / 130.0 + 1.5 * max(0, lat_slope), 0.0, 1.0)
        tunnel_health_signal = np.clip(drp_curr / 10.0, 0.0, 1.0)
        routing_instability_signal = np.clip(flaps_sum / 3.0, 0.0, 1.0)
        
        # Explainable risk formula
        formula_risk = (
            0.4 * congestion_signal +
            0.3 * latency_signal +
            0.2 * tunnel_health_signal +
            0.1 * routing_instability_signal
        )
        
        # Machine learning risk using XGBoost if available
        if self.model:
            try:
                # Convert feature dict to single-row DataFrame
                feat_df = pd.DataFrame([features])
                # Reorder columns to match training set (XGBoost requires consistent ordering)
                # Note: XGBoost model saves the feature names in model.feature_names
                if hasattr(self.model, "feature_names") and self.model.feature_names:
                    feat_df = feat_df[self.model.feature_names]
                prob = self.model.predict_proba(feat_df)[0][1]
                # Combine both: XGBoost gives the prediction, but we anchor it with formula_risk
                # to ensure we don't output high risk if metrics are perfectly normal
                risk_score = float(prob)
            except Exception as e:
                print(f"XGBoost prediction error: {e}. Using trend formula.")
                risk_score = float(formula_risk)
        else:
            risk_score = float(formula_risk)
            
        # Ensure risk score is closely correlated with severity
        if util_curr < 60.0 and lat_curr < 30.0:
            risk_score = min(risk_score, 0.15) # Cap risk if everything is green
            
        # Time-to-impact estimation (minutes) via linear extrapolation
        time_to_impact = -1.0
        candidates = []
        
        # 1. Utilization SLA breach (95%)
        if util_slope > 0.01:
            rem_util = 95.0 - util_curr
            if rem_util > 0:
                steps = rem_util / util_slope
                # 2 seconds per step
                candidates.append((steps * 2) / 60.0)
                
        # 2. Latency SLA breach (150ms)
        if lat_slope > 0.1:
            rem_lat = 150.0 - lat_curr
            if rem_lat > 0:
                steps = rem_lat / lat_slope
                candidates.append((steps * 2) / 60.0)
                
        if candidates:
            time_to_impact = float(np.min(candidates))
            
        # Compile contributing signals
        contributing = []
        if util_slope > 0.1:
            contributing.append(f"utilization rising {util_slope*100:.2f}%/sample")
        elif util_curr > 75.0:
            contributing.append(f"utilization elevated at {util_curr:.1f}%")
            
        if lat_slope > 0.5:
            contributing.append(f"latency trending up (+{lat_slope:.1f}ms/sample)")
        elif lat_curr > 60.0:
            contributing.append(f"latency elevated at {lat_curr:.1f}ms")
            
        if drp_curr > 0.0:
            contributing.append(f"egress drops starting ({drp_curr:.1f} drops/s)")
            
        if flaps_sum > 0:
            contributing.append(f"routing instability detected ({flaps_sum} flaps/min)")
            
        # Default contributing signals if none are active but risk is elevated
        if not contributing and risk_score > 0.3:
            contributing.append("gradual telemetry drift detected")
            
        return {
            "risk_score": float(risk_score),
            "time_to_impact": float(time_to_impact) if time_to_impact > 0 else -1.0,
            "contributing_signals": contributing
        }

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "train":
        train_model()
