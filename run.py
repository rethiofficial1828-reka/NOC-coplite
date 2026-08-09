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
    """Perform runtime hardware & LLM backend diagnostics."""
    print("\n🔍 Inspecting Host Runtime Environment & Acceleration Capabilities...")
    service = RuntimeService()
    caps = service.get_capabilities(force_refresh=True)

    print(f"\n[OS Platform]          : {caps.operating_system.value} ({caps.architecture})")
    print(f"[Python Version]       : {caps.python_version}")
    print(f"[Virtualization]       : {caps.virtualization_environment.value}")
    print(f"[System CPU Cores]     : {caps.cpu_count}")
    print(f"[System Memory]        : {caps.total_memory_gb:.1f} GB Total / {caps.available_memory_gb:.1f} GB Available")
    
    print(f"\n[GPU Hardware]         : {caps.gpu_vendor.value} - {caps.gpu_name}")
    print(f"[GPU Status]           : {caps.gpu_status.value}")
    print(f"[Guest GPU Exposure]   : {'Exposed to Guest' if caps.is_guest_gpu_exposed else 'NOT EXPOSED TO GUEST'}")
    if caps.gpu_memory_mb > 0:
        print(f"[VRAM Memory]          : {caps.gpu_memory_mb:.0f} MB")
        print(f"[Driver Version]       : {caps.gpu_driver_version}")

    print(f"\n[Ollama Endpoint]      : {caps.ollama_endpoint}")
    print(f"[Ollama Location]      : {caps.ollama_location.value}")
    print(f"[Ollama Status]        : {'ONLINE (' + caps.ollama_version + ')' if caps.ollama_available else 'OFFLINE'}")
    print(f"[Primary Model]        : {caps.qwen_model} -> {'AVAILABLE' if caps.qwen_available else 'MISSING'}")

    print(f"\n[Selected Backend]     : {caps.selected_backend.value}")
    print(f"[Runtime Health]       : {caps.runtime_health.value}")

    if caps.degradation_reason:
        print(f"\n⚠️ Degradation Rationale : {caps.degradation_reason}")

    print("-" * 65)
    return caps.runtime_health != RuntimeHealth.UNAVAILABLE


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
