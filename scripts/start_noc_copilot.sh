#!/usr/bin/env bash
# ==============================================================================
# NOC Copilot — Unified Production-Grade Launcher
#
# Launches all backend microservices, validates runtime health, and starts the
# Streamlit Operator Dashboard in an air-gapped, zero-outbound environment.
# ==============================================================================

set -e

# Resolve script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "======================================================================"
echo "          NOC COPILOT — UNIFIED PLATFORM LAUNCHER"
echo "======================================================================"

# 1. Virtual environment resolution
if [ -d "venv" ]; then
    PYTHON_BIN="$PROJECT_ROOT/venv/bin/python3"
    STREAMLIT_BIN="$PROJECT_ROOT/venv/bin/streamlit"
    UVICORN_BIN="$PROJECT_ROOT/venv/bin/uvicorn"
elif command -v python3 &>/dev/null; then
    PYTHON_BIN="$(command -v python3)"
    STREAMLIT_BIN="$(command -v streamlit || echo 'streamlit')"
    UVICORN_BIN="$(command -v uvicorn || echo 'uvicorn')"
else
    echo "❌ Error: Python 3 environment not found. Please create 'venv'."
    exit 1
fi

export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# 2. Run Pre-Flight Startup Health & Diagnostic Check
echo "🔍 Running pre-flight system diagnostics..."
"$PYTHON_BIN" run.py --check-only || {
    echo "⚠️ Warning: Pre-flight diagnostics returned non-healthy status, continuing in degraded/safe mode..."
}

# 3. Ensure Data Directory and Telemetry DB exist
mkdir -p "$PROJECT_ROOT/data"

# 4. Starting Backend Services
echo ""
echo "🚀 Starting NOC Copilot Backend Services..."

# Start Telemetry Simulator Daemon
"$PYTHON_BIN" -m faultsim.inject_fault > /tmp/noc_faultsim.log 2>&1 &
SIM_PID=$!
echo "  [OK] Telemetry Simulator Daemon started (PID: $SIM_PID)"

# Start Predictive Engine API (Port 8000)
"$PYTHON_BIN" -m uvicorn engine.api:app --host 0.0.0.0 --port 8000 > /tmp/noc_engine.log 2>&1 &
ENGINE_PID=$!
echo "  [OK] Predictive Engine API started on port 8000 (PID: $ENGINE_PID)"

# Start Copilot RAG & Reasoning API (Port 8001)
"$PYTHON_BIN" -m uvicorn copilot.api:app --host 0.0.0.0 --port 8001 > /tmp/noc_copilot.log 2>&1 &
COPILOT_PID=$!
echo "  [OK] Copilot Reasoning & RAG API started on port 8001 (PID: $COPILOT_PID)"

# Trap handler for clean shutdown
cleanup() {
    echo ""
    echo "🛑 Shutting down NOC Copilot services..."
    kill "$SIM_PID" "$ENGINE_PID" "$COPILOT_PID" 2>/dev/null || true
    echo "✅ Shutdown complete."
    exit 0
}
trap cleanup INT TERM EXIT

echo ""
echo "======================================================================"
echo "✅ NOC Copilot Services Active:"
echo "   • Streamlit Dashboard : http://localhost:8501"
echo "   • Copilot Reasoning   : http://localhost:8001"
echo "   • Predictive Engine   : http://localhost:8000"
echo "   • Telemetry Simulator : Background Active"
echo "======================================================================"
echo ""

# 5. Launch Streamlit UI Dashboard
"$STREAMLIT_BIN" run ui/app.py --server.port 8501 --server.address 0.0.0.0
