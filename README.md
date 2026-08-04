# 🌐 Air-Gapped Predictive NOC Copilot

An AI-powered Network Operations Center copilot that predicts network failures before they happen and provides RAG-grounded remediation guidance — fully air-gapped, zero cloud dependencies.

![Python](https://img.shields.io/badge/Python-3.13-blue)
![XGBoost](https://img.shields.io/badge/ML-XGBoost-orange)
![FastAPI](https://img.shields.io/badge/API-FastAPI-green)
![Tests](https://img.shields.io/badge/Tests-31%20Passing-brightgreen)

## 🏗️ Architecture

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

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch all services
./run.sh

# 4. Open dashboard
# http://localhost:8501
```

## 📂 Project Structure

```
noc-copilot/
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
├── .github/workflows/
│   └── test.yml         # CI/CD pipeline
├── test_master.py       # Master test runner (31 tests)
├── test_config.yml      # Test scenarios in YAML
├── topology_map.html    # Visual network topology
├── requirements.txt     # Python dependencies
└── run.sh               # One-command launcher
```

## 🧪 Testing

```bash
# Run all 31 tests (Unit + Integration + E2E + Edge + Stress)
PYTHONPATH=$(pwd) python3 test_master.py
```

| Category | Tests | Coverage |
|---|---|---|
| Unit Tests | 9 | Modules, features, model, RAG, LLM |
| Integration | 7 | API contracts, error codes |
| E2E Scenarios | 4 | Healthy → Congestion → Copilot → Recovery |
| Edge Cases | 8 | Empty DB, unknown interfaces, extremes |
| Stress Tests | 3 | Rapid-fire APIs, DB consistency |

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
