# NOC Copilot — Enterprise Architecture Specification

## 1. System Overview

NOC Copilot is an air-gapped, zero-cloud-dependency enterprise network observability and controlled failover execution platform.

```text
+-----------------------------------------------------------------------------------+
|                                  STREAMLIT UI                                     |
+-----------------------------------------------------------------------------------+
                                         |
+-----------------------------------------------------------------------------------+
|                                 EVENTBUS & DI                                     |
|              EventBus (Pub/Sub)  ·  ServiceContainer (DI)                         |
+-----------------------------------------------------------------------------------+
    |                   |                  |                  |                 |
+-------+           +-------+          +-------+          +-------+         +-------+
|  ML   |           |  AI   |          | TRUST |          | PATH  |         | FED   |
| RISK  |           | REASON|          | GATE  |          | DECIS |         | KNOW  |
+-------+           +-------+          +-------+          +-------+         +-------+
    |                   |                  |                  |                 |
+-----------------------------------------------------------------------------------+
|                        STRUCTURED INVESTIGATION MEMORY                            |
|       InvestigationContext  ·  EvidenceRegistry  ·  VectorStore (RAG/CAG)         |
+-----------------------------------------------------------------------------------+
                                         |
+-----------------------------------------------------------------------------------+
|                             TYPED EXECUTION ADAPTER                               |
|        DryRunExecutionAdapter (Default)  ·  AuthorizedNetworkAdapter              |
+-----------------------------------------------------------------------------------+
```

---

## 2. Core Architectural Principles

1. **Atomic Agent Architecture**: 18 specialized agents inherit from `BaseAgent` and communicate asynchronously over `EventBus`.
2. **Structured Investigation Memory Model**: Thread-safe `InvestigationContext` and `EvidenceRegistry` maintain immutable evidence lineage across investigation steps.
3. **Strict Data Provenance**: Every metric and prediction retains explicit provenance (`OBSERVED`, `PREDICTED`, `INFERRED`, `HISTORICAL`, `SIMULATION`).
4. **Safety Boundaries**: `DryRunExecutionAdapter` is the default execution boundary. Raw shell, SSH, CLI, or firewall command generation is strictly prohibited.
5. **Air-Gapped Privacy**: PrivacySanitizer scrubs PII with 100% precision. CryptoSigner signs bundles with HMAC-SHA256 before federated import into RAG vectorstore.

---

## 3. Subsystem Breakdown

- **Telemetry Processing**: `TelemetryAgent`, `TelemetryService`, `TelemetryCollector`
- **Predictive Risk**: `PredictionAgent`, `PredictionService`, `XGBoostModel`
- **Orchestration**: `PlannerAgent`, `OrchestratorAgent`, `AgentOrchestrator`
- **Reasoning Engine**: `ReasoningAgent`, `ReasoningService`
- **Trust & Safety Gate**: `TrustAgent`, `TrustService`, `AutonomyPolicyGate`
- **Pre-Mortem Intelligence**: `PreMortemAgent`, `PreMortemService`, `EarlyWarningSystem`
- **Intelligent Path Decision**: `PathDecisionAgent`, `PathDecisionService`, `PathEvaluationEngine`, `NetworkEconomicsEngine`
- **Controlled Failover**: `FailoverAgent`, `FailoverService`, `PreExecutionValidator`, `PostExecutionVerifier`, `RollbackEngine`
- **Adaptive Failover & Hysteresis**: `AdaptiveFailoverAgent`, `AdaptiveFailoverService`, `HysteresisEngine`, `StabilityEngine`, `TransitionManager`
- **Air-Gapped Federated Intelligence**: `FederatedIntelligenceAgent`, `FederatedIntelligenceService`, `PrivacySanitizer`, `CryptoSigner`, `BundleExporter`, `BundleImporter`, `FederatedKnowledgeBase`
