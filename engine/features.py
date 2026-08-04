import numpy as np
import pandas as pd

def compute_slope(y):
    """
    Computes the linear regression slope of a series y.
    Assumes standard sample intervals.
    """
    if len(y) < 2:
        return 0.0
    x = np.arange(len(y))
    slope, _ = np.polyfit(x, y, 1)
    return float(slope)

def extract_features_from_df(df):
    """
    Takes a DataFrame containing the recent window of telemetry.
    Expected columns: utilization, latency, jitter, drops, routing_flaps
    Returns a dictionary of features.
    """
    features = {}
    
    # We expect the DataFrame to be sorted chronologically
    utils = df["utilization"].values
    lats = df["latency"].values
    jits = df["jitter"].values
    drps = df["drops"].values
    flaps = df["routing_flaps"].values
    
    # Current values
    features["utilization_current"] = float(utils[-1]) if len(utils) > 0 else 0.0
    features["latency_current"] = float(lats[-1]) if len(lats) > 0 else 0.0
    features["jitter_current"] = float(jits[-1]) if len(jits) > 0 else 0.0
    features["drops_current"] = float(drps[-1]) if len(drps) > 0 else 0.0
    features["routing_flaps_current"] = int(flaps[-1]) if len(flaps) > 0 else 0
    
    # Rolling averages (last 15 samples ~ 30 seconds)
    w_size = min(len(utils), 15)
    features["utilization_mean_30s"] = float(np.mean(utils[-w_size:])) if w_size > 0 else 0.0
    features["latency_mean_30s"] = float(np.mean(lats[-w_size:])) if w_size > 0 else 0.0
    features["jitter_mean_30s"] = float(np.mean(jits[-w_size:])) if w_size > 0 else 0.0
    features["drops_mean_30s"] = float(np.mean(drps[-w_size:])) if w_size > 0 else 0.0
    
    # Slopes (last 30 samples ~ 60 seconds)
    w_slope = min(len(utils), 30)
    features["utilization_slope_60s"] = compute_slope(utils[-w_slope:]) if w_slope > 1 else 0.0
    features["latency_slope_60s"] = compute_slope(lats[-w_slope:]) if w_slope > 1 else 0.0
    features["jitter_slope_60s"] = compute_slope(jits[-w_slope:]) if w_slope > 1 else 0.0
    features["drops_slope_60s"] = compute_slope(drps[-w_slope:]) if w_slope > 1 else 0.0
    
    # Sum of routing flaps in last 60s
    features["routing_flaps_sum_60s"] = int(np.sum(flaps[-w_slope:])) if w_slope > 0 else 0
    
    # Baseline deltas (assuming healthy baselines: util=45%, lat=20ms, jit=3ms)
    features["utilization_delta_baseline"] = features["utilization_current"] - 45.0
    features["latency_delta_baseline"] = features["latency_current"] - 20.0
    features["jitter_delta_baseline"] = features["jitter_current"] - 3.0
    
    return features
