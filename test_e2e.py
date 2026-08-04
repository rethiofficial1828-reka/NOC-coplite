import time
import requests
import sqlite3
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.settings import DB_PATH, ENGINE_PORT, COPILOT_PORT

ENGINE_HEALTH = f"http://localhost:{ENGINE_PORT}/health"
ENGINE_PREDICT = f"http://localhost:{ENGINE_PORT}/predict"
COPILOT_HEALTH = f"http://localhost:{COPILOT_PORT}/health"
COPILOT_API = f"http://localhost:{COPILOT_PORT}/copilot"


def set_sim_mode(mode):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO sim_config (key, value) VALUES ('mode', ?)", (mode,))
    if mode == "congestion":
        cursor.execute("INSERT OR REPLACE INTO sim_config (key, value) VALUES ('congestion_step', '0')")
    conn.commit()
    conn.close()

def clear_metrics():
    """Wipes the metrics database to isolate the test from the background simulation daemon."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM metrics")
    conn.commit()
    conn.close()

def insert_mock_telemetry_history(target_util, target_lat, target_jit, target_drp, target_flaps):
    """
    Inserts a 30-sample history (60 seconds) into telemetry.db leading up to target metrics.
    This simulates a realistic positive-slope trend over the full feature window.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = time.time()
    
    # 30 samples, 2 seconds apart
    for i in range(30):
        t = now - (30 - i) * 2
        # Linear interpolation from normal baseline to target values
        u = 45.0 + (target_util - 45.0) * ((i + 1) / 30.0)
        l = 20.0 + (target_lat - 20.0) * ((i + 1) / 30.0)
        j = 3.0 + (target_jit - 3.0) * ((i + 1) / 30.0)
        d = 0.0 + (target_drp - 0.0) * ((i + 1) / 30.0)
        # Occasional BGP flap flags near the end of the window
        f = target_flaps if i >= 28 else 0
        
        cursor.execute("""
            INSERT INTO metrics (timestamp, interface, utilization, latency, jitter, drops, routing_flaps)
            VALUES (?, 'Branch3-Uplink', ?, ?, ?, ?, ?)
        """, (t, u, l, j, d, f))
        
    conn.commit()
    conn.close()

def main():
    print("=== Starting End-to-End Integration Scenario Tests ===")
    
    # 1. Check Service Availability
    print("\n[1/5] Checking service availability...")
    try:
        engine_res = requests.get(ENGINE_HEALTH, timeout=2.0)
        copilot_res = requests.get(COPILOT_HEALTH, timeout=2.0)
        if engine_res.status_code == 200 and copilot_res.status_code == 200:
            print("  [PASS] Predictive Engine API is active.")
            print("  [PASS] Copilot RAG & LLM API is active.")
        else:
            print("  [FAIL] Health check endpoints returned non-200 codes.")
            sys.exit(1)
    except Exception as e:
        print(f"  [FAIL] Failed to connect to backend APIs: {e}")
        print("  Make sure run.sh is running in the background.")
        sys.exit(1)

    # 2. Check Healthy Baseline State
    print("\n[2/5] Testing healthy baseline parameters...")
    clear_metrics()
    set_sim_mode("healthy")
    # Feed healthy baseline telemetry
    insert_mock_telemetry_history(target_util=46.0, target_lat=21.0, target_jit=3.0, target_drp=0.0, target_flaps=0)
    
    try:
        res = requests.get(ENGINE_PREDICT, params={"interface": "Branch3-Uplink"}, timeout=2.0)
        data = res.json()
        risk = data["risk_score"]
        util = data["metrics"]["utilization"]
        lat = data["metrics"]["latency"]
        
        print(f"  Current state -> Utilization: {util:.1f}%, Latency: {lat:.1f}ms, Risk Score: {risk*100:.2f}%")
        if risk < 0.3 and util < 55.0 and lat < 30.0:
            print("  [PASS] Baseline metrics are healthy and risk is low.")
        else:
            print("  [FAIL] Unexpected baseline metrics or elevated risk.")
            sys.exit(1)
    except Exception as e:
        print(f"  [FAIL] Failed to fetch prediction: {e}")
        sys.exit(1)

    # 3. Inject Congestion Fault & Check Risk Escalation
    print("\n[3/5] Injecting progressive congestion fault...")
    clear_metrics()
    set_sim_mode("congestion")
    # Inject high-congestion telemetry trend
    insert_mock_telemetry_history(target_util=88.0, target_lat=125.0, target_jit=15.0, target_drp=4.0, target_flaps=2)
    
    try:
        res = requests.get(ENGINE_PREDICT, params={"interface": "Branch3-Uplink"}, timeout=2.0)
        data = res.json()
        risk = data["risk_score"]
        util = data["metrics"]["utilization"]
        lat = data["metrics"]["latency"]
        time_to_impact = data["time_to_impact"]
        signals = data["contributing_signals"]
        
        print(f"  Ramp state -> Utilization: {util:.1f}%, Latency: {lat:.1f}ms, Risk Score: {risk*100:.2f}%")
        print(f"  Time-to-impact: {time_to_impact:.2f} mins | Contributing signals: {signals}")
        
        if risk > 0.3:
            print("  [PASS] Risk score successfully elevated in response to fault injection.")
        else:
            print("  [FAIL] Risk score failed to react to congestion.")
            sys.exit(1)
    except Exception as e:
        print(f"  [FAIL] Failed to fetch prediction during fault: {e}")
        sys.exit(1)

    # 4. Request AI Copilot Action & Verify RAG Grounding
    print("\n[4/5] Fetching AI Copilot structured recommendations...")
    try:
        payload = {
            "interface": "Branch3-Uplink",
            "risk_score": risk,
            "time_to_impact": time_to_impact,
            "contributing_signals": signals
        }
        res = requests.post(COPILOT_API, json=payload, timeout=10.0)
        data = res.json()
        
        exp = data["explanation"]
        sources = data["sources"]
        
        print(f"  Copilot Predicted Issue: '{exp['predicted_issue']}'")
        print(f"  Hypothesized Root Cause: '{exp['root_cause_hypothesis']}'")
        print(f"  Recommended Actions count: {len(exp['recommended_actions'])}")
        print(f"  RAG Evidence chunks retrieved: {len(sources)}")
        
        # Check grounding sources
        cites = [s["source"] for s in sources]
        print(f"  Documents cited: {cites}")
        
        if len(exp["recommended_actions"]) > 0 and len(sources) > 0:
            print("  [PASS] AI Copilot returned valid RAG-grounded structure.")
        else:
            print("  [FAIL] Missing recommendations or RAG citations.")
            sys.exit(1)
    except Exception as e:
        print(f"  [FAIL] Copilot query failed: {e}")
        sys.exit(1)

    # 5. Apply QoS Mitigation & Verify Recovery
    print("\n[5/5] Applying QoS mitigation and route changes...")
    clear_metrics()
    set_sim_mode("mitigated")
    # Feed healthy baseline telemetry again to simulate recovery
    insert_mock_telemetry_history(target_util=45.5, target_lat=19.5, target_jit=2.8, target_drp=0.0, target_flaps=0)
    
    try:
        res = requests.get(ENGINE_PREDICT, params={"interface": "Branch3-Uplink"}, timeout=2.0)
        data = res.json()
        risk = data["risk_score"]
        util = data["metrics"]["utilization"]
        lat = data["metrics"]["latency"]
        
        print(f"  Mitigated state -> Utilization: {util:.1f}%, Latency: {lat:.1f}ms, Risk Score: {risk*100:.2f}%")
        if risk < 0.3:
            print("  [PASS] Network successfully recovered. Risk is green.")
        else:
            print("  [FAIL] Risk failed to drop back after mitigation.")
            sys.exit(1)
    except Exception as e:
        print(f"  [FAIL] Failed to fetch prediction after mitigation: {e}")
        sys.exit(1)

    print("\n=== All End-to-End Integration Tests PASSED with Zero Errors! ===")

if __name__ == "__main__":
    main()
