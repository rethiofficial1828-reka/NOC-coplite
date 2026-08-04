#!/bin/bash

# Ensure we are in the project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Error: Virtual environment 'venv' not found. Please create it first."
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Add project root directory to PYTHONPATH
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

# 1. Generate dataset if missing
if [ ! -f "data/synthetic_telemetry.csv" ]; then
    echo "==> Generating synthetic telemetry training dataset..."
    python3 -m faultsim.generate_dataset
fi

# 2. Train model if missing
if [ ! -f "data/xgboost_model.json" ]; then
    echo "==> Training predictive XGBoost classifier..."
    python3 -m engine.model train
fi

# 3. Build RAG index if missing
if [ ! -f "data/faiss_index.bin" ]; then
    echo "==> Compiling local RAG vector index..."
    python3 -m copilot.rag
fi

# Cleanup old database to start clean
if [ -f "data/telemetry.db" ]; then
    echo "==> Resetting live telemetry database..."
    rm -f data/telemetry.db
fi

echo "==> Starting backend services..."

# Start simulation daemon
python3 -m faultsim.inject_fault > /tmp/noc_faultsim.log 2>&1 &
SIM_PID=$!
echo "  [OK] Telemetry Simulation daemon started (PID: $SIM_PID)"

# Start predictive engine API (Port 8000)
uvicorn engine.api:app --host 0.0.0.0 --port 8000 > /tmp/noc_engine.log 2>&1 &
ENGINE_PID=$!
echo "  [OK] Predictive Engine API started on port 8000 (PID: $ENGINE_PID)"

# Start copilot API (Port 8001)
uvicorn copilot.api:app --host 0.0.0.0 --port 8001 > /tmp/noc_copilot.log 2>&1 &
COPILOT_PID=$!
echo "  [OK] Copilot RAG & LLM API started on port 8001 (PID: $COPILOT_PID)"

# Handler to terminate background services on exit
cleanup() {
    echo ""
    echo "==> Terminating background services..."
    kill $SIM_PID $ENGINE_PID $COPILOT_PID 2>/dev/null
    echo "  Done."
    exit 0
}

trap cleanup INT TERM

echo "==> Starting Streamlit Dashboard..."
streamlit run ui/app.py --server.port 8501 --server.address 0.0.0.0

# Wait for Streamlit to exit
wait $SIM_PID $ENGINE_PID $COPILOT_PID
