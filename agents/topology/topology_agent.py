"""
Production Topology Agent Implementation.

Subclasses BaseAgent to subscribe to 'incident.created' and 'incident.updated'
events, perform network topology analysis, store TopologyAnalysis inside
ExecutionContext.shared_state, and publish 'topology.analysis.completed' events
onto the EventBus.

The TopologyAgent is positioned in the reactive event chain between
RecommendationAgent and KnowledgeAgent:

    TelemetryAgent → PredictionAgent → IncidentAgent → RecommendationAgent
    → TopologyAgent → KnowledgeAgent → OllamaProvider → Qwen
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import uuid

from agents.base.base_agent import BaseAgent
from agents.core.container import ServiceContainer
from agents.core.logger import get_agent_logger, log_execution_event
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.registry.registry import AgentRegistry
from agents.schemas.schemas import AgentMetadata, CapabilityFlags, ExecutionContext
from agents.topology.topology_models import TopologyAnalysis
from agents.topology.topology_service import TopologyService

logger = get_agent_logger("TopologyAgent")


class TopologyAgent(BaseAgent):
    """
    Production Topology Agent for NOC Copilot.

    Subscribes to 'incident.created' and 'incident.updated' events, performs
    full topology graph analysis via TopologyService, stores the resulting
    TopologyAnalysis in ExecutionContext.shared_state['latest_topology'], and
    publishes a 'topology.analysis.completed' event onto the EventBus.

    The agent is designed to be zero-configuration — defaults are production-
    ready without requiring any constructor arguments.
    """

    def __init__(
        self,
        service: Optional[TopologyService] = None,
        metadata: Optional[AgentMetadata] = None,
        container: Optional[ServiceContainer] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        """
        Initialise TopologyAgent.

        Args:
            service: TopologyService instance.  Defaults to a fresh instance.
            metadata: AgentMetadata instance.  Defaults to production metadata.
            container: ServiceContainer instance for DI.
            event_bus: EventBus instance.  Defaults to global singleton.
        """
        agent_metadata = metadata or AgentMetadata(
            name="TopologyAgent",
            version="1.0.0",
            description=(
                "Analyses network topology graph on incident events, computes "
                "blast radius, upstream/downstream dependencies, service impact, "
                "and SPOF exposure."
            ),
            author="NOC Copilot Core Team",
            dependencies=["IncidentAgent", "RecommendationAgent"],
            tags=["topology", "dependency-analysis", "graph", "network"],
            capabilities=CapabilityFlags(supports_cpu=True, supports_batch=True),
        )

        super().__init__(
            metadata=agent_metadata,
            container=container,
            event_bus=event_bus,
        )

        self._service = service or TopologyService()
        self._incident_sub_ids: List[str] = []
        self._setup_event_subscriptions()

    @property
    def service(self) -> TopologyService:
        """TopologyService instance used by this agent."""
        return self._service

    # ------------------------------------------------------------------
    # Event subscription
    # ------------------------------------------------------------------

    def _setup_event_subscriptions(self) -> None:
        """Subscribe to incident.created and incident.updated events."""
        if self.event_bus:
            for topic in ("incident.created", "incident.updated"):
                sub_id = self.event_bus.subscribe(
                    topic=topic,
                    callback=self._handle_incident_event,
                )
                self._incident_sub_ids.append(sub_id)
            logger.info(
                "TopologyAgent subscribed to 'incident.created' and"
                " 'incident.updated' events."
            )

    def _handle_incident_event(self, event: Event) -> None:
        """
        Callback invoked when an incident.created or incident.updated event fires.

        Extracts the incident payload from the event, triggers topology analysis,
        and publishes the result.  Errors are caught and logged so that the
        event chain is never interrupted by a topology failure.

        Args:
            event: The incoming Event object from the EventBus.
        """
        try:
            incident_payload: Dict[str, Any] = event.payload
            logger.info(
                "TopologyAgent received '%s' event (incident_id=%s).",
                event.event_type,
                incident_payload.get("incident_id", "unknown"),
            )

            analysis = self._service.analyze_incident(incident_payload)
            self._publish_analysis(analysis, event)

        except Exception as exc:
            logger.error(
                "TopologyAgent failed to handle '%s' event: %s",
                event.event_type,
                exc,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # BaseAgent abstract method implementation
    # ------------------------------------------------------------------

    def validate_input(self, input_data: Any) -> List[Dict[str, Any]]:
        """
        Validate and normalise input data for direct agent execution.

        Accepts:
            - A single incident dict.
            - A list of incident dicts.

        Args:
            input_data: Raw input to validate.

        Returns:
            List of incident payload dictionaries.

        Raises:
            TypeError: If input_data is not a dict or list.
        """
        if isinstance(input_data, dict):
            return [input_data]
        if isinstance(input_data, list):
            validated: List[Dict[str, Any]] = []
            for item in input_data:
                if isinstance(item, dict):
                    validated.append(item)
                elif isinstance(item, str):
                    # Support lists of device ID strings as shorthand
                    validated.append({"affected_entities": [item]})
                else:
                    raise TypeError(
                        f"TopologyAgent expects incident dicts; got {type(item).__name__}"
                    )
            return validated
        raise TypeError(
            f"TopologyAgent.validate_input expects dict or list, got"
            f" {type(input_data).__name__}"
        )

    def _execute_internal(
        self,
        input_data: List[Dict[str, Any]],
        context: Optional[ExecutionContext] = None,
    ) -> List[TopologyAnalysis]:
        """
        Execute topology analysis for each incident payload in *input_data*.

        For every incident:
            1. Analyse via TopologyService.
            2. Store result in ExecutionContext.shared_state.
            3. Publish 'topology.analysis.completed' event.

        Args:
            input_data: List of validated incident payload dicts.
            context: Optional shared ExecutionContext.

        Returns:
            List of TopologyAnalysis objects produced.
        """
        analyses: List[TopologyAnalysis] = []
        exec_id = context.context_id if context else str(uuid.uuid4())

        for incident_payload in input_data:
            try:
                analysis = self._service.analyze_incident(incident_payload)
                analyses.append(analysis)
                self._publish_analysis(analysis, None, exec_id=exec_id)
            except Exception as exc:
                logger.error(
                    "TopologyAgent failed to analyse incident payload: %s",
                    exc,
                    exc_info=True,
                )

        log_execution_event(
            logger,
            self.name,
            "TOPOLOGY_ANALYSES_COMPLETED",
            f"TopologyAgent produced {len(analyses)} topology analysis result(s).",
        )

        # Persist results in execution context
        if context:
            context.results[self.name] = [
                a.model_dump(mode="json") for a in analyses
            ]
            context.shared_state["latest_topology"] = {
                a.analysis_id: a.model_dump(mode="json") for a in analyses
            }

        return analyses

    # ------------------------------------------------------------------
    # Event publication
    # ------------------------------------------------------------------

    def _publish_analysis(
        self,
        analysis: TopologyAnalysis,
        trigger_event: Optional[Event],
        exec_id: str = "",
    ) -> None:
        """
        Publish a 'topology.analysis.completed' event carrying the full analysis.

        Args:
            analysis: The completed TopologyAnalysis.
            trigger_event: The original incident event (for trace metadata).
            exec_id: Optional execution context ID for trace correlation.
        """
        if not self.event_bus:
            return

        metadata: Dict[str, Any] = {
            "analysis_id": analysis.analysis_id,
            "device_id": analysis.device_id,
            "interface": analysis.interface,
            "severity": analysis.overall_severity.value,
            "timestamp": analysis.timestamp.isoformat(),
        }
        if exec_id:
            metadata["execution_id"] = exec_id
        if trigger_event:
            metadata["trigger_event_id"] = trigger_event.event_id
            metadata["trigger_event_type"] = trigger_event.event_type

        evt = Event(
            event_type="topology.analysis.completed",
            source=self.name,
            payload=analysis.model_dump(mode="json"),
            metadata=metadata,
        )
        self.event_bus.publish(evt)
        logger.debug(
            "TopologyAgent published 'topology.analysis.completed' for device '%s'.",
            analysis.device_id,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Unsubscribe all event handlers and terminate the agent."""
        if self.event_bus:
            for sub_id in self._incident_sub_ids:
                self.event_bus.unsubscribe(sub_id)
            self._incident_sub_ids.clear()
        super().shutdown()


def register_topology_agent(
    registry: Optional[AgentRegistry] = None,
) -> TopologyAgent:
    """
    Convenience function to instantiate and register TopologyAgent.

    Args:
        registry: Target AgentRegistry.  Defaults to the global instance.

    Returns:
        Registered TopologyAgent instance.
    """
    target_registry = registry or AgentRegistry.get_global()
    agent = TopologyAgent()
    target_registry.register(agent, allow_override=True)
    return agent
