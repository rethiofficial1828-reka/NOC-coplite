# NOC Copilot — Production Recommendation Agent

## Overview

The `RecommendationAgent` transforms active network incidents (`IncidentRecord`) into structured, production-ready remediation and rollback plans (`RecommendationRecord`). It maps incident categories to reusable remediation templates, formats platform-specific CLI commands, assesses business risk, and generates verification and rollback procedures.

---

## Architecture Diagram

```
+-----------------------------------------------------------------------------------+
|                                EVENT BUS SYSTEM                                   |
|       Emits 'incident.created' / 'incident.updated' -> RecommendationAgent        |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                  AGENT LAYER                                      |
|   RecommendationAgent (BaseAgent subclass, listens to incidents, emits recs)      |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                 SERVICE LAYER                                     |
|   RecommendationService (Matches templates, formats commands, saves records)     |
+-----------------------------------------------------------------------------------+
     |                                    |                                    |
     v                                    v                                    v
+------------------------+      +-------------------+      +------------------------+
| RecommendationTemplates|      |RecommendationRules|      |RecommendationValidator |
| (Congestion, Drops...) |      | (Severity->Prio)  |      | (Schema validation)    |
+------------------------+      +-------------------+      +------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                               REPOSITORY LAYER                                    |
|   RecommendationRepository (Thread-safe SQLite storage for REC-YYYY-XXXXXX)      |
+-----------------------------------------------------------------------------------+
```

---

## Remediation Templates

Pre-configured remediation templates include:
- **`NETWORK_CONGESTION`**: Egress QoS bandwidth shaping and BGP local preference tuning.
- **`LATENCY_SPIKE`**: Queue buffer expansion and weighted fair queueing.
- **`EGRESS_PACKET_DROPS`**: TX ring buffer size expansion and CRC diagnostic verification.
- **`ROUTING_INSTABILITY`**: BGP route dampening and keepalive/holdtime timer extensions.
- **`WAN_FAILURE`**: Automated failover to secondary WAN transport link.

Each template defines:
- High-level summary & root-cause hypothesis.
- Ordered execution steps with CLI commands & verification commands.
- Detailed rollback plan with steps and revert CLI commands.
- Impact assessment (business impact, affected services, risk level, downtime expectation).
- Automation feasibility flag (`automation_possible=True`).

---

## Published Events

- **Topic**: `recommendation.generated`
- **Source**: `RecommendationAgent`
- **Payload**: Serialized `RecommendationRecord` JSON object.
- **Metadata**:
  - `execution_id`: Context run identifier.
  - `recommendation_id`: Sequential ID (e.g. `REC-2026-000001`).
  - `incident_id`: Associated incident ID (e.g. `INC-2026-000001`).
  - `device_id`: Monitored device/interface name.
  - `priority`: Remediation priority enum (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).
  - `timestamp`: UTC ISO timestamp string.

---

## Usage Example

```python
from agents.telemetry import TelemetryAgent
from agents.prediction import register_prediction_agent
from agents.incident import register_incident_agent
from agents.recommendation import RecommendationAgent, register_recommendation_agent
from agents.events import EventBus

# Register full multi-agent workflow pipeline
pred_agent = register_prediction_agent()
inc_agent = register_incident_agent()
rec_agent = register_recommendation_agent()

# Subscribe to generated recommendation events
recommendations = []
EventBus.get_global().subscribe("recommendation.generated", lambda e: recommendations.append(e))

# Trigger end-to-end reactive agent chain
telemetry_agent = TelemetryAgent()
telemetry_agent.execute({"device_id": "Branch3-Uplink"})

print(f"Recommendations generated: {len(recommendations)}")
if recommendations:
    rec = recommendations[0].payload
    print(f"Recommendation ID: {rec['recommendation_id']}")
    print(f"Summary: {rec['summary']}")
    print(f"Actions count: {len(rec['execution_plan']['actions'])}")
```
