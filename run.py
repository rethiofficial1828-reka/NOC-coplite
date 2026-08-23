#!/usr/bin/env python3
"""
NOC Copilot Cross-Platform Entrypoint & Hardware-Aware Launcher.

Provides portable startup for Windows native, Linux native, Kali Linux, and virtualized guest environments.
Validates dependencies, detects hardware/GPU capabilities, probes Ollama & Qwen3:1.7B,
selects inference backend, and launches required NOC Copilot services.
"""

import argparse
import os
import sys
import time
import subprocess
from pathlib import Path

# Ensure root directory is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.runtime import (
    CapabilityManager,
    CapabilityStatus,
    InferenceBackend,
    RuntimeHealth,
    RuntimeService,
)
from config.settings import COPILOT_PORT, ENGINE_PORT, OLLAMA_MODEL, STREAMLIT_PORT


def print_banner():
    print("=" * 65)
    print("      NOC COPILOT — ENTERPRISE AI OPERATIONAL PLATFORM")
    print("     Cross-Platform Hardware & Acceleration Launcher")
    print("=" * 65)


def run_diagnostics() -> bool:
    """Perform runtime hardware, database, and LLM backend diagnostics."""
    from agents.runtime.startup_health import StartupHealthService
    health_svc = StartupHealthService()
    return health_svc.print_startup_report()


def start_services():
    """Launch NOC Copilot backend services."""
    python_bin = sys.executable
    print(f"\n🚀 Launching NOC Copilot Services using Python: {python_bin}")

    # Launch Engine API
    cmd_engine = [python_bin, "-m", "uvicorn", "engine.api:app", "--host", "0.0.0.0", "--port", str(ENGINE_PORT)]
    print(f"  [1/3] Starting Predictive Engine API on port {ENGINE_PORT}...")
    p_engine = subprocess.Popen(cmd_engine, cwd=str(PROJECT_ROOT))

    # Launch Copilot API
    cmd_copilot = [python_bin, "-m", "uvicorn", "copilot.api:app", "--host", "0.0.0.0", "--port", str(COPILOT_PORT)]
    print(f"  [2/3] Starting Copilot RAG & LLM API on port {COPILOT_PORT}...")
    p_copilot = subprocess.Popen(cmd_copilot, cwd=str(PROJECT_ROOT))

    # Launch Streamlit UI
    cmd_ui = [python_bin, "-m", "streamlit", "run", "ui/app.py", "--server.port", str(STREAMLIT_PORT), "--server.address", "0.0.0.0"]
    print(f"  [3/3] Starting Streamlit Dashboard on port {STREAMLIT_PORT}...")
    p_ui = subprocess.Popen(cmd_ui, cwd=str(PROJECT_ROOT))

    print("\n✅ All services started successfully!")
    print(f"   Dashboard URL : http://localhost:{STREAMLIT_PORT}")
    print(f"   Copilot API   : http://localhost:{COPILOT_PORT}")
    print(f"   Engine API    : http://localhost:{ENGINE_PORT}")
    print("\nPress Ctrl+C to terminate services.")

    try:
        p_ui.wait()
    except KeyboardInterrupt:
        print("\nStopping services...")
        p_engine.terminate()
        p_copilot.terminate()
        p_ui.terminate()
        print("Shutdown complete.")


def main():
    parser = argparse.ArgumentParser(description="NOC Copilot Cross-Platform Hardware & Acceleration Launcher")
    parser.add_argument("--check-only", action="store_true", help="Run hardware & runtime capability check without starting services")
    args = parser.parse_args()

    print_banner()
    is_ready = run_diagnostics()

    if args.check_only:
        sys.exit(0 if is_ready else 1)

    if not is_ready:
        print("\n❌ Cannot start services: Required runtime backend is unavailable.")
        sys.exit(1)

    start_services()


if __name__ == "__main__":
    main()
