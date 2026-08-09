"""
Enterprise Live Data Integration Layer (Atomic Agent Ready).

Provides pluggable multi-source telemetry collection (SNMP, Syslog, REST, Windows,
Linux, Prometheus, and Simulation), runtime source selection, thread-safe scheduling,
automatic failover, health monitoring, and EventBus integration.
"""

from agents.collectors.collector_base import CollectorBase
from agents.collectors.collector_events import (
    EVENT_COLLECTOR_ERROR,
    EVENT_COLLECTOR_HEALTH_CHANGED,
    EVENT_COLLECTOR_REGISTERED,
    EVENT_COLLECTOR_UNREGISTERED,
    EVENT_SOURCE_MODE_CHANGED,
    EVENT_TELEMETRY_COLLECTED,
    create_collector_error_event,
    create_collector_health_event,
    create_source_mode_changed_event,
    create_telemetry_collected_event,
)
from agents.collectors.collector_health import CollectorHealthMonitor
from agents.collectors.collector_manager import CollectorManager
from agents.collectors.collector_models import (
    CollectorCapabilities,
    CollectorHealth,
    CollectorMetadata,
    CollectorSchedule,
    CollectorState,
    SourceMode,
    TelemetryPacket,
)
from agents.collectors.collector_registry import CollectorRegistry
from agents.collectors.collector_scheduler import CollectorScheduler
from agents.collectors.linux_collector import LinuxCollector
from agents.collectors.prometheus_collector import PrometheusCollector
from agents.collectors.rest_collector import RESTCollector
from agents.collectors.simulation_collector import SimulationCollector
from agents.collectors.snmp_collector import SNMPCollector
from agents.collectors.syslog_collector import SyslogCollector
from agents.collectors.windows_collector import WindowsCollector

__all__ = [
    # Base and Models
    "CollectorBase",
    "CollectorState",
    "SourceMode",
    "CollectorSchedule",
    "CollectorCapabilities",
    "CollectorMetadata",
    "CollectorHealth",
    "TelemetryPacket",
    # Core Components
    "CollectorRegistry",
    "CollectorScheduler",
    "CollectorHealthMonitor",
    "CollectorManager",
    # Collectors
    "SimulationCollector",
    "SNMPCollector",
    "SyslogCollector",
    "RESTCollector",
    "WindowsCollector",
    "LinuxCollector",
    "PrometheusCollector",
    # Events
    "EVENT_TELEMETRY_COLLECTED",
    "EVENT_COLLECTOR_HEALTH_CHANGED",
    "EVENT_COLLECTOR_REGISTERED",
    "EVENT_COLLECTOR_UNREGISTERED",
    "EVENT_COLLECTOR_ERROR",
    "EVENT_SOURCE_MODE_CHANGED",
    "create_telemetry_collected_event",
    "create_collector_health_event",
    "create_collector_error_event",
    "create_source_mode_changed_event",
]
