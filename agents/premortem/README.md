# 🔮 Enterprise Incident Fingerprinting & Pre-Mortem Intelligence Engine (`agents/premortem`)

The **Enterprise Incident Fingerprinting & Pre-Mortem Intelligence Engine** recognizes normalized incident signatures, matches historical incidents via vector search, clusters recurring failure patterns, and predicts "What is likely to happen next if we do nothing?"

---

> [!IMPORTANT]
> **CATEGORICAL BOUNDARY ENFORCED**
> Pre-Mortem outputs explicitly distinguish:
> - `OBSERVED`: Empirical telemetry data
> - `PREDICTED`: Projected metrics & machine learning model outputs
> - `INFERRED`: Derived conclusions
> - `HISTORICAL`: Past incident records from RAG vector store
> - `UNKNOWN`: Unverified telemetry

> [!CAUTION]
> **SAFETY BOUNDARY NOTICE**
> `PreMortemAgent` simulates scenarios and predicts future states. **It DOES NOT execute network configuration changes.**

---

## 🏗️ Pre-Mortem Pipeline Architecture

```
                    ┌────────────────────────┐
                    │    InvestigationContext│
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │IncidentFingerprintEngine│ (Deterministic Signature Extraction)
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │HistoricalIncidentMatcher│ (RAG VectorStore Similarity Lookup)
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │IncidentPatternClusterer│ (Recurring Failure Patterns)
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │  FutureScenarioEngine  │ (What-If Scenario Simulation)
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │ TimeToImpactEstimator  │ (Impact Range Bounds)
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │   EarlyWarningEngine   │ (Early Pattern Detection)
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │    PreMortemResult     │ (Complete Future-State Intelligence)
                    └────────────────────────┘
```

---

## 📖 Developer Guide

```python
from agents.premortem import PreMortemAgent, PreMortemService
from agents.orchestrator_ai import InvestigationContext

# Execute PreMortem Agent
agent = PreMortemAgent()
context = InvestigationContext()
result = agent.execute(context)

print(f"Pre-Mortem ID: {result.premortem_id}")
print(f"Summary: {result.summary}")
print(f"Estimated Time to Impact: {result.time_to_impact.min_time_minutes}–{result.time_to_impact.max_time_minutes} mins")
```
