# NOC Copilot — Operator Demonstration Guide

**Version**: v1.0.0-rc1

This guide provides step-by-step instructions for conducting an executive or operator demonstration of NOC Copilot.

---

## 1. Demonstration Setup & Verification

Before starting the demonstration, verify that the application and environment are healthy:

```bash
# 1. Run environment & model readiness diagnostic
PYTHONPATH=. ./venv/bin/python3 run.py --check-only

# 2. Start the Streamlit UI dashboard
PYTHONPATH=. ./venv/bin/streamlit run ui/app.py --server.port 8501
```

Access the Streamlit Dashboard at `http://localhost:8501`.

---

## 2. Primary Demo Scenario: Branch3-Uplink WAN Degradation

The primary demonstration showcases the end-to-end operator workflow when **Branch3-Uplink** experiences upstream ISP congestion and degradation.

### 17-Step Operator Journey

```text
1. Select Device: Branch3-Uplink
      ↓
2. Live Telemetry: Utilization 96%, Latency 195ms, Loss 8.5% [OBSERVED]
      ↓
3. Predictive Risk: Failure Risk = 91%, ETA to SLA Breach: ~2.5 min [PREDICTED]
      ↓
4. Incident Creation: IncidentRecord Severity = CRITICAL / HIGH
      ↓
5. Evidence Timeline: Chronological event ledger with provenance tags
      ↓
6. AI Reasoning: Root-cause hypothesis ranked ("WAN Link Congestion") + Cited RAG sources
      ↓
7. Trust & Blast Radius: Trust Score = 0.52 / 1.00, Blast Radius = HIGH
      ↓
8. Autonomy Policy Gate: HUMAN_APPROVAL_REQUIRED enforced
      ↓
9. Path Decision: Evaluates candidates, recommends ISP-B
      ↓
10. UI Selection Rationale: Health 94.1 vs 42.5, Latency 22ms vs 195ms, Loss 0.1% vs 8.5%
      ↓
11. Controlled DRY_RUN: Operator triggers simulated failover with DryRunExecutionAdapter
      ↓
12. 16 Pre-Execution Checks: Evaluated and passed before change is committed
      ↓
13. Plan Hash Binding: Cryptographically bound to SHA-256 Plan Hash
      ↓
14. Closed-Loop Verification: Fresh post-execution telemetry comparison (Latency <= 35ms, Loss <= 0.5%)
      ↓
15. Rollback Feasibility: Rollback test triggers automatic restore to original provider if verification fails
      ↓
16. Final Lifecycle State: Status = COMPLETED / ROLLED_BACK with Audit Reference
      ↓
17. Incident Learning: Offline .nockb bundle export with HMAC-SHA256 and zero PII leaks
```

---

## 3. UI Controls & Operator Actions

| Action / Button | UI Location | Behavior / Expected State |
|---|---|---|
| **▶️ Start Scenario** | Sidebar (Demo Scenario Controller) | Selects `Branch3-Uplink`, injects WAN congestion, sets risk to elevated (91%), and triggers incident investigation. |
| **🔄 Reset Scenario** | Sidebar (Demo Scenario Controller) | Restores healthy baseline across all fleet devices and resets lifecycle states. |
| **Simulate Dry-Run Failover** | Stage 8 (Controlled Failover Panel) | Runs `FailoverService` in `DRY_RUN` mode via `DryRunExecutionAdapter`, displays SHA-256 plan hash, evaluates 16 prechecks, and updates status to `COMPLETED`. |
| **Request Approval** | Stage 8 (Controlled Failover Panel) | Creates an approval request bound to the SHA-256 plan hash (`PENDING_APPROVAL`). |
| **Verify Closed-Loop** | Stage 8 (Controlled Failover Panel) | Executes post-change telemetry audit confirming latency and loss are within SLA bounds. |
| **Trigger Rollback Test** | Stage 8 (Controlled Failover Panel) | Simulates verification failure and triggers immediate automatic rollback to `ISP-A` (`ROLLED_BACK`). |
| **Evaluate Adaptive State** | Stage 9 (Adaptive Control Panel) | Evaluates hysteresis cooldown (120s) and hold time (300s) to prevent route flapping. |
| **Export Signed Bundle** | Stage 10 (Federated Exchange Panel) | Exports an offline `.nockb` knowledge bundle with HMAC-SHA256 signature and 0 PII leaks. |

---

## 4. Operator Status Strip

The dashboard features a high-visibility 7-metric Operator Status Strip at the top of the interface:

1. **Incident State**: `INVESTIGATING` / `MITIGATING` / `RESOLVED` / `STABLE`
2. **Failure Risk**: Dynamic XGBoost failure probability (`12%` healthy to `91%` degraded)
3. **Trust Score**: Composite score (`0.52 / 1.00`) across reasoning, evidence, adversarial, and safety factors
4. **Blast Radius**: `HIGH` (WAN uplink affecting all branch subnets)
5. **Autonomy Decision**: `HUMAN_APPROVAL_REQUIRED`
6. **Operating Mode**: `DRY_RUN` (Mandatory safety boundary)
7. **Recommended Provider**: `ISP-B` (Optimal alternative path)

---

## 5. Decision Explanations & Evidence Rationale

NOC-Copilot provides concise, factored evidence explanations without exposing raw chain-of-thought:

- **Failure Risk Rationale**: Top contributing signals: Egress drops > 8.5/s, Latency > 195ms, Utilization > 96%.
- **Root Cause Rationale**: ISP upstream circuit saturation confirmed via queue buffer exhaustion telemetry.
- **Trust Score Rationale**: Reasoning (30%), Evidence freshness (25%), Adversarial probing (25%), Operational safety (20%).
- **Blast Radius Rationale**: Multi-branch WAN uplink impacts inter-site voice/data, requiring mandatory human confirmation.
- **Provider Recommendation Rationale**: Candidate evaluation ranks ISP-B #1 with Score 94.1, Latency 22ms, Packet Loss 0.1%, and full SLA compliance.

---

## 6. Safety Boundaries & Guarantees

1. **Execution Safety Boundary**: All operations execute in `ExecutionMode.DRY_RUN`. No subprocess, shell execution, or SSH mutations occur.
2. **Deterministic Provenance**: All data displays explicit origin tags: `[OBSERVED]`, `[PREDICTED]`, `[INFERRED]`, `[HISTORICAL]`, and `[SIMULATION]`. Zero synthetic metrics are fabricated.
3. **Air-Gapped Operation**: 100% local operation using local SQLite database (`data/telemetry.db`), `qwen3:1.7b` local inference via Ollama (`10.0.2.2:11434`), and offline `.nockb` bundle exchanges.
4. **Hermes / MCP Exclusion**: Zero dependency on external MCP protocols or Hermes runtime.

---

## 7. Acceptance Evidence & Verification Checklist

- [x] Streamlit UI test suite passes: `pytest -q tests/test_ui_streamlit.py` (50/50 passed)
- [x] Runtime capability suite passes: `pytest -q tests/test_runtime_capability.py` (37/37 passed)
- [x] Full repository test suite passes: `pytest -q` (19,280 passed, 1 skipped)
- [x] Headless Streamlit launch passes: `streamlit run ui/app.py --server.headless true --server.port 8501`
- [x] Operator status strip displays all 7 status dimensions accurately.
- [x] Scenario controller transitions between Healthy and Congestion states deterministically.
- [x] 16 pre-execution checks and SHA-256 plan hash render correctly.
- [x] Rollback simulation executes automatically upon verification failure.
