# 🌐 Enterprise Live Data Integration Layer (Atomic Agent Ready)

> **Production Enterprise Telemetry Ingestion Layer for NOC Copilot — Ingesting Live Infrastructure Telemetry with Zero Regressions and Seamless Fault Simulator Compatibility.**

---

## 🏗️ Architecture Overview

The Enterprise Integration Layer transforms NOC Copilot from a simulator-driven platform into a production enterprise NOC platform capable of ingesting telemetry from live enterprise infrastructure (SNMP switches, Syslog feeds, REST management APIs, Windows servers, Linux hosts, and Prometheus exporters) while maintaining 100% backward compatibility with the existing Fault Simulator and Atomic Agent framework.

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 Enterprise Telemetry Sources                           │
│  ┌──────────────┐  ┌─────────────┐  ┌────────────┐  ┌─────────────┐  ┌──────────────┐  │
│  │ SNMP Devices │  │ Syslog Feeds│  │ REST APIs  │  │ Win/Linux   │  │ Prometheus   │  │
│  └──────┬───────┘  └──────┬──────┘  └─────┬──────┘  └──────┬──────┘  └──────┬───────┘  │
└─────────┼─────────────────┼───────────────┼────────────────┼────────────────┼──────────┘
          │                 │               │                │                │
          ▼                 ▼               ▼                ▼                ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                           Pluggable Telemetry Collectors                               │
│  ┌──────────────┐  ┌─────────────┐  ┌────────────┐  ┌─────────────┐  ┌──────────────┐  │
│  │SNMPCollector │  │SyslogCollect│  │RESTCollect │  │Win/LinuxColl│  │PrometheusColl│  │
│  └──────┬───────┘  └──────┬──────┘  └─────┬──────┘  └──────┬──────┘  └──────┬───────┘  │
│         │                 │               │                │                │          │
│         └─────────────────┴───────┬───────┴────────────────┴────────────────┘          │
│                                   │                                                    │
│                                   ▼                                                    │
│                        ┌──────────────────────┐                                        │
│                        │ SimulationCollector  │  (Fallback / Synthetic)                │
│                        └──────────┬───────────┘                                        │
└───────────────────────────────────┼────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              CollectorManager & Scheduler                              │
│         - Thread-Safe Scheduler & Parallel Pool                                        │
│         - Source Mode: Live | Simulation | Hybrid | Failover                           │
│         - Automatic Health Monitoring & Retries                                        │
└───────────────────────────────────┬────────────────────────────────────────────────────┘
                                    │
                                    ▼  Publishes 'telemetry.collected'
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                EventBus & Agent Flow                                   │
│  telemetry.collected ──► TelemetryAgent ──► PredictionAgent ──► IncidentAgent          │
│  ──► RecommendationAgent ──► TopologyAgent ──► CAG ──► RAG ──► KnowledgeAgent ──► Ollama│
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## ⚡ Core Features

- **Pluggable Collector Interface**: Standardized `CollectorBase` contract (`initialize()`, `shutdown()`, `collect()`, `health()`, `metadata()`, `capabilities()`, `schedule()`).
- **Production Collector implementations**:
  - `SimulationCollector`: Wraps existing TelemetryService / synthetic generator.
  - `SNMPCollector`: Polls MIB-II interface OIDs and UDP targets.
  - `SyslogCollector`: Parses UDP RFC 3164/5424 logs into telemetry metric counters.
  - `RESTCollector`: Polls controller & gateway HTTP REST APIs.
  - `WindowsCollector`: Windows host performance telemetry (CPU, Memory, Net drops).
  - `LinuxCollector`: Linux kernel `/proc/net/dev`, CPU, and network interface metrics.
  - `PrometheusCollector`: Scrapes Prometheus exposition format endpoints (`/metrics`).
- **Runtime Source Selection**:
  - `SIMULATION`: Pure simulator mode.
  - `LIVE`: Enterprise production collectors only.
  - `HYBRID`: Concurrent live & simulated telemetry.
  - `FAILOVER`: Live primary; automatically fails over to simulation if live feeds fail.
- **Thread-Safe Scheduler**: Priority execution, exponential backoff retries, configurable timeouts.
- **Health Monitoring & Dashboard Metrics**: Latency metrics, success rates, availability %, consecutive failure tracking.

---

## 🛠️ Collector Development Guide

To create a custom collector for your enterprise hardware:

```python
from typing import List
from datetime import datetime, timezone
from agents.collectors import CollectorBase, CollectorMetadata, CollectorSchedule, TelemetryPacket

class CustomEnterpriseCollector(CollectorBase):
    def __init__(self):
        meta = CollectorMetadata(
            name="CustomEnterpriseCollector",
            description="Custom hardware collector",
            source_type="custom_hw",
            supported_metrics=["utilization", "latency", "drops"]
        )
        sched = CollectorSchedule(interval_seconds=5.0, priority=15)
        super().__init__(metadata=meta, schedule=sched)

    def initialize(self) -> bool:
        # Establish connection / resources
        return True

    def shutdown(self) -> bool:
        # Clean up sockets / connections
        return True

    def collect(self) -> List[TelemetryPacket]:
        now = datetime.now(timezone.utc)
        return [
            TelemetryPacket(
                device_id="custom-dev-01",
                interface="TenGigabitEthernet0/1",
                metrics={"utilization": 45.2, "latency": 8.5, "drops": 0.0},
                timestamp=now,
                metadata={"source": self.name}
            )
        ]
```

### Runtime Registration

```python
from agents.collectors import CollectorManager, CollectorRegistry

manager = CollectorManager.get_global()
manager.initialize()

# Register custom collector
my_collector = CustomEnterpriseCollector()
CollectorRegistry.get_global().register(my_collector)

# Trigger collection pass
packets = manager.collect_once()
```

---

## 🧪 Verification & Event Flow

All collectors publish strongly-typed `TelemetryPacket` instances via `telemetry.collected` onto the `EventBus`. Downstream agents (`TelemetryAgent`, `PredictionAgent`, `IncidentAgent`, etc.) receive packets without requiring code modifications.
