import os

# Project root directory (parent directory of config package)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VERSION = "1.5.0-dev"
__version__ = VERSION

# Key directories
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DOCS_DIR = os.path.join(PROJECT_ROOT, "copilot", "docs")

# Core data & model file paths
MODEL_PATH = os.path.join(DATA_DIR, "xgboost_model.json")
DB_PATH = os.path.join(DATA_DIR, "telemetry.db")
CHUNKS_PATH = os.path.join(DATA_DIR, "chunks.txt")
INDEX_PATH = os.path.join(DATA_DIR, "faiss_index.bin")

# External service URLs & Ports
OLLAMA_URL = "http://localhost:11434/api/generate"
ENGINE_PORT = 8000
COPILOT_PORT = 8001
STREAMLIT_PORT = 8501

# LLM Provider Configuration Defaults
LLM_PROVIDER_TYPE = "ollama"
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "qwen3:1.7b"
OLLAMA_TIMEOUT_SEC = 300.0
OLLAMA_RETRY_COUNT = 3
OLLAMA_TEMPERATURE = 0.2
OLLAMA_TOP_P = 0.9
OLLAMA_MAX_TOKENS = 2048

# ---------------------------------------------------------------------------
# Device Registry — single source of truth for all monitored network nodes.
# The "name" field is used as the interface key in the telemetry database.
# ---------------------------------------------------------------------------
DEVICE_REGISTRY = [
    {
        "id": "core-01",
        "name": "Campus Core",
        "type": "Core Switch",
        "location": "Main Building",
    },
    {
        "id": "fw-01",
        "name": "Firewall",
        "type": "Firewall",
        "location": "Data Center",
    },
    {
        "id": "rtr-01",
        "name": "Router 1",
        "type": "Router",
        "location": "Block A",
    },
    {
        "id": "branch3-uplink",
        "name": "Branch3-Uplink",
        "type": "WAN Interface",
        "location": "Branch Office",
    },
]

# Convenience: ordered list of interface names (matches DB "interface" column)
DEVICE_NAMES = [d["name"] for d in DEVICE_REGISTRY]

# ---------------------------------------------------------------------------
# WAN Provider Registry (v1.5 Multi-WAN N-Provider Model)
# Configuration-driven provider definitions supporting both physical lab
# endpoints (ISP-A, ISP-B) and simulated candidates (ISP-C, ISP-D).
# ---------------------------------------------------------------------------
WAN_PROVIDER_REGISTRY = [
    {
        "provider_id": "ISP-A",
        "provider_name": "ISP-A",
        "wan_interface": "Branch3-Uplink",
        "source_device": "branch3-uplink",
        "next_hop": "10.10.1.1",
        "priority": 1,
        "bandwidth_mbps": 1000.0,
        "is_primary": True,
        "is_simulated": False,
        "metadata": {
            "provider_type": "Primary Fiber",
            "sla_latency_max_ms": 50.0,
            "sla_loss_max_percent": 1.0,
        },
    },
    {
        "provider_id": "ISP-B",
        "provider_name": "ISP-B",
        "wan_interface": "Branch3-Backup",
        "source_device": "branch3-uplink",
        "next_hop": "10.10.2.1",
        "priority": 2,
        "bandwidth_mbps": 500.0,
        "is_primary": False,
        "is_simulated": False,
        "metadata": {
            "provider_type": "Secondary Broadband",
            "sla_latency_max_ms": 60.0,
            "sla_loss_max_percent": 2.0,
        },
    },
    {
        "provider_id": "ISP-C",
        "provider_name": "ISP-C",
        "wan_interface": "Branch3-Cellular",
        "source_device": "branch3-uplink",
        "next_hop": "10.10.3.1",
        "priority": 3,
        "bandwidth_mbps": 250.0,
        "is_primary": False,
        "is_simulated": True,
        "metadata": {
            "provider_type": "5G LTE Backup",
            "sla_latency_max_ms": 70.0,
            "sla_loss_max_percent": 3.0,
        },
    },
    {
        "provider_id": "ISP-D",
        "provider_name": "ISP-D",
        "wan_interface": "Branch3-Satellite",
        "source_device": "branch3-uplink",
        "next_hop": "10.10.4.1",
        "priority": 4,
        "bandwidth_mbps": 100.0,
        "is_primary": False,
        "is_simulated": True,
        "metadata": {
            "provider_type": "LEO Satellite Backup",
            "sla_latency_max_ms": 90.0,
            "sla_loss_max_percent": 4.0,
        },
    },
]

# ---------------------------------------------------------------------------
# Site Registry (v1.3 / v1.5) — Hierarchical physical and logical site grouping.
# Maps constituent device IDs and interfaces into manageable operational sites.
# ---------------------------------------------------------------------------
SITE_REGISTRY = [
    {
        "site_id": "site-campus",
        "site_name": "Campus Main Site",
        "site_type": "CAMPUS",
        "location": "Main Campus",
        "device_ids": ["core-01", "rtr-01"],
        "primary_providers": ["ISP-A"],
        "backup_providers": ["ISP-B"],
    },
    {
        "site_id": "site-dc",
        "site_name": "Data Center HQ",
        "site_type": "DATACENTER",
        "location": "Data Center",
        "device_ids": ["fw-01", "hub"],
        "primary_providers": ["ISP-B"],
        "backup_providers": ["ISP-A"],
    },
    {
        "site_id": "site-branch3",
        "site_name": "Branch Office 3",
        "site_type": "BRANCH",
        "location": "Branch Office",
        "device_ids": ["branch3-uplink"],
        "primary_providers": ["ISP-A"],
        "backup_providers": ["ISP-B", "ISP-C", "ISP-D"],
    },
    {
        "site_id": "site-branch1",
        "site_name": "Branch Office 1",
        "site_type": "BRANCH",
        "location": "Branch 1",
        "device_ids": ["branch1"],
        "primary_providers": ["ISP-A"],
        "backup_providers": ["ISP-B"],
    },
]

# ---------------------------------------------------------------------------
# Network Control-Plane Configuration (v1.2)
# ---------------------------------------------------------------------------
LAB_CONTROL_PLANE = os.getenv("NOC_LAB_CONTROL_PLANE", "none")
SUPPORTED_CONTROL_PLANES = ["none", "gnmi", "netconf", "frr_zapi"]

# ---------------------------------------------------------------------------
# Production Authorization & Safety Invariants (v1.4 / v1.5)
# ---------------------------------------------------------------------------
PRODUCTION_AUTHORIZED = False
