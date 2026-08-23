# NOC Copilot — Production Deployment Guide

**Version**: v1.0.0-rc1

This guide describes the installation, air-gapped deployment, network setup, hardware configuration, and service verification procedure for NOC Copilot.

---

## 1. Fresh Environment Requirements

- **Operating System**: Linux (Kali Linux, Ubuntu 22.04/24.04 LTS, Debian 12) or Windows 11 Host
- **Python Version**: Python 3.10+ (Recommended: Python 3.13)
- **Virtualization Support**: Oracle VirtualBox (for Guest VM deployment)
- **System Memory**: Minimum 4 GB RAM (Recommended: 8 GB allocated)
- **Disk Storage**: 5 GB free disk space
- **LLM Inference Provider**: Local Ollama service listening on `http://10.0.2.2:11434` (Host NAT gateway) or `http://127.0.0.1:11434` (Local)
- **Local Model**: `qwen3:1.7b` (Size: ~1.36 GB, Format: GGUF)

---

## 2. Step-by-Step Installation Procedure

### Step 1: Clone Repository & Create Virtual Environment
```bash
# Clone the repository
git clone https://github.com/rethiofficial1828/NOC-coplite.git
cd NOC-coplite

# Create virtual environment with Python 3.13
python3 -m venv venv
source venv/bin/activate
```

### Step 2: Install Required Dependencies
```bash
# Install core dependencies including PyYAML
pip install -r requirements.txt
```

### Step 3: Ollama & Local Model Setup
Ensure Ollama is running and has the `qwen3:1.7b` model loaded:

```bash
# On Host or Local Machine:
ollama pull qwen3:1.7b

# When running in VirtualBox Guest, verify NAT Gateway connectivity:
curl http://10.0.2.2:11434/api/version
```

### Step 4: Pre-Flight Startup Health & Diagnostic Verification
Run the unified pre-flight health diagnostic:

```bash
PYTHONPATH=. ./venv/bin/python3 run.py --check-only
```

Expected diagnostic output:
```text
======================================================================
          NOC COPILOT — UNIFIED STARTUP HEALTH & DIAGNOSTICS
======================================================================

OVERALL SYSTEM STATUS: 🟢 HEALTHY

--- System Environment Summary ---
  • Os                    : Linux (x86_64)
  • Python                : 3.13.2
  • Virtualization        : VirtualBox
  • Cpu Cores             : 4
  • Memory Gb             : 7.7 GB Total / 5.2 GB Available
  • Gpu                   : None (VirtualBox Guest Adapter)
  • Ollama Endpoint       : http://10.0.2.2:11434
  • Ollama Status         : ONLINE
  • Qwen Model            : qwen3:1.7b -> AVAILABLE
  • Dry Run Mode          : ENFORCED (DRY_RUN)

--- Subsystem Pre-Flight Checks ---
  [  OK  ] Python Runtime           : Python 3.13.2 (Compatible)
  [  OK  ] System Memory            : 5.2 GB available (Sufficient for air-gapped pipeline)
  [  OK  ] Ollama & Local LLM       : Ollama 0.31.2 online at http://10.0.2.2:11434; Model qwen3:1.7b ready
  [  OK  ] Telemetry SQLite DB      : DB accessible at data/telemetry.db
  [  OK  ] Topology Registry        : 4 devices registered
  [  OK  ] Knowledge / RAG Store    : Vector embeddings index and runbook chunks loaded
  [  OK  ] Execution Safety Boundary: DRY_RUN execution boundary strictly active
----------------------------------------------------------------------
```

---

## 3. Starting Operational Services

### Unified Single-Command Startup
To start all background microservices and the Streamlit operator UI in a single command:

```bash
./scripts/start_noc_copilot.sh
```

Or using the Python hardware-aware launcher:
```bash
PYTHONPATH=. ./venv/bin/python3 run.py
```

### Headless / Server-Only Startup
To launch the dashboard headlessly (e.g. inside CI/CD or background server):

```bash
PYTHONPATH=. ./venv/bin/streamlit run ui/app.py \
  --server.headless true \
  --server.port 8501 \
  --server.address 0.0.0.0
```

---

## 4. Operational Ports & Architecture

| Service | Port | Endpoint | Description |
|---|---|---|---|
| **Streamlit Dashboard** | `8501` | `http://localhost:8501` | Unified Incident Investigation Operator Console |
| **Copilot RAG & Reasoning** | `8001` | `http://localhost:8001/copilot` | FastAPI Reasoning & RAG Retrieval API |
| **Predictive Engine** | `8000` | `http://localhost:8000/predict` | FastAPI XGBoost Failure Risk Prediction API |
| **Local Ollama Inference** | `11434` | `http://10.0.2.2:11434` | Offline Qwen3:1.7B LLM Inference Service |

---

## 5. Security & DRY_RUN Safety Guarantees

1. **DRY_RUN Safety Boundary**: All failover triggers execute via `DryRunExecutionAdapter` by default. Real network mutations require explicit authorization and manual mode overrides.
2. **Zero Outbound Dependencies**: No telemetry, incident data, or embeddings leave the local host/VM.
3. **16 Pre-Execution Checks**: Evaluated before any network configuration changes can be committed.
4. **SHA-256 Plan Hash & Anti-Replay**: Every approval binds directly to the specific execution plan hash with non-reusable tokens.
5. **Deterministic PII Scrubbing**: 100% of IPs, MACs, credentials, and hostnames are sanitized before offline `.nockb` bundle exchanges.
