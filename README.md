# 🌐 Air-Gapped Predictive NOC Copilot

An AI-powered Network Operations Center copilot that predicts network failures before they happen and provides topology-aware incident intelligence, evidence-grounded remediation, explainable decisioning, historical pattern intelligence, closed-loop adaptive learning, and air-gapped federated intelligence — fully air-gapped, zero cloud dependencies.

![Version](https://img.shields.io/badge/Version-v1.1.0--rc1-blue)
![Python](https://img.shields.io/badge/Python-3.13-blue)
![XGBoost](https://img.shields.io/badge/ML-XGBoost-orange)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-red)
![Tests](https://img.shields.io/badge/Tests-19%2C351%20Passing-brightgreen)
![Targeted](https://img.shields.io/badge/Targeted%20Suites-391%20Passing-brightgreen)
![Golden](https://img.shields.io/badge/Golden%20Scenario-13%2F13%20Passing-success)
![Stress](https://img.shields.io/badge/Stress-100k%20Passed-success)

## 🌟 NOC-Copilot v1.1 Intelligence Capabilities

NOC-Copilot v1.1 introduces a 5-phase intelligence architecture unified in an end-to-end **Golden Incident Scenario**:

1. **Topology-Aware Incident Intelligence (Phase 1)**: Real-time graph traversal, BFS blast-radius calculation, downstream device impact percentages, and single points of failure (SPOF) identification.
2. **Evidence-Centric Cross-Agent Investigation (Phase 2)**: Read-only unified evidence lineage tracking cross-agent contributions with strict provenance (`OBSERVED`, `PREDICTED`, `INFERRED`, `HISTORICAL`, `SIMULATION`).
3. **Confidence & Decision Explainability (Phase 3)**: Concise, factored decision explanation reports detailing why candidate paths won, safety constraints, and factors that would change autonomy policy outcomes.
4. **Adaptive Incident Learning & Historical Pattern Intelligence (Phase 4)**: Multidimensional comparison, incident fingerprinting, and pattern clustering against historical incident archives to adjust confidence.
5. **Closed-Loop Adaptive Decision Learning (Phase 5)**: Post-hoc delta evaluation comparing predicted vs observed telemetry to compute prediction error, bounded decision quality $[0.0, 1.0]$, and factual lessons learned.
6. **Golden Incident Scenario Integration**: Deterministic end-to-end lifecycle verification for `Branch3-Uplink` WAN degradation with zero policy mutation and strict `DRY_RUN` safety boundaries.

## 📚 Productization Documentation

- 📋 [PRODUCT_INVENTORY.md](file:///home/kali/Downloads/NOC-coplite/PRODUCT_INVENTORY.md) — Comprehensive inventory of all Atomic Agents, services, and UI panels.
- 🎯 [PRODUCT_DEMO_GUIDE.md](file:///home/kali/Downloads/NOC-coplite/PRODUCT_DEMO_GUIDE.md) — Step-by-step demonstration walkthrough for operators and executive reviewers.
- 🧪 [NETWORK_LAB_GUIDE.md](file:///home/kali/Downloads/NOC-coplite/NETWORK_LAB_GUIDE.md) — Technical guide for executing and customizing network lab simulation scenarios.
- 🏗️ [ARCHITECTURE.md](file:///home/kali/Downloads/NOC-coplite/ARCHITECTURE.md) — System architecture specification (Atomic Agents, Structured memory, RAG/CAG).
- 🚀 [DEPLOYMENT_GUIDE.md](file:///home/kali/Downloads/NOC-coplite/DEPLOYMENT_GUIDE.md) — Production deployment, VirtualBox NAT networking setup, and system verification instructions.
- 📊 [PRODUCT_ACCEPTANCE_REPORT.md](file:///home/kali/Downloads/NOC-coplite/PRODUCT_ACCEPTANCE_REPORT.md) — Final validation report and operational readiness status.

## 🏗️ Architecture Overview

```
┌─────────────────┐      ┌──────────────────┐       ┌─────────────────┐
│  Fault Simulator │────▶│ Predictive Engine│────▶  │  NOC Copilot    │
│  (Telemetry)     │     │  (XGBoost ML)    │       │  (RAG + LLM)    │
└─────────────────┘      └──────────────────┘       └─────────────────┘
        │                       │                          │
        ▼                       ▼                          ▼
   SQLite DB              FastAPI :8000            FastAPI :8001
                                                           │
                          ┌──────────────────┐             │
                          │ Streamlit Dashboard│◀──────────┘
                          │     :8501          │
                          └──────────────────┘
```

## 🚀 Quick Start

```bash
# 1. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies (including PyYAML)
pip install -r requirements.txt

# 3. Verify runtime health & diagnostics
PYTHONPATH=. ./venv/bin/python3 run.py --check-only

# 4. Launch all services with the unified starter
./scripts/start_noc_copilot.sh

# 5. Open dashboard
# http://localhost:8501
```

## 📂 Project Structure

```
├── agents/
│   ├── federated_intelligence/ # Sprint 20 Air-Gapped Federated Incident Intelligence & Signed Knowledge Exchange
│   │   ├── federated_models.py       # Pydantic V2 Domain Models & Enums
│   │   ├── privacy_sanitizer.py     # PrivacySanitizer (Deterministic PII Scrubbing)
│   │   ├── crypto_signer.py         # CryptoSigner (HMAC/RSA Signatures)
│   │   ├── bundle_exporter.py       # BundleExporter (Offline JSON Bundles)
│   │   ├── bundle_importer.py       # BundleImporter (Verification Gates)
│   │   ├── federated_knowledge_base.py # FederatedKnowledgeBaseManager (RAG Indexing)
│   │   ├── federated_intelligence_service.py # FederatedIntelligenceService
│   │   └── federated_intelligence_agent.py   # FederatedIntelligenceAgent
│   ├── adaptive_failover/ # Sprint 19 Adaptive Multi-Provider Failover & Stability Intelligence
│   │   ├── adaptive_models.py       # Pydantic V2 Domain Models & Enums
│   │   ├── provider_monitor.py      # ProviderMonitor (Trend Tracking)
│   │   ├── degradation_detector.py # DegradationDetector (Multi-Signal Correlation)
│   │   ├── stability_engine.py      # StabilityEngine (Hysteresis & Flap Prevention)
│   │   ├── adaptive_path_scoring.py # AdaptivePathScoringEngine (Temporal Scoring)
│   │   ├── failover_trigger.py      # FailoverTriggerEngine
│   │   ├── continuous_verifier.py   # ContinuousVerificationEngine
│   │   ├── failback_engine.py       # FailbackEngine (Recovery Stability Window)
│   │   ├── transition_manager.py    # NetworkTransitionManager (State Machine)
│   │   ├── transition_memory.py     # TransitionMemory (Historical Evidence)
│   │   ├── adaptive_failover_service.py # AdaptiveFailoverService
│   │   └── adaptive_failover_agent.py   # AdaptiveFailoverAgent
│   ├── failover/        # Sprint 18 Controlled Failover Execution & Verification Engine
│   │   ├── failover_models.py       # Pydantic V2 Domain Models & Enums
│   │   ├── approval_manager.py      # ApprovalManager (Hash-Bound & Anti-Replay)
│   │   ├── pre_execution_validator.py # PreExecutionValidator (16 Prechecks)
│   │   ├── execution_adapter.py     # IExecutionAdapter Interface
│   │   ├── dry_run_adapter.py       # DryRunExecutionAdapter
│   │   ├── authorized_execution_adapter.py # AuthorizedNetworkAdapter
│   │   ├── post_execution_verifier.py # PostExecutionVerifier (Closed-Loop)
│   │   ├── rollback_engine.py       # RollbackEngine (Restoration Verification)
│   │   ├── failover_service.py      # FailoverService
│   │   └── failover_agent.py        # FailoverAgent
│   ├── path_decision/   # Sprint 17 Path & Provider Decision Engine
│   │   ├── path_discovery.py        # PathDiscoveryEngine
│   │   ├── provider_health.py       # ProviderHealthEngine
│   │   ├── path_evaluator.py        # PathEvaluationEngine
│   │   ├── economics_engine.py      # NetworkEconomicsEngine
│   │   ├── path_scoring.py          # PathScoringEngine
│   │   ├── path_simulator.py        # PathSimulationEngine
│   │   ├── recommendation_engine.py  # FailoverRecommendationEngine
│   │   ├── decision_service.py      # PathDecisionService
│   │   └── path_decision_agent.py   # PathDecisionAgent
│   ├── reasoning/       # Enterprise Reasoning Subsystem
│   ├── trust/           # Trust, Verification & Safe Autonomy
│   ├── premortem/       # Pre-Mortem Forecasting Engine
│   └── runtime/         # Cross-Platform AI Hardware Acceleration
├── engine/              # Predictive ML Engine
│   ├── api.py           # FastAPI server (port 8000)
│   ├── features.py      # Rolling-window feature extraction
│   └── model.py         # XGBoost RiskPredictor
├── copilot/             # RAG + LLM Copilot
│   ├── api.py           # FastAPI server (port 8001)
│   ├── rag.py           # TF-IDF knowledge retriever
│   ├── llm.py           # Ollama/Phi-3 interface + fallback
│   └── docs/            # Runbook knowledge base
├── faultsim/            # Fault Simulation
│   ├── generate_dataset.py  # Synthetic training data
│   └── inject_fault.py      # Live fault injection daemon
├── ui/
│   └── app.py           # Streamlit dashboard
├── tests/
│   ├── test_path_decision.py  # 40 Sprint 17 Path Decision tests
│   └── ...
├── .github/workflows/
│   └── test.yml         # CI/CD pipeline
├── test_master.py       # Master test runner
├── test_config.yml      # Test scenarios in YAML
├── topology_map.html    # Visual network topology
├── requirements.txt     # Python dependencies
└── run.sh               # One-command launcher
```

## 🧪 Testing & Validation

```bash
# Run full repository test suite (19,351 tests)
PYTHONPATH=. ./venv/bin/python3 -m pytest -q

# Run Golden Scenario end-to-end integration suite (13 tests)
PYTHONPATH=. ./venv/bin/python3 -m pytest -q tests/test_golden_scenario.py

# Run targeted v1.1 intelligence test suites (391 tests)
PYTHONPATH=. ./venv/bin/python3 -m pytest -q tests/test_failover_agent.py tests/test_adaptive_failover.py tests/test_premortem_agent.py tests/test_orchestrator_ai.py tests/test_trust_agent.py tests/test_path_decision.py tests/test_topology_agent.py tests/test_ui_streamlit.py tests/test_golden_scenario.py
```

| Validation Category | Test Suites | Discovered Tests | Passed | Status |
|---|---|---|---|---|
| **Repository Baseline** | Full 25-module pytest suite | 19,352 | **19,351** (1 skipped) | **PASS** |
| **v1.1 Multi-Agent Intelligence** | 9 targeted intelligence suites | 391 | **391** | **PASS** |
| **Golden Incident Scenario** | `tests/test_golden_scenario.py` | 13 | **13** | **PASS** |
| **Deterministic Stress Matrix** | Deterministic parametric matrix | 100,000 | **100,000** | **PASS** |
| **Streamlit UI Automation** | Headless UI & data labels | 50 | **50** | **PASS** |
| **Startup Diagnostics** | Hardware & runtime capability | 37 | **37** | **PASS** |

## 🔧 Fault Injection

```bash
# Simulate congestion
PYTHONPATH=$(pwd) python3 faultsim/inject_fault.py congestion

# Return to healthy
PYTHONPATH=$(pwd) python3 faultsim/inject_fault.py healthy
```

## 🌐 Network Topology

Based on real campus network reconnaissance:

| Zone | Subnet | Purpose |
|---|---|---|
| Campus Wi-Fi | 10.50.0.0/22 | Student/faculty internet |
| Lab Network | 192.168.56.0/24 | Security labs (air-gapped) |
| Wired LAN | domain.name | Faculty PCs, printers |

## 📡 API Endpoints

### Predictive Engine (`:8000`)
- `GET /health` — Health check
- `GET /predict?interface=Branch3-Uplink` — Risk prediction

### Copilot (`:8001`)
- `GET /health` — Health check
- `POST /copilot` — RAG-grounded recommendations

## 📄 License

MIT License — College Network Security Lab Project
