"""
Digital Twin Service Module for NOC-Copilot v1.5.

Orchestration service providing a unified domain interface to the Network Digital Twin,
integrating with TopologyService, PathDiscoveryEngine, and TelemetryAgent for simulation,
state tracking, and What-If analysis.
"""

from typing import Any, Dict, List, Optional
import threading

from agents.core.logger import get_agent_logger
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.topology.topology_service import TopologyService
from agents.twin.digital_twin import NetworkDigitalTwin
from agents.twin.twin_models import (
    AffectedComponentsSummary,
    DigitalTwinSnapshot,
    TwinSimulationResult,
)

logger = get_agent_logger("DigitalTwinService")


class DigitalTwinService:
    """
    Domain service facade for the Network Digital Twin subsystem.
    """

    def __init__(
        self,
        digital_twin: Optional[NetworkDigitalTwin] = None,
        topology_service: Optional[TopologyService] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self._topo_service = topology_service or TopologyService()
        self._twin = digital_twin or NetworkDigitalTwin(repository=self._topo_service.repository)
        self._event_bus = event_bus
        self._lock = threading.RLock()

    @property
    def twin(self) -> NetworkDigitalTwin:
        """Accessor for the underlying NetworkDigitalTwin engine."""
        return self._twin

    def get_snapshot(self) -> DigitalTwinSnapshot:
        """Capture and return current immutable Digital Twin snapshot."""
        with self._lock:
            snap = self._twin.snapshot()
            self._publish_event("twin.snapshot.captured", {"snapshot_id": snap.snapshot_id, "devices_count": len(snap.devices)})
            return snap

    def simulate_provider_failure(self, provider_name: str) -> TwinSimulationResult:
        """Simulate failure of a WAN provider."""
        with self._lock:
            res = self._twin.simulate_provider_failure(provider_name)
            self._publish_event("twin.simulation.completed", {"scenario": "PROVIDER_FAILURE", "target": provider_name, "severity": res.impact_severity})
            return res

    def simulate_link_failure(self, source_node: str, target_node: str) -> TwinSimulationResult:
        """Simulate failure of a network link."""
        with self._lock:
            res = self._twin.simulate_link_failure(source_node, target_node)
            self._publish_event("twin.simulation.completed", {"scenario": "LINK_FAILURE", "target": f"{source_node}<->{target_node}"})
            return res

    def simulate_failover(
        self,
        source_provider: str,
        target_provider: str,
        target_device: str = "branch3-uplink",
    ) -> TwinSimulationResult:
        """Simulate WAN route failover transition."""
        with self._lock:
            res = self._twin.simulate_failover(source_provider, target_provider, target_device)
            self._publish_event("twin.simulation.completed", {"scenario": "FAILOVER", "source": source_provider, "target": target_provider})
            return res

    def analyze_affected_components(self, failed_entities: List[str]) -> AffectedComponentsSummary:
        """Analyze affected components and blast radius for failing entities."""
        with self._lock:
            return self._twin.get_affected_components(failed_entities)

    def _publish_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Publish lifecycle event to EventBus if available."""
        if self._event_bus:
            try:
                evt = Event(
                    event_type=event_type,
                    source="DigitalTwinService",
                    payload=payload,
                )
                self._event_bus.publish(evt)
            except Exception as e:
                logger.warning(f"EventBus publish error for '{event_type}': {e}")
