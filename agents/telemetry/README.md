# NOC Copilot — Production Telemetry Agent

## Overview

The `TelemetryAgent` is the primary production ingestion agent in the NOC Copilot Atomic Agent architecture. It integrates with the live SQLite telemetry database and multi-device simulation daemon while maintaining total backward compatibility with existing services (`engine/`, `copilot/`, `faultsim/`, `ui/`).

---

## Architecture Diagram

```
+-----------------------------------------------------------------------------------+
|                            SQLITE TELEMETRY DATABASE                              |
|                          (metrics table / telemetry.db)                           |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                               REPOSITORY LAYER                                    |
|       TelemetryRepository (Thread-Safe Persistence / SQLite Prepared Queries)     |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                VALIDATION LAYER                                   |
|       TelemetryValidator (Type checking, Bounds, Null checks, Schema validation)  |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                 SERVICE LAYER                                     |
|    TelemetryService (Maps DEVICE_REGISTRY, constructs TelemetryPacket objects)     |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                  AGENT LAYER                                      |
|    TelemetryAgent (BaseAgent implementation, updates ExecutionContext & metrics)  |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                EVENT BUS SYSTEM                                   |
|         EventBus -> Publishes 'telemetry.updated' (Consumed by downstream agents) |
+-----------------------------------------------------------------------------------+
```

---

## Component Layers

### 1. TelemetryRepository (`agents.telemetry.TelemetryRepository`)
- Pure persistence layer.
- Thread-safe SQLite access using connection-per-query context management.
- Standard queries:
  - `get_latest_telemetry(interface)`
  - `get_all_latest_telemetry()`
  - `get_historical_telemetry(interface, limit)`
  - `get_telemetry_by_timerange(interface, start_time, end_time, limit, offset)`

### 2. TelemetryValidator (`agents.telemetry.TelemetryValidator`)
- Enforces strict data types, numeric range constraints (utilization 0–100%, non-negative latency, jitter, drops, flaps), and required fields.
- Raises `ValidationError` upon invalid raw database records or corrupted `TelemetryPacket` instances.

### 3. TelemetryService (`agents.telemetry.TelemetryService`)
- Business logic layer.
- Resolves device IDs and interface names against `DEVICE_REGISTRY`.
- Transforms validated dictionary rows into strongly typed `TelemetryPacket` Pydantic models.

### 4. TelemetryAgent (`agents.telemetry.TelemetryAgent`)
- Subclasses `BaseAgent`.
- Automatically registers with `AgentRegistry`.
- Accepts query parameters (`mode`, `device_id`, `interface`, `limit`, `start_time`, `end_time`).
- Publishes `telemetry.updated` events onto `EventBus`.
- Populates workflow `ExecutionContext.results` and `ExecutionContext.shared_state`.

---

## Event Publication Protocol

- **Topic**: `telemetry.updated`
- **Source**: `TelemetryAgent`
- **Payload**: Serialized `TelemetryPacket` JSON object.
- **Metadata**:
  - `execution_id`: Context run identifier.
  - `device_id`: Monitored device ID (e.g. `core-01`, `branch3-uplink`).
  - `interface`: Interface name key.
  - `timestamp`: UTC ISO timestamp string.

---

## Usage Example

```python
from agents.registry import AgentRegistry
from agents.telemetry import TelemetryAgent, register_telemetry_agent
from agents.events import EventBus

# Register agent
agent = register_telemetry_agent()

# Subscribe to event bus updates
events = []
EventBus.get_global().subscribe("telemetry.updated", lambda e: events.append(e))

# Execute agent
packets = agent.execute({"device_id": "Branch3-Uplink", "mode": "latest"})

print(f"Ingested {len(packets)} telemetry packet(s)")
print(f"Received {len(events)} event(s)")
```
