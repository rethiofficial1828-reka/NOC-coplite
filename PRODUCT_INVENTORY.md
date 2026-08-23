# NOC Copilot — Comprehensive Product Inventory

This document maps all existing subsystems, Atomic Agents, domain services, databases, collectors, vectorstores, execution adapters, and Streamlit UI panels in the NOC Copilot codebase (Sprints 1–20 Complete).

---

## 1. Atomic Agent Architecture (18 Core Agents)

| Agent Name | Source File | Core Responsibility |
|---|---|---|
| **TelemetryAgent** | [agents/telemetry/telemetry_agent.py](file:///home/kali/Downloads/NOC-coplite/agents/telemetry/telemetry_agent.py) | Ingests real & simulated telemetry, aggregates metrics, publishes metric events |
| **PredictionAgent** | [agents/prediction/prediction_agent.py](file:///home/kali/Downloads/NOC-coplite/agents/prediction/prediction_agent.py) | Evaluates XGBoost ML failure risk probabilities on network interfaces |
| **IncidentAgent** | [agents/incident/incident_agent.py](file:///home/kali/Downloads/NOC-coplite/agents/incident/incident_agent.py) | Manages incident lifecycles, severities, correlations, and fingerprints |
| **TopologyAgent** | [agents/topology/topology_agent.py](file:///home/kali/Downloads/NOC-coplite/agents/topology/topology_agent.py) | Maintains network topology graph, device registries, links, and SPOFs |
| **KnowledgeAgent** | [agents/knowledge/knowledge_agent.py](file:///home/kali/Downloads/NOC-coplite/agents/knowledge/knowledge_agent.py) | Enriches context with operational runbooks and Ollama LLM synthesis |
| **PlannerAgent** | [agents/orchestrator_ai/planner_agent.py](file:///home/kali/Downloads/NOC-coplite/agents/orchestrator_ai/planner_agent.py) | Builds multi-step investigation DAG plans |
| **OrchestratorAgent** | [agents/orchestrator_ai/orchestrator_agent.py](file:///home/kali/Downloads/NOC-coplite/agents/orchestrator_ai/orchestrator_agent.py) | Coordinates AI DAG execution and evidence collection |
| **ReasoningAgent** | [agents/reasoning/reasoning_agent.py](file:///home/kali/Downloads/NOC-coplite/agents/reasoning/reasoning_agent.py) | Ranks root-cause hypotheses based on evidence lineage |
| **TrustAgent** | [agents/trust/trust_agent.py](file:///home/kali/Downloads/NOC-coplite/agents/trust/trust_agent.py) | Enforces blast radius evaluation and autonomy policy gates |
| **PreMortemAgent** | [agents/premortem/premortem_agent.py](file:///home/kali/Downloads/NOC-coplite/agents/premortem/premortem_agent.py) | Forecasts time-to-impact and SLA breach risk scenarios |
| **RuntimeAgent** | [agents/runtime/runtime_agent.py](file:///home/kali/Downloads/NOC-coplite/agents/runtime/runtime_agent.py) | Detects OS, VirtualBox, GPU, and Ollama capabilities |
| **PathDecisionAgent** | [agents/path_decision/path_decision_agent.py](file:///home/kali/Downloads/NOC-coplite/agents/path_decision/path_decision_agent.py) | Evaluates multi-provider path health, SLAs, and financial economics |
| **FailoverAgent** | [agents/failover/failover_agent.py](file:///home/kali/Downloads/NOC-coplite/agents/failover/failover_agent.py) | Manages 16 prechecks, dry-run failover, and post-verification |
| **AdaptiveFailoverAgent** | [agents/adaptive_failover/adaptive_failover_agent.py](file:///home/kali/Downloads/NOC-coplite/agents/adaptive_failover/adaptive_failover_agent.py) | Enforces hysteresis, anti-flapping hold time, and safe failback |
| **FederatedIntelligenceAgent** | [agents/federated_intelligence/federated_intelligence_agent.py](file:///home/kali/Downloads/NOC-coplite/agents/federated_intelligence/federated_intelligence_agent.py) | Sanitizes PII, signs knowledge bundles, and imports verified patterns |
| **RAGAgent** | [agents/rag/rag_agent.py](file:///home/kali/Downloads/NOC-coplite/agents/rag/rag_agent.py) | Queries local VectorStore for historical incident matches |
| **RecommendationAgent** | [agents/recommendation/recommendation_agent.py](file:///home/kali/Downloads/NOC-coplite/agents/recommendation/recommendation_agent.py) | Synthesizes operator action recommendations |
| **TelemetryCollector** | [agents/telemetry/collectors.py](file:///home/kali/Downloads/NOC-coplite/agents/telemetry/collectors.py) | Enterprise SNMP/gNMI/IPFIX collector abstraction |

---

## 2. Infrastructure & Shared Services

- **EventBus**: [agents/events/event_bus.py](file:///home/kali/Downloads/NOC-coplite/agents/events/event_bus.py) — In-memory pub/sub event distribution mechanism.
- **ServiceContainer**: [agents/core/container.py](file:///home/kali/Downloads/NOC-coplite/agents/core/container.py) — Dependency injection container.
- **InvestigationContext**: [agents/orchestrator_ai/investigation_context.py](file:///home/kali/Downloads/NOC-coplite/agents/orchestrator_ai/investigation_context.py) — Thread-safe structured investigation memory context.
- **EvidenceRegistry**: [agents/orchestrator_ai/evidence_registry.py](file:///home/kali/Downloads/NOC-coplite/agents/orchestrator_ai/evidence_registry.py) — Evidence reference tracker.
- **VectorStore**: [agents/rag/vector_store.py](file:///home/kali/Downloads/NOC-coplite/agents/rag/vector_store.py) — SQLite-backed vector knowledge store.
- **PrivacySanitizer**: [agents/federated_intelligence/privacy_sanitizer.py](file:///home/kali/Downloads/NOC-coplite/agents/federated_intelligence/privacy_sanitizer.py) — Regex PII scrubbing engine.
- **CryptoSigner**: [agents/federated_intelligence/crypto_signer.py](file:///home/kali/Downloads/NOC-coplite/agents/federated_intelligence/crypto_signer.py) — HMAC-SHA256 signature engine.

---

## 3. Execution Adapters & Safety Boundaries

- **DryRunExecutionAdapter**: [agents/failover/dry_run_adapter.py](file:///home/kali/Downloads/NOC-coplite/agents/failover/dry_run_adapter.py) — Default execution mode. Simulated state mutation without touching physical routers.
- **AuthorizedNetworkAdapter**: [agents/failover/authorized_execution_adapter.py](file:///home/kali/Downloads/NOC-coplite/agents/failover/authorized_execution_adapter.py) — Typed production adapter interface. Defaults to `NOT_CONFIGURED`.

---

## 4. UI Dashboard Panels (`ui/app.py`)

1. **Header & Data Origin Badges**: Displays execution mode (`DRY_RUN`) and provenance badges (`OBSERVED`, `PREDICTED`, `SIMULATION`).
2. **Network Health & Telemetry Grid**: Displays ISP-A vs ISP-B metrics (latency, loss, jitter, utilization).
3. **Predictive Failure Engine**: XGBoost risk probability displays.
4. **Reasoning & Root Cause Engine**: Hypothesis ranking with evidence citations.
5. **Trust & Safety Autonomy Control**: Trust score, blast radius, and approval gate.
6. **Controlled Failover Execution**: SHA-256 plan hash binding, 16 prechecks, dry-run button, and rollback controls.
7. **Adaptive Multi-Provider Network Control**: Provider state, hysteresis hold time, oscillation risk, and safe failback trigger.
8. **Air-Gapped Federated Knowledge Exchange**: Privacy gate, cryptographic signature status, and export/import controls.
