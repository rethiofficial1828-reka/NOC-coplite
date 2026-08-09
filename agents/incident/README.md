# NOC Copilot — Production Incident Agent & Subsystem

## Overview

The **Incident Management Subsystem** transforms predictive ML risk predictions (`prediction.generated`) into enterprise-grade, deduplicated network incidents (`INC-YYYY-XXXXXX`). It enforces lifecycle state transitions, maintains audit timelines, calculates business impact, and manages incident ownership.

---

## Architecture Diagram

```
+-----------------------------------------------------------------------------------+
|                                EVENT BUS SYSTEM                                   |
|             Emits 'prediction.generated' -> Subscribed by IncidentAgent           |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                  AGENT LAYER                                      |
|   IncidentAgent (BaseAgent subclass, listens to predictions, publishes events)    |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                 SERVICE LAYER                                     |
|    IncidentService (Coordinates deduplication, state machine, & rules engine)     |
+-----------------------------------------------------------------------------------+
     |                                    |                                    |
     v                                    v                                    v
+------------------+            +-------------------+            +------------------+
|  IncidentRules   |            |IncidentStateMachine|           | IncidentValidator|
| (Risk->Severity) |            | (NEW->OPEN->...)  |            | (Schema checks)  |
+------------------+            +-------------------+            +------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                               REPOSITORY LAYER                                    |
|    IncidentRepository (Thread-safe SQLite storage for incidents & timelines)      |
+-----------------------------------------------------------------------------------+
```

---

## Incident State Machine

```
                      +-------------------+
                      |        NEW        |
                      +-------------------+
                        /               \
                       v                 v
             +-------------------+    +-------------------+
             |       OPEN        |--->|      CLOSED       |
             +-------------------+    +-------------------+
             /     |       |     \             ^
            v      v       v      v            |
    +-------+  +-------+ +-------+ +---------+ |
    |  ACK  |->|IN_PROG|->|MITIGAT|->|RESOLVED |-+
    +-------+  +-------+ +-------+ +---------+
```

### State Definitions
- **NEW**: Initial unverified incident record.
- **OPEN**: Active verified incident requiring NOC attention.
- **ACKNOWLEDGED**: Incident claimed by an operator or team.
- **IN_PROGRESS**: Remediation or troubleshooting underway.
- **MITIGATED**: Temporary fix or QoS change applied.
- **RESOLVED**: Root cause resolved or risk recovered.
- **CLOSED**: Finalized archive state.

---

## Severity Mapping Rules

Continuous predictive risk scores map to severity levels:
- **`>= 0.85`** -> `CRITICAL`
- **`>= 0.70`** -> `HIGH`
- **`>= 0.45`** -> `MEDIUM`
- **`>= 0.25`** -> `LOW`
- **`< 0.25`**  -> `INFO` (Auto-resolves active incidents when risk score drops below `0.20`)

---

## Deduplication Logic

When a new prediction event arrives:
1. `IncidentService` queries `IncidentRepository` for an active (non-RESOLVED, non-CLOSED) incident matching `(device_id, incident_type)`.
2. **If an active incident exists**:
   - Updates the existing record (`risk_score`, `time_to_impact`, `contributing_signals`, `updated_at`).
   - Appends a timeline audit event (`PREDICTION_UPDATED` or `SEVERITY_CHANGED`).
   - Emits `incident.updated` or `incident.severity_changed` event.
   - If risk score drops below `0.20`, automatically transitions to `RESOLVED` and emits `incident.resolved`.
3. **If no active incident exists** and risk score is `>= 0.25`:
   - Generates a new sequential ID (e.g. `INC-2026-000001`).
   - Creates a new `IncidentRecord` in status `OPEN`.
   - Appends initial `CREATED` timeline audit entry.
   - Emits `incident.created` event.

---

## Published Events

- `incident.created`
- `incident.updated`
- `incident.severity_changed`
- `incident.resolved`
- `incident.closed`

**Payload**: Serialized `IncidentRecord` model.
**Metadata**: `execution_id`, `incident_id`, `device_id`, `severity`, `status`, `timestamp`.

---

## Usage Example

```python
from agents.telemetry import TelemetryAgent
from agents.prediction import register_prediction_agent
from agents.incident import IncidentAgent, register_incident_agent
from agents.events import EventBus

# Register agent pipeline
pred_agent = register_prediction_agent()
inc_agent = register_incident_agent()

# Subscribe to incident events
incidents = []
EventBus.get_global().subscribe("incident.created", lambda e: incidents.append(e))

# Run pipeline: Telemetry -> Prediction -> Incident (reactive event-driven pipeline)
telemetry_agent = TelemetryAgent()
telemetry_agent.execute({"device_id": "Branch3-Uplink"})

print(f"Incidents created: {len(incidents)}")
if incidents:
    print(f"Incident ID: {incidents[0].metadata['incident_id']}")
    print(f"Severity: {incidents[0].metadata['severity']}")
```
