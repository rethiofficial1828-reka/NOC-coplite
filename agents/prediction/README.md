# NOC Copilot — Production Prediction Agent

## Overview

The `PredictionAgent` is the predictive ML AI orchestration agent in NOC Copilot. It wraps the existing XGBoost predictive engine (`engine.model.RiskPredictor`) with **zero duplication of ML logic** and complete backward compatibility with existing API services, Streamlit dashboard, and SQLite telemetry schema.

---

## Architecture Diagram

```
+-----------------------------------------------------------------------------------+
|                                EVENT BUS SYSTEM                                   |
|               Emits 'telemetry.updated' -> Subscribed by PredictionAgent          |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                  AGENT LAYER                                      |
|   PredictionAgent (BaseAgent subclass, listens to telemetry, updates Context)     |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                 SERVICE LAYER                                     |
|    PredictionService (Normalizes risk scores, constructs PredictionResult model)   |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                VALIDATION LAYER                                   |
|    PredictionValidator (Range checks risk 0..1, TTI bounds, signal validation)    |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                               REPOSITORY LAYER                                    |
|    PredictionRepository (Fetches 30-sample window DF & calls engine.model)        |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                             EXISTING PREDICTION ENGINE                            |
|        RiskPredictor (engine/model.py -> XGBoost + Trend Formula heuristics)      |
+-----------------------------------------------------------------------------------+
```

---

## Component Layers

### 1. PredictionRepository (`agents.prediction.PredictionRepository`)
- Wraps `engine.model.RiskPredictor` without duplicating ML logic.
- Queries recent 30-sample telemetry DataFrame for rolling feature extraction (`engine.features.extract_features_from_df`).
- Provides methods:
  - `predict_for_interface(interface)`
  - `predict_fleet(interfaces)`
  - `predict_from_df(interface, df)`

### 2. PredictionValidator (`agents.prediction.PredictionValidator`)
- Validates risk scores (range 0.0 to 1.0), time-to-impact (>= -1.0), confidence scores, and non-empty contributing signals list.
- Raises `ValidationError` upon invalid prediction outputs.

### 3. PredictionService (`agents.prediction.PredictionService`)
- Business service layer.
- Transforms raw prediction dicts into strongly-typed `PredictionResult` Pydantic models.
- Provides `predict_for_interface`, `predict_for_telemetry_packet`, and `predict_fleet`.

### 4. PredictionAgent (`agents.prediction.PredictionAgent`)
- Subclasses `BaseAgent`.
- Automatically subscribes to `telemetry.updated` events on `EventBus`.
- Publishes `prediction.generated` events onto `EventBus`.
- Populates `ExecutionContext.results` and `ExecutionContext.shared_state`.

---

## Event Subscriptions and Publications

### Subscribed Event
- **Topic**: `telemetry.updated`
- **Action**: Triggers `PredictionAgent.execute()` automatically for affected interfaces.

### Published Event
- **Topic**: `prediction.generated`
- **Source**: `PredictionAgent`
- **Payload**: Serialized `PredictionResult` JSON object.
- **Metadata**:
  - `execution_id`: Context execution run ID.
  - `device_id`: Interface name.
  - `risk_score`: Computed failure risk score (0.0 to 1.0).
  - `confidence`: Prediction confidence score.
  - `timestamp`: UTC ISO timestamp string.

---

## Usage Example

```python
from agents.telemetry import TelemetryAgent
from agents.prediction import PredictionAgent, register_prediction_agent
from agents.events import EventBus

# Register PredictionAgent (automatically subscribes to telemetry.updated)
pred_agent = register_prediction_agent()

# Subscribe to prediction events
predictions = []
EventBus.get_global().subscribe("prediction.generated", lambda e: predictions.append(e))

# Run telemetry agent -> triggers prediction agent via EventBus
telemetry_agent = TelemetryAgent()
telemetry_agent.execute({"device_id": "Branch3-Uplink"})

print(f"Prediction events generated: {len(predictions)}")
if predictions:
    print(f"Risk Score: {predictions[0].metadata['risk_score']}")
```
