# Enterprise Intelligent Network Path & Provider Decision Engine (Sprint 17)

## Overview

The **Enterprise Intelligent Network Path & Provider Decision Engine** enables NOC Copilot to make evidence-driven path and provider failover decisions when network links, interfaces, or service providers degrade or are predicted to fail.

The system enforces a strict operational safety pipeline:
```
Detect → Predict → Discover Alternatives → Evaluate → Compare → Simulate → Verify → Recommend → Apply Trust Policy → Request Approval
```

> [!IMPORTANT]
> **Safety Boundary**: The Path Decision Engine **NEVER** executes unauthorized router, firewall, SSH, or SDN configuration changes. All recommendations remain strictly advisory (`HUMAN_APPROVAL_REQUIRED` / `BLOCKED`) until explicitly authorized through an enterprise change management gateway.

---

## Architectural Components

The subsystem is located at `agents/path_decision/`:

| Component | Class | Responsibility |
|---|---|---|
| `path_models.py` | Domain Models | Pydantic V2 models (`PathCandidate`, `PathEvaluation`, `PathScore`, `FailoverRecommendation`, etc.) |
| `path_discovery.py` | `PathDiscoveryEngine` | Discovers primary/alternate paths, intermediate hops, dependencies, and SPOFs from topology. |
| `provider_health.py` | `ProviderHealthEngine` | Computes transparent 0–100 provider health scores normalized from telemetry & XGBoost risk. |
| `path_evaluator.py` | `PathEvaluationEngine` | Evaluates candidates across 14 technical and operational dimensions. |
| `economics_engine.py` | `NetworkEconomicsEngine` | Evaluates bandwidth cost, SLAs, and pricing terms (returns `UNKNOWN` if missing). |
| `path_scoring.py` | `PathScoringEngine` | Ranks candidate paths using configurable weighted scoring algorithms. |
| `path_simulator.py` | `PathSimulationEngine` | Simulates performance scenarios (`SIMULATED / ESTIMATED` vs `OBSERVED`). |
| `recommendation_engine.py` | `FailoverRecommendationEngine` | Formulates actionable recommendations (`KEEP_CURRENT_PATH`, `RECOMMEND_ALTERNATIVE`, etc.). |
| `decision_service.py` | `PathDecisionService` | Orchestrates decision pipeline, re-using `ReasoningAgent`, `TrustAgent`, & `PreMortemAgent`. |
| `path_decision_agent.py` | `PathDecisionAgent` | Atomic Agent wrapping the decision service, handling `EventBus` subscriptions. |

---

## Data Flow

```
                     ┌────────────────────────┐
                     │ Live Telemetry & DB    │
                     └───────────┬────────────┘
                                 │
┌────────────────────────┐       ▼        ┌────────────────────────┐
│ Topology & Inventory   ├───────────────►│ PathDiscoveryEngine    │
└────────────────────────┘                └───────────┬────────────┘
                                                      │
                                                      ▼
                                          ┌────────────────────────┐
                                          │ ProviderHealthEngine   │
                                          └───────────┬────────────┘
                                                      │
                                                      ▼
                                          ┌────────────────────────┐
                                          │ PathEvaluationEngine   │
                                          └───────────┬────────────┘
                                                      │
                                                      ▼
                                          ┌────────────────────────┐
                                          │ NetworkEconomicsEngine │
                                          └───────────┬────────────┘
                                                      │
                                                      ▼
                                          ┌────────────────────────┐
                                          │ PathScoringEngine      │
                                          └───────────┬────────────┘
                                                      │
                                                      ▼
                                          ┌────────────────────────┐
                                          │ PathSimulationEngine   │
                                          └───────────┬────────────┘
                                                      │
  ┌───────────────────────┐                           ▼                           ┌───────────────────────┐
  │ ReasoningAgent        ├───────────────────────────┼──────────────────────────►│ TrustAgent            │
  └───────────────────────┘                           │                           └───────────┬───────────┘
                                                      │                                       │
  ┌───────────────────────┐                           ▼                                       │
  │ PreMortemAgent        ├───────────────────────────┼───────────────────────────────────────┘
  └───────────────────────┘                           │
                                                      ▼
                                          ┌────────────────────────┐
                                          │ FailoverRecommendation │
                                          └────────────────────────┘
```

---

## Scoring & Evaluation Criteria

Paths are evaluated across **14 criteria**:
1. Health Score (0–100)
2. Reliability Rating (0–100)
3. XGBoost Predicted Failure Risk (0.0–1.0)
4. Round-Trip Latency (ms)
5. Packet Loss Percentage (%)
6. Jitter (ms)
7. Link Capacity (Mbps)
8. Bandwidth Utilization (%)
9. SLA Compliance Status (`COMPLIANT`, `VIOLATED`, `UNKNOWN`)
10. Topology Independence Score (0–100)
11. Operational Blast Radius Score (0.0–1.0)
12. Historical Reliability Index (0–100)
13. Evidence Freshness (seconds)
14. Telemetry Collector Confidence (0.0–1.0)

### Default Scoring Weights

Configurable via `PathScoringEngine(custom_weights=...)`:
- Health Weight: `0.20`
- Reliability Weight: `0.15`
- Risk Weight: `0.20`
- Latency Weight: `0.15`
- Packet Loss Weight: `0.10`
- SLA Weight: `0.05`
- Economics Weight: `0.05`
- Topology Independence Weight: `0.10`

---

## EventBus Lifecycle Events

The subsystem emits the following lifecycle events on the `EventBus`:
- `path.discovery.started`
- `path.discovery.completed`
- `path.health.evaluated`
- `path.evaluation.completed`
- `path.economics.calculated`
- `path.simulation.completed`
- `path.ranking.completed`
- `path.recommendation.generated`
- `path.decision.completed`
- `path.decision.blocked`
- `path.decision.failed`

---

## Running Tests

Run the complete Sprint 17 test suite:
```bash
PYTHONPATH=. ./venv/bin/python3 -m unittest tests/test_path_decision.py
```
