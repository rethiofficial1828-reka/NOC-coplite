#!/usr/bin/env python3
"""
NOC Copilot - Master Test Runner
Runs ALL test categories and produces a final error summary.

Test Types:
  1. Unit Tests         - Individual function/class correctness
  2. Integration Tests  - API endpoint contracts & HTTP behavior
  3. E2E Scenario Tests - Full lifecycle: healthy -> congestion -> copilot -> mitigate
  4. Edge Case Tests    - Boundary values, empty inputs, malformed data
  5. Stress Tests       - Rapid-fire API calls under load
"""

import os
import sys
import time
import json
import sqlite3
import traceback
import pandas as pd
import numpy as np
import requests

# --- Config ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.settings import DB_PATH, ENGINE_PORT, COPILOT_PORT

ENGINE_URL = f"http://localhost:{ENGINE_PORT}"
COPILOT_URL = f"http://localhost:{COPILOT_PORT}"


# --- Tracking ---
RESULTS = []  # list of (category, name, status, detail)

def record(category, name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    RESULTS.append((category, name, status, detail))
    icon = "✅" if passed else "❌"
    print(f"  {icon} [{status}] {name}")
    if detail and not passed:
        print(f"       ↳ {detail}")

def clear_metrics():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM metrics")
    conn.commit()
    conn.close()

def set_sim_mode(mode):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO sim_config (key, value) VALUES ('mode', ?)", (mode,))
    if mode == "congestion":
        conn.execute("INSERT OR REPLACE INTO sim_config (key, value) VALUES ('congestion_step', '0')")
    conn.commit()
    conn.close()

def insert_mock_telemetry(target_util, target_lat, target_jit, target_drp, target_flaps, n=30):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = time.time()
    for i in range(n):
        t = now - (n - i) * 2
        u = 45.0 + (target_util - 45.0) * ((i + 1) / float(n))
        l = 20.0 + (target_lat - 20.0) * ((i + 1) / float(n))
        j = 3.0 + (target_jit - 3.0) * ((i + 1) / float(n))
        d = 0.0 + (target_drp - 0.0) * ((i + 1) / float(n))
        f = target_flaps if i >= n - 2 else 0
        cursor.execute("""
            INSERT INTO metrics (timestamp, interface, utilization, latency, jitter, drops, routing_flaps)
            VALUES (?, 'Branch3-Uplink', ?, ?, ?, ?, ?)
        """, (t, u, l, j, d, f))
    conn.commit()
    conn.close()


# ============================================================
# 1. UNIT TESTS
# ============================================================
def run_unit_tests():
    print("\n" + "="*60)
    print("  [1/5] UNIT TESTS")
    print("="*60)

    # 1a. Module imports
    try:
        import config.settings
        import faultsim.generate_dataset
        import faultsim.inject_fault
        import engine.features
        import engine.model
        import engine.api
        import copilot.rag
        import copilot.llm
        import copilot.api
        record("UNIT", "All core modules import without error", True)

    except Exception as e:
        record("UNIT", "All core modules import without error", False, str(e))

    # 1b. Feature extraction – healthy telemetry
    try:
        from engine.features import extract_features_from_df, compute_slope
        healthy_df = pd.DataFrame({
            "utilization": np.full(30, 45.0),
            "latency": np.full(30, 20.0),
            "jitter": np.full(30, 3.0),
            "drops": np.zeros(30),
            "routing_flaps": np.zeros(30),
        })
        feats = extract_features_from_df(healthy_df)
        assert feats["utilization_current"] == 45.0
        assert feats["latency_current"] == 20.0
        assert abs(feats["utilization_slope_60s"]) < 0.01  # flat
        assert feats["utilization_delta_baseline"] == 0.0
        record("UNIT", "Feature extraction on flat healthy data", True)
    except Exception as e:
        record("UNIT", "Feature extraction on flat healthy data", False, str(e))

    # 1c. Feature extraction – rising congestion telemetry
    try:
        from engine.features import extract_features_from_df
        rising_df = pd.DataFrame({
            "utilization": np.linspace(50, 95, 30),
            "latency": np.linspace(25, 160, 30),
            "jitter": np.linspace(3, 18, 30),
            "drops": np.linspace(0, 8, 30),
            "routing_flaps": np.zeros(30),
        })
        feats = extract_features_from_df(rising_df)
        assert feats["utilization_slope_60s"] > 0, "Slope should be positive for rising data"
        assert feats["latency_slope_60s"] > 0
        assert feats["utilization_current"] == 95.0
        assert feats["latency_current"] == 160.0
        record("UNIT", "Feature extraction on rising congestion data", True)
    except Exception as e:
        record("UNIT", "Feature extraction on rising congestion data", False, str(e))

    # 1d. compute_slope math correctness
    try:
        from engine.features import compute_slope
        slope = compute_slope(np.array([0, 1, 2, 3, 4]))
        assert abs(slope - 1.0) < 0.001, f"Expected slope=1.0, got {slope}"
        slope_flat = compute_slope(np.array([5, 5, 5, 5]))
        assert abs(slope_flat) < 0.001
        slope_single = compute_slope(np.array([42]))
        assert slope_single == 0.0
        record("UNIT", "compute_slope mathematical correctness", True)
    except Exception as e:
        record("UNIT", "compute_slope mathematical correctness", False, str(e))

    # 1e. RiskPredictor – healthy input yields low risk
    try:
        from engine.model import RiskPredictor
        pred = RiskPredictor()
        healthy_df = pd.DataFrame({
            "utilization": np.full(30, 44.0),
            "latency": np.full(30, 19.0),
            "jitter": np.full(30, 2.5),
            "drops": np.zeros(30),
            "routing_flaps": np.zeros(30),
        })
        result = pred.predict(healthy_df)
        assert result["risk_score"] < 0.16, f"Healthy risk should be low, got {result['risk_score']}"
        record("UNIT", "RiskPredictor: healthy input → low risk", True)
    except Exception as e:
        record("UNIT", "RiskPredictor: healthy input → low risk", False, str(e))

    # 1f. RiskPredictor – congested input yields high risk
    try:
        from engine.model import RiskPredictor
        pred = RiskPredictor()
        cong_df = pd.DataFrame({
            "utilization": np.linspace(50, 92, 30),
            "latency": np.linspace(25, 140, 30),
            "jitter": np.linspace(3, 15, 30),
            "drops": np.linspace(0, 5, 30),
            "routing_flaps": np.zeros(30),
        })
        result = pred.predict(cong_df)
        assert result["risk_score"] > 0.5, f"Congested risk should be high, got {result['risk_score']}"
        assert result["time_to_impact"] > 0 or result["time_to_impact"] == -1.0
        record("UNIT", "RiskPredictor: congested input → high risk", True)
    except Exception as e:
        record("UNIT", "RiskPredictor: congested input → high risk", False, str(e))

    # 1g. RAG retriever returns results with correct schema
    try:
        from copilot.rag import LocalRAG
        rag = LocalRAG()
        results = rag.retrieve("congestion MPLS Branch3", k=3)
        assert len(results) > 0, "RAG returned no results"
        for r in results:
            assert "chunk" in r and "source" in r and "score" in r
        record("UNIT", "RAG retriever returns valid schema", True)
    except Exception as e:
        record("UNIT", "RAG retriever returns valid schema", False, str(e))

    # 1h. LLM fallback produces valid JSON structure
    try:
        from copilot.llm import get_fallback_explanation
        exp = get_fallback_explanation("Branch3-Uplink", 0.85, 4.5, ["latency rising"])
        required = ["predicted_issue", "confidence", "time_to_impact", "contributing_signals",
                     "affected_scope", "root_cause_hypothesis", "recommended_actions"]
        for field in required:
            assert field in exp, f"Missing field: {field}"
        assert isinstance(exp["recommended_actions"], list)
        assert len(exp["recommended_actions"]) >= 1
        record("UNIT", "LLM fallback JSON schema correctness", True)
    except Exception as e:
        record("UNIT", "LLM fallback JSON schema correctness", False, str(e))

    # 1i. Dataset generation
    try:
        from faultsim.generate_dataset import generate_scenario
        df = generate_scenario(0, "TestLink", mode="healthy")
        assert len(df) == 450
        assert "label" in df.columns
        assert df["label"].max() == 0  # healthy scenarios should have no breach labels
        df2 = generate_scenario(5, "TestLink", mode="congestion")
        assert len(df2) == 450
        assert df2["label"].max() == 1  # congestion scenarios should have some breach labels
        record("UNIT", "Dataset generation healthy & congestion modes", True)
    except Exception as e:
        record("UNIT", "Dataset generation healthy & congestion modes", False, str(e))


# ============================================================
# 2. INTEGRATION TESTS (API Contract)
# ============================================================
def run_integration_tests():
    print("\n" + "="*60)
    print("  [2/5] INTEGRATION TESTS (API Contracts)")
    print("="*60)

    # 2a. Engine /health endpoint
    try:
        res = requests.get(f"{ENGINE_URL}/health", timeout=2)
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        record("INTEGRATION", "Engine /health returns 200 + ok", True)
    except Exception as e:
        record("INTEGRATION", "Engine /health returns 200 + ok", False, str(e))

    # 2b. Copilot /health endpoint
    try:
        res = requests.get(f"{COPILOT_URL}/health", timeout=2)
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        record("INTEGRATION", "Copilot /health returns 200 + ok", True)
    except Exception as e:
        record("INTEGRATION", "Copilot /health returns 200 + ok", False, str(e))

    # 2c. Engine /predict JSON schema
    try:
        clear_metrics()
        insert_mock_telemetry(46, 21, 3, 0, 0)
        res = requests.get(f"{ENGINE_URL}/predict", params={"interface": "Branch3-Uplink"}, timeout=2)
        assert res.status_code == 200
        data = res.json()
        for key in ["interface", "risk_score", "time_to_impact", "contributing_signals", "status", "metrics"]:
            assert key in data, f"Missing key: {key}"
        for mkey in ["utilization", "latency", "jitter", "drops", "routing_flaps"]:
            assert mkey in data["metrics"], f"Missing metric key: {mkey}"
        record("INTEGRATION", "Engine /predict JSON schema complete", True)
    except Exception as e:
        record("INTEGRATION", "Engine /predict JSON schema complete", False, str(e))

    # 2d. Copilot /copilot JSON schema
    try:
        payload = {
            "interface": "Branch3-Uplink",
            "risk_score": 0.75,
            "time_to_impact": 5.0,
            "contributing_signals": ["test signal"]
        }
        res = requests.post(f"{COPILOT_URL}/copilot", json=payload, timeout=10)
        assert res.status_code == 200
        data = res.json()
        assert "explanation" in data
        assert "sources" in data
        exp = data["explanation"]
        for key in ["predicted_issue", "confidence", "recommended_actions"]:
            assert key in exp, f"Missing explanation key: {key}"
        record("INTEGRATION", "Copilot /copilot JSON schema complete", True)
    except Exception as e:
        record("INTEGRATION", "Copilot /copilot JSON schema complete", False, str(e))

    # 2e. Engine /predict returns correct interface echo
    try:
        clear_metrics()
        insert_mock_telemetry(46, 21, 3, 0, 0)
        res = requests.get(f"{ENGINE_URL}/predict", params={"interface": "Branch3-Uplink"}, timeout=2)
        data = res.json()
        assert data["interface"] == "Branch3-Uplink"
        record("INTEGRATION", "Engine echoes correct interface name", True)
    except Exception as e:
        record("INTEGRATION", "Engine echoes correct interface name", False, str(e))

    # 2f. Engine 404 for unknown routes
    try:
        res = requests.get(f"{ENGINE_URL}/nonexistent", timeout=2)
        assert res.status_code == 404
        record("INTEGRATION", "Engine returns 404 for unknown route", True)
    except Exception as e:
        record("INTEGRATION", "Engine returns 404 for unknown route", False, str(e))

    # 2g. Copilot 422 for invalid payload
    try:
        res = requests.post(f"{COPILOT_URL}/copilot", json={"bad": "data"}, timeout=5)
        assert res.status_code == 422
        record("INTEGRATION", "Copilot returns 422 for invalid payload", True)
    except Exception as e:
        record("INTEGRATION", "Copilot returns 422 for invalid payload", False, str(e))


# ============================================================
# 3. E2E SCENARIO TESTS
# ============================================================
def run_e2e_tests():
    print("\n" + "="*60)
    print("  [3/5] END-TO-END SCENARIO TESTS")
    print("="*60)

    # 3a. Healthy baseline
    try:
        clear_metrics()
        set_sim_mode("healthy")
        insert_mock_telemetry(46, 21, 3, 0, 0)
        res = requests.get(f"{ENGINE_URL}/predict", params={"interface": "Branch3-Uplink"}, timeout=2)
        data = res.json()
        assert data["risk_score"] < 0.3, f"Risk={data['risk_score']}"
        assert data["metrics"]["utilization"] < 55
        record("E2E", "Healthy baseline → low risk", True)
    except Exception as e:
        record("E2E", "Healthy baseline → low risk", False, str(e))

    # 3b. Congestion injection → high risk
    try:
        clear_metrics()
        set_sim_mode("congestion")
        insert_mock_telemetry(88, 125, 15, 4, 2)
        res = requests.get(f"{ENGINE_URL}/predict", params={"interface": "Branch3-Uplink"}, timeout=2)
        data = res.json()
        assert data["risk_score"] > 0.3, f"Risk={data['risk_score']}"
        assert len(data["contributing_signals"]) > 0
        record("E2E", "Congestion injection → elevated risk + signals", True)
    except Exception as e:
        record("E2E", "Congestion injection → elevated risk + signals", False, str(e))

    # 3c. Copilot recommendation grounded in runbooks
    try:
        payload = {
            "interface": "Branch3-Uplink",
            "risk_score": 0.9,
            "time_to_impact": 3.0,
            "contributing_signals": ["utilization 88%", "latency 125ms"]
        }
        res = requests.post(f"{COPILOT_URL}/copilot", json=payload, timeout=10)
        data = res.json()
        assert len(data["explanation"]["recommended_actions"]) >= 1
        assert len(data["sources"]) >= 1
        source_files = [s["source"] for s in data["sources"]]
        assert any("runbook" in s or "incidents" in s or "topology" in s for s in source_files)
        record("E2E", "Copilot returns RAG-grounded recommendations", True)
    except Exception as e:
        record("E2E", "Copilot returns RAG-grounded recommendations", False, str(e))

    # 3d. Mitigation recovery → risk drops
    try:
        clear_metrics()
        set_sim_mode("mitigated")
        insert_mock_telemetry(45.5, 19.5, 2.8, 0, 0)
        res = requests.get(f"{ENGINE_URL}/predict", params={"interface": "Branch3-Uplink"}, timeout=2)
        data = res.json()
        assert data["risk_score"] < 0.2, f"Risk={data['risk_score']}"
        record("E2E", "Mitigation applied → risk recovers to green", True)
    except Exception as e:
        record("E2E", "Mitigation applied → risk recovers to green", False, str(e))


# ============================================================
# 4. EDGE CASE TESTS
# ============================================================
def run_edge_case_tests():
    print("\n" + "="*60)
    print("  [4/5] EDGE CASE TESTS")
    print("="*60)

    # 4a. Predict with empty database
    try:
        clear_metrics()
        res = requests.get(f"{ENGINE_URL}/predict", params={"interface": "Branch3-Uplink"}, timeout=2)
        assert res.status_code == 200
        data = res.json()
        assert data["risk_score"] == 0.0
        record("EDGE", "Predict with empty metrics DB → 0.0 risk", True)
    except Exception as e:
        record("EDGE", "Predict with empty metrics DB → 0.0 risk", False, str(e))

    # 4b. Predict for unknown interface
    try:
        clear_metrics()
        res = requests.get(f"{ENGINE_URL}/predict", params={"interface": "NonExistent-Link"}, timeout=2)
        assert res.status_code == 200
        data = res.json()
        assert data["risk_score"] == 0.0
        record("EDGE", "Predict for unknown interface → 0.0 risk", True)
    except Exception as e:
        record("EDGE", "Predict for unknown interface → 0.0 risk", False, str(e))

    # 4c. Feature extraction with only 1 sample
    try:
        from engine.features import extract_features_from_df
        single_df = pd.DataFrame({
            "utilization": [75.0],
            "latency": [50.0],
            "jitter": [5.0],
            "drops": [1.0],
            "routing_flaps": [0],
        })
        feats = extract_features_from_df(single_df)
        assert feats["utilization_current"] == 75.0
        assert feats["utilization_slope_60s"] == 0.0  # can't compute slope with 1 point
        record("EDGE", "Feature extraction with 1 sample (no crash)", True)
    except Exception as e:
        record("EDGE", "Feature extraction with 1 sample (no crash)", False, str(e))

    # 4d. Feature extraction with all-zero data
    try:
        from engine.features import extract_features_from_df
        zero_df = pd.DataFrame({
            "utilization": np.zeros(30),
            "latency": np.zeros(30),
            "jitter": np.zeros(30),
            "drops": np.zeros(30),
            "routing_flaps": np.zeros(30),
        })
        feats = extract_features_from_df(zero_df)
        assert feats["utilization_current"] == 0.0
        record("EDGE", "Feature extraction with all-zero data (no crash)", True)
    except Exception as e:
        record("EDGE", "Feature extraction with all-zero data (no crash)", False, str(e))

    # 4e. RAG retrieval with empty query
    try:
        from copilot.rag import LocalRAG
        rag = LocalRAG()
        results = rag.retrieve("", k=2)
        assert isinstance(results, list)
        record("EDGE", "RAG retrieval with empty query (no crash)", True)
    except Exception as e:
        record("EDGE", "RAG retrieval with empty query (no crash)", False, str(e))

    # 4f. LLM fallback with empty signals
    try:
        from copilot.llm import get_fallback_explanation
        exp = get_fallback_explanation("Branch3-Uplink", 0.5, -1.0, [])
        assert "recommended_actions" in exp
        assert len(exp["recommended_actions"]) >= 1
        record("EDGE", "LLM fallback with empty signals (no crash)", True)
    except Exception as e:
        record("EDGE", "LLM fallback with empty signals (no crash)", False, str(e))

    # 4g. Copilot with extreme risk score
    try:
        payload = {
            "interface": "Branch3-Uplink",
            "risk_score": 1.0,
            "time_to_impact": 0.0,
            "contributing_signals": ["total failure"]
        }
        res = requests.post(f"{COPILOT_URL}/copilot", json=payload, timeout=10)
        assert res.status_code == 200
        record("EDGE", "Copilot handles extreme risk_score=1.0", True)
    except Exception as e:
        record("EDGE", "Copilot handles extreme risk_score=1.0", False, str(e))

    # 4h. Copilot with zero risk (should still respond)
    try:
        payload = {
            "interface": "Branch3-Uplink",
            "risk_score": 0.0,
            "time_to_impact": -1.0,
            "contributing_signals": []
        }
        res = requests.post(f"{COPILOT_URL}/copilot", json=payload, timeout=10)
        assert res.status_code == 200
        record("EDGE", "Copilot handles zero risk_score=0.0", True)
    except Exception as e:
        record("EDGE", "Copilot handles zero risk_score=0.0", False, str(e))


# ============================================================
# 5. STRESS TESTS
# ============================================================
def run_stress_tests():
    print("\n" + "="*60)
    print("  [5/5] STRESS TESTS")
    print("="*60)

    # 5a. Rapid-fire /predict calls (20 requests)
    try:
        clear_metrics()
        insert_mock_telemetry(46, 21, 3, 0, 0)
        failures = 0
        latencies = []
        for i in range(20):
            start = time.time()
            res = requests.get(f"{ENGINE_URL}/predict", params={"interface": "Branch3-Uplink"}, timeout=3)
            elapsed = time.time() - start
            latencies.append(elapsed)
            if res.status_code != 200:
                failures += 1
        avg_lat = sum(latencies) / len(latencies) * 1000
        max_lat = max(latencies) * 1000
        detail = f"Avg: {avg_lat:.0f}ms, Max: {max_lat:.0f}ms, Failures: {failures}/20"
        assert failures == 0, detail
        record("STRESS", f"20x rapid /predict calls → {detail}", True)
    except Exception as e:
        record("STRESS", "20x rapid /predict calls", False, str(e))

    # 5b. Rapid-fire /copilot calls (5 requests)
    try:
        failures = 0
        latencies = []
        payload = {
            "interface": "Branch3-Uplink",
            "risk_score": 0.7,
            "time_to_impact": 4.0,
            "contributing_signals": ["test"]
        }
        for i in range(5):
            start = time.time()
            res = requests.post(f"{COPILOT_URL}/copilot", json=payload, timeout=10)
            elapsed = time.time() - start
            latencies.append(elapsed)
            if res.status_code != 200:
                failures += 1
        avg_lat = sum(latencies) / len(latencies) * 1000
        max_lat = max(latencies) * 1000
        detail = f"Avg: {avg_lat:.0f}ms, Max: {max_lat:.0f}ms, Failures: {failures}/5"
        assert failures == 0, detail
        record("STRESS", f"5x rapid /copilot calls → {detail}", True)
    except Exception as e:
        record("STRESS", "5x rapid /copilot calls", False, str(e))

    # 5c. Database write/read consistency under load
    try:
        clear_metrics()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = time.time()
        for i in range(100):
            cursor.execute("""
                INSERT INTO metrics (timestamp, interface, utilization, latency, jitter, drops, routing_flaps)
                VALUES (?, 'StressTest', ?, ?, ?, ?, ?)
            """, (now + i * 0.01, 50 + i * 0.1, 20 + i * 0.05, 3, 0, 0))
        conn.commit()
        cursor.execute("SELECT COUNT(*) FROM metrics WHERE interface='StressTest'")
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 100, f"Expected 100 rows, got {count}"
        record("STRESS", "100x DB write/read consistency", True)
    except Exception as e:
        record("STRESS", "100x DB write/read consistency", False, str(e))


# ============================================================
# MAIN RUNNER
# ============================================================
def print_summary():
    print("\n" + "="*60)
    print("  FINAL TEST SUMMARY")
    print("="*60)
    
    categories = {}
    for cat, name, status, detail in RESULTS:
        if cat not in categories:
            categories[cat] = {"pass": 0, "fail": 0, "errors": []}
        if status == "PASS":
            categories[cat]["pass"] += 1
        else:
            categories[cat]["fail"] += 1
            categories[cat]["errors"].append((name, detail))

    total_pass = sum(c["pass"] for c in categories.values())
    total_fail = sum(c["fail"] for c in categories.values())
    total = total_pass + total_fail

    print(f"\n  {'Category':<20} {'Passed':>8} {'Failed':>8} {'Total':>8}")
    print(f"  {'-'*20} {'-'*8} {'-'*8} {'-'*8}")
    for cat in ["UNIT", "INTEGRATION", "E2E", "EDGE", "STRESS"]:
        if cat in categories:
            c = categories[cat]
            t = c["pass"] + c["fail"]
            print(f"  {cat:<20} {c['pass']:>8} {c['fail']:>8} {t:>8}")
    print(f"  {'-'*20} {'-'*8} {'-'*8} {'-'*8}")
    print(f"  {'TOTAL':<20} {total_pass:>8} {total_fail:>8} {total:>8}")

    if total_fail > 0:
        print(f"\n  ❌ ERRORS FOUND ({total_fail}):")
        print(f"  {'─'*56}")
        for cat, name, status, detail in RESULTS:
            if status == "FAIL":
                print(f"  [{cat}] {name}")
                if detail:
                    print(f"         ↳ {detail}")
    else:
        print(f"\n  🎉 ALL {total} TESTS PASSED WITH ZERO ERRORS!")

    return total_fail


if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════════╗")
    print("║    NOC COPILOT — MASTER TEST RUNNER (All Test Types)    ║")
    print("╚══════════════════════════════════════════════════════════╝")

    run_unit_tests()
    run_integration_tests()
    run_e2e_tests()
    run_edge_case_tests()
    run_stress_tests()
    
    failures = print_summary()
    
    # Restore healthy sim state after tests
    set_sim_mode("healthy")
    clear_metrics()
    
    sys.exit(1 if failures > 0 else 0)
