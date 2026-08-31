"""
GNN Service Facade Module for NOC-Copilot v1.5.

Orchestrates GNN graph building and advisory blast-radius estimation.
Integrates with PathDecisionService, DigitalTwinService, and EventBus.
"""

from typing import Any, Dict, List, Optional
import threading

from agents.core.logger import get_agent_logger
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.gnn.blast_radius_gnn import GNNBlastRadiusEngine
from agents.gnn.gnn_models import (
    GNNBlastRadiusRequest,
    GNNBlastRadiusResult,
    GNNGraphData,
)
from agents.gnn.graph_builder import TopologyGraphBuilder
from agents.topology.topology_service import TopologyService

logger = get_agent_logger("GNNService")


class GNNService:
    """
    Service facade for GNN Blast-Radius and failure propagation estimation.
    """

    def __init__(
        self,
        gnn_engine: Optional[GNNBlastRadiusEngine] = None,
        topology_service: Optional[TopologyService] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self._topo_service = topology_service or TopologyService()
        self._builder = TopologyGraphBuilder(repository=self._topo_service.repository)
        self._engine = gnn_engine or GNNBlastRadiusEngine(graph_builder=self._builder)
        self._event_bus = event_bus
        self._lock = threading.RLock()

    @property
    def engine(self) -> GNNBlastRadiusEngine:
        """Accessor for the underlying GNNBlastRadiusEngine."""
        return self._engine

    def evaluate_blast_radius(
        self,
        target_entity: str,
        scenario: str = "PROVIDER_FAILURE",
        initial_perturbation: float = 0.90,
    ) -> GNNBlastRadiusResult:
        """
        Evaluate advisory blast radius for a target entity or scenario.
        """
        with self._lock:
            req = GNNBlastRadiusRequest(
                target_entity=target_entity,
                scenario=scenario,
                initial_perturbation=initial_perturbation,
            )
            result = self._engine.predict_blast_radius(req)

            self._publish_event(
                "gnn.blast_radius.evaluated",
                {
                    "target_entity": target_entity,
                    "blast_radius_pct": result.predicted_blast_radius_pct,
                    "high_risk_nodes": result.high_risk_nodes,
                    "provenance": result.provenance.value,
                },
            )
            return result

    def get_graph_data(self) -> GNNGraphData:
        """Retrieve current structured graph feature data."""
        with self._lock:
            return self._builder.build_graph_data()

    def _publish_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Publish event to EventBus if available."""
        if self._event_bus:
            try:
                evt = Event(
                    event_type=event_type,
                    source="GNNService",
                    payload=payload,
                )
                self._event_bus.publish(evt)
            except Exception as e:
                logger.warning(f"EventBus publish error in GNNService for '{event_type}': {e}")
