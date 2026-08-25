# NOC Copilot — Operator Demonstration Guide

**Version**: v1.1.0-rc1

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

## 2. Primary Demo Scenario: Branch3-Uplink Golden Incident Lifecycle

The primary demonstration showcases the end-to-end multi-agent intelligence pipeline when **Branch3-Uplink** experiences upstream WAN degradation.

### 5-Phase Unified Intelligence Flow

```text
1. Telemetry & Predictive Risk: XGBoost predicts failure trajectory (45%-91% risk) [PREDICTED]
      ↓
2. Phase 1 — Topology Intelligence: Graph BFS computes blast radius (CRITICAL) & identifies 2 SPOFs
      ↓
3. Phase 2 — Evidence Lineage: Aggregates 5 typed evidence items across 4 source agents with strict provenance
      ↓
4. Phase 4 — Historical Intelligence: Matches WAN_CONGESTION patterns, adjusts confidence (+0.11)
      ↓
5. Phase 3 — Confidence & Explainability: Synthesizes DecisionExplanationReport (Score 52%, why ISP-B won)
      ↓
6. Trust & Safety Gate: Evaluates blast radius > max policy -> Enforces HUMAN_APPROVAL_REQUIRED
      ↓
7. Path Decision: PathScoringEngine ranks ISP-B #1 (Score: 94.1 vs ISP-A 72.4)
      ↓
8. Operator Approval Checkpoint: Operator signs off on execution plan hash (OPERATOR-GOLDEN)
      ↓
9. DRY_RUN Execution: DryRunExecutionAdapter executes simulated provider failover safely
      ↓
10. Closed-Loop Verification: Post-execution telemetry audit confirms Latency 22ms and Loss 0.20%
      ↓
11. Rollback Protection: Automatic RollbackEngine restores healthy baseline if verification fails
      ↓
12. Phase 5 — Adaptive Decision Learning: Compares predicted vs observed delta (SUCCESSFUL_PREDICTION, 98% Quality)
```

---

## 3. UI Controls & Operator Actions

| Action / Button | UI Location | Behavior / Expected State |
|---|---|---|
| **🌟 Golden Incident Panel** | Top Expander | Renders live 5-phase intelligence lifecycle, decisive metrics, and provenance breakdown for `Branch3-Uplink`. |
| **▶️ Start Scenario** | Sidebar (Demo Scenario Controller) | Selects `Branch3-Uplink`, injects WAN congestion, sets risk to elevated, and triggers incident investigation. |
| **🔄 Reset Scenario** | Sidebar (Demo Scenario Controller) | Restores healthy baseline across all fleet devices and resets lifecycle states. |
| **Simulate Dry-Run Failover** | Stage 8 (Controlled Failover Panel) | Runs `FailoverService` in `DRY_RUN` mode via `DryRunExecutionAdapter`, displays SHA-256 plan hash, evaluates 16 prechecks, and updates status to `COMPLETED`. |
| **Request Approval** | Stage 8 (Controlled Failover Panel) | Creates an approval request bound to the SHA-256 plan hash (`PENDING_APPROVAL`). |
| **Verify Closed-Loop** | Stage 8 (Controlled Failover Panel) | Executes post-change telemetry audit confirming latency and loss are within SLA bounds. |
| **Trigger Rollback Test** | Stage 8 (Controlled Failover Panel) | Simulates verification failure and triggers immediate automatic rollback to `ISP-A` (`ROLLED_BACK`). |
| **Evaluate Adaptive State** | Stage 9 (Adaptive Control Panel) | Evaluates hysteresis cooldown (120s) and hold time (300s) to prevent route flapping. |
| **Stage 9.5 Adaptive Learning** | Stage 9.5 (Adaptive Learning Panel) | Displays prediction error, bounded decision quality score, and actionable operational lessons learned. |
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
- **Topology Blast Radius Rationale**: Level CRITICAL (100% network impact, 2 single points of failure).
- **Evidence Lineage Rationale**: 5 evidence items aggregated across TelemetryAgent, PredictionAgent, IncidentAgent, TopologyAgent, and PreMortemService.
- **Provider Recommendation Rationale**: Candidate evaluation ranks ISP-B #1 with Score 94.1, Latency 22ms, Packet Loss 0.1%, and full SLA compliance.
- **Closed-Loop Learning Rationale**: Predicted outcome closely matches observed outcome (Error: 3.0%, Quality: 98.0% EXCELLENT).

---

## 6. Safety Boundaries & Guarantees

1. **Execution Safety Boundary**: All operations execute in `ExecutionMode.DRY_RUN`. No subprocess, shell execution, or SSH mutations occur.
2. **Deterministic Provenance**: All data displays explicit origin tags: `[OBSERVED]`, `[PREDICTED]`, `[INFERRED]`, `[HISTORICAL]`, and `[SIMULATION]`. Zero synthetic metrics are fabricated.
3. **Air-Gapped Operation**: 100% local operation using local SQLite database (`data/telemetry.db`), `qwen3:1.7b` local inference via Ollama (`10.0.2.2:11434`), and offline `.nockb` bundle exchanges.
4. **Hermes / MCP Exclusion**: Zero dependency on external MCP protocols or Hermes runtime.

---

## 7. Acceptance Evidence & Verification Checklist

- [x] Full repository test suite passes: `pytest -q` (19,351 passed, 1 skipped)
- [x] Golden Scenario integration suite passes: `pytest -q tests/test_golden_scenario.py` (13/13 passed)
- [x] Targeted intelligence suites pass: (391/391 passed across 9 suites)
- [x] Streamlit UI test suite passes: `pytest -q tests/test_ui_streamlit.py` (50/50 passed)
- [x] Runtime capability suite passes: `pytest -q tests/test_runtime_capability.py` (37/37 passed)
- [x] Headless Streamlit launch passes: `streamlit run ui/app.py --server.headless true --server.port 8501`
- [x] Operator status strip displays all 7 status dimensions accurately.
- [x] Top-level Golden Incident Scenario panel renders full 5-stage lifecycle and provenance tags.
- [x] 16 pre-execution checks and SHA-256 plan hash render correctly.
- [x] Rollback simulation executes automatically upon verification failure.
