import pandas as pd
import numpy as np
import os

def generate_scenario(scenario_id, interface, mode="healthy"):
    """
    Generates a 15-minute scenario sampled every 2 seconds.
    Total samples: 450
    """
    np.random.seed(scenario_id)
    timestamps = np.arange(0, 450 * 2, 2)
    
    utilization = []
    latency = []
    jitter = []
    drops = []
    routing_flaps = []
    
    # Base states
    util = 45.0
    lat = 20.0
    jit = 3.0
    
    congestion_start_idx = 200
    
    for i in range(450):
        if mode == "healthy":
            # Normal fluctuation
            util = np.clip(util + np.random.normal(0, 1.0), 35.0, 55.0)
            lat = np.clip(lat + np.random.normal(0, 0.5), 15.0, 25.0)
            jit = np.clip(jit + np.random.normal(0, 0.2), 1.0, 5.0)
            drp = 0.0
            flaps = 0
            if np.random.random() < 0.01:
                flaps = 1  # Rare single flap
        elif mode == "congestion":
            if i < congestion_start_idx:
                # Normal fluctuation before congestion starts
                util = np.clip(util + np.random.normal(0, 1.0), 35.0, 55.0)
                lat = np.clip(lat + np.random.normal(0, 0.5), 15.0, 25.0)
                jit = np.clip(jit + np.random.normal(0, 0.2), 1.0, 5.0)
                drp = 0.0
                flaps = 0
            else:
                # Congestion ramp
                step = i - congestion_start_idx
                # Linear ramp in utilization from ~50% to ~98%
                util = np.clip(util + 0.25 + np.random.normal(0, 0.5), 35.0, 99.5)
                # Exponential-like ramp in latency as queues fill up
                lat = np.clip(lat + 0.1 * np.exp(step * 0.02) + np.random.normal(0, 1.0), 15.0, 300.0)
                # Jitter increases with congestion
                jit = np.clip(jit + 0.05 * np.exp(step * 0.015) + np.random.normal(0, 0.5), 1.0, 30.0)
                # Drops start occurring once latency exceeds 80ms
                drp = 0.0
                if lat > 80.0:
                    drp = np.clip((lat - 80.0) * 0.1 + np.random.normal(0, 0.5), 0.0, 15.0)
                # Occasional routing flaps under heavy load
                flaps = 0
                if step > 100 and np.random.random() < 0.05:
                    flaps = np.random.choice([1, 2])
        
        utilization.append(util)
        latency.append(lat)
        jitter.append(jit)
        drops.append(drp)
        routing_flaps.append(flaps)
        
    df = pd.DataFrame({
        "timestamp": timestamps,
        "interface": [interface] * 450,
        "utilization": utilization,
        "latency": latency,
        "jitter": jitter,
        "drops": drops,
        "routing_flaps": routing_flaps
    })
    
    # Label generation:
    # Breach threshold: utilization >= 95.0 or latency >= 150.0
    # Predictive label (1): Will breach in the next 90 seconds (45 samples)
    df["is_breaching"] = ((df["utilization"] >= 95.0) | (df["latency"] >= 150.0)).astype(int)
    
    label = np.zeros(len(df))
    for idx in range(len(df)):
        # Look ahead 45 samples (90 seconds)
        lookahead = df["is_breaching"].iloc[idx : idx + 45]
        if lookahead.max() == 1:
            label[idx] = 1
            
    df["label"] = label.astype(int)
    df = df.drop(columns=["is_breaching"])
    return df

def main():
    print("Generating synthetic network telemetry dataset...")
    dfs = []
    # Generate 5 healthy and 5 congestion scenarios
    for s_id in range(5):
        dfs.append(generate_scenario(s_id, "Branch3-Uplink", mode="healthy"))
    for s_id in range(5, 10):
        dfs.append(generate_scenario(s_id, "Branch3-Uplink", mode="congestion"))
        
    df = pd.concat(dfs, ignore_index=True)
    os.makedirs("noc-copilot/data", exist_ok=True)
    df.to_csv("noc-copilot/data/synthetic_telemetry.csv", index=False)
    print(f"Dataset generated with {len(df)} samples and saved to noc-copilot/data/synthetic_telemetry.csv")

if __name__ == "__main__":
    main()
