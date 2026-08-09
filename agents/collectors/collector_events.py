"""
Event definitions and factory functions for the Telemetry Collector Integration Layer.

Emits events onto the framework EventBus to notify subscribers when telemetry packets
are collected, collector health changes, or source failovers occur.
"""

from typing import Any, Dict, List, Optional
from agents.events.event import Event
from agents.schemas.schemas import TelemetryPacket
from agents.collectors.collector_models import CollectorHealth, SourceMode

# Standard Event Topics
EVENT_TELEMETRY_COLLECTED = "telemetry.collected"
EVENT_COLLECTOR_HEALTH_CHANGED = "collector.health_changed"
EVENT_COLLECTOR_REGISTERED = "collector.registered"
EVENT_COLLECTOR_UNREGISTERED = "collector.unregistered"
EVENT_COLLECTOR_ERROR = "collector.error"
EVENT_SOURCE_MODE_CHANGED = "source_mode.changed"


def create_telemetry_collected_event(
    collector_name: str,
    collector_id: str,
    source_type: str,
    packets: List[TelemetryPacket],
    execution_context_id: Optional[str] = None,
) -> Event:
    """
    Construct a 'telemetry.collected' Event for published telemetry packets.

    Args:
        collector_name: Name of the collector.
        collector_id: Instance ID of the collector.
        source_type: Telemetry source type (e.g. 'snmp', 'simulation').
        packets: List of collected TelemetryPacket instances.
        execution_context_id: Optional parent context ID for tracing.

    Returns:
        Structured Event object ready for EventBus publication.
    """
    packet_dumps = [p.model_dump(mode="json") for p in packets]
    return Event(
        event_type=EVENT_TELEMETRY_COLLECTED,
        source=collector_name,
        payload={
            "collector_name": collector_name,
            "collector_id": collector_id,
            "source_type": source_type,
            "count": len(packets),
            "packets": packet_dumps,
        },
        metadata={
            "execution_context_id": execution_context_id or "",
            "source_type": source_type,
            "packet_count": str(len(packets)),
        },
    )


def create_collector_health_event(health: CollectorHealth) -> Event:
    """
    Construct a 'collector.health_changed' Event.

    Args:
        health: CollectorHealth snapshot.

    Returns:
        Structured Event object.
    """
    return Event(
        event_type=EVENT_COLLECTOR_HEALTH_CHANGED,
        source=health.collector_name,
        payload=health.model_dump(mode="json"),
        metadata={
            "collector_id": health.collector_id,
            "is_healthy": str(health.is_healthy),
            "state": health.state.value,
        },
    )


def create_collector_error_event(
    collector_name: str,
    collector_id: str,
    error_message: str,
    details: Optional[Dict[str, Any]] = None,
) -> Event:
    """
    Construct a 'collector.error' Event.

    Args:
        collector_name: Collector name.
        collector_id: Collector ID.
        error_message: Error string description.
        details: Optional contextual error dictionary.

    Returns:
        Structured Event object.
    """
    return Event(
        event_type=EVENT_COLLECTOR_ERROR,
        source=collector_name,
        payload={
            "collector_name": collector_name,
            "collector_id": collector_id,
            "error": error_message,
            "details": details or {},
        },
        metadata={"collector_id": collector_id},
    )


def create_source_mode_changed_event(
    old_mode: SourceMode,
    new_mode: SourceMode,
    reason: str = "",
) -> Event:
    """
    Construct a 'source_mode.changed' Event.

    Args:
        old_mode: Previous SourceMode.
        new_mode: New SourceMode.
        reason: Description of trigger (e.g. automatic failover).

    Returns:
        Structured Event object.
    """
    return Event(
        event_type=EVENT_SOURCE_MODE_CHANGED,
        source="CollectorManager",
        payload={
            "old_mode": old_mode.value if isinstance(old_mode, SourceMode) else str(old_mode),
            "new_mode": new_mode.value if isinstance(new_mode, SourceMode) else str(new_mode),
            "reason": reason,
        },
        metadata={"reason": reason},
    )
