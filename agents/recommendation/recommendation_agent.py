"""
Production Recommendation Agent Implementation.

Subclasses BaseAgent to generate structured remediation plans, subscribe to 'incident.created'
and 'incident.updated' events, publish 'recommendation.generated' events, and update ExecutionContext.
"""

from typing import Any, Dict, List, Optional, Union
import uuid

from agents.base.base_agent import BaseAgent
from agents.core.container import ServiceContainer
from agents.core.logger import get_agent_logger, log_execution_event
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.incident.incident_models import IncidentRecord
from agents.recommendation.recommendation_models import RecommendationRecord
from agents.recommendation.recommendation_service import RecommendationService
from agents.registry.registry import AgentRegistry
from agents.schemas.schemas import AgentMetadata, CapabilityFlags, ExecutionContext

logger = get_agent_logger("RecommendationAgent")


class RecommendationAgent(BaseAgent):
    """
    Production Recommendation Agent for NOC Copilot.

    Subscribes to incident events, applies remediation templates and rules to build structured CLI,
    verification, and rollback plans, and emits 'recommendation.generated' events.
    """

    def __init__(
        self,
        service: Optional[RecommendationService] = None,
        metadata: Optional[AgentMetadata] = None,
        container: Optional[ServiceContainer] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        """
        Initialize RecommendationAgent.

        Args:
            service: RecommendationService instance.
            metadata: AgentMetadata instance.
            container: ServiceContainer instance.
            event_bus: EventBus instance.
        """
        agent_metadata = metadata or AgentMetadata(
            name="RecommendationAgent",
            version="1.0.0",
            description="Transforms network incidents into structured, automated remediation and rollback plans.",
            author="NOC Copilot Core Team",
            dependencies=["IncidentAgent"],
            tags=["recommendation", "remediation", "action"],
            capabilities=CapabilityFlags(supports_cpu=True, supports_batch=True),
        )

        super().__init__(metadata=agent_metadata, container=container, event_bus=event_bus)
        self._service = service or RecommendationService()
        self._incident_sub_ids: List[str] = []
        self._setup_event_subscriptions()

    @property
    def service(self) -> RecommendationService:
        """Recommendation service instance."""
        return self._service

    def _setup_event_subscriptions(self) -> None:
        """Subscribe to 'incident.created' and 'incident.updated' events on the EventBus."""
        if self.event_bus:
            sub1 = self.event_bus.subscribe(
                topic="incident.created",
                callback=self._handle_incident_event,
            )
            sub2 = self.event_bus.subscribe(
                topic="incident.updated",
                callback=self._handle_incident_event,
            )
            self._incident_sub_ids.extend([sub1, sub2])
            logger.info("RecommendationAgent subscribed to incident lifecycle events.")

    def _handle_incident_event(self, event: Event) -> None:
        """
        Event subscriber callback for incident events.

        Args:
            event: Published Incident Event object.
        """
        try:
            payload = event.payload or {}
            log_execution_event(
                logger,
                self.name,
                "EVENT_RECEIVED",
                f"RecommendationAgent received incident event '{event.event_type}' for incident '{payload.get('incident_id')}'.",
            )
            self.execute(payload)
        except Exception as e:
            logger.error(f"Error handling incident event in RecommendationAgent: {e}", exc_info=True)

    def validate_input(self, input_data: Any) -> List[Dict[str, Any]]:
        """
        Validate execution input payload.

        Supports IncidentRecord model, event payload dict, or list of incident payloads.
        """
        if input_data is None:
            return []

        if isinstance(input_data, IncidentRecord):
            return [input_data.model_dump(mode="json")]

        if isinstance(input_data, Event):
            payload = input_data.payload or {}
            return [payload]

        if isinstance(input_data, list):
            validated: List[Dict[str, Any]] = []
            for item in input_data:
                if isinstance(item, IncidentRecord):
                    validated.append(item.model_dump(mode="json"))
                elif isinstance(item, dict):
                    validated.append(item)
            return validated

        if isinstance(input_data, dict):
            return [input_data]

        return []

    def _execute_internal(
        self, input_data: List[Dict[str, Any]], context: Optional[ExecutionContext] = None
    ) -> List[RecommendationRecord]:
        """
        Execute recommendation processing logic, emit recommendation.generated events, and update context.

        Args:
            input_data: Validated list of incident payload dictionaries.
            context: Shared ExecutionContext.

        Returns:
            List of generated RecommendationRecord objects.
        """
        recommendations: List[RecommendationRecord] = []
        exec_id = context.context_id if context else str(uuid.uuid4())

        for inc_payload in input_data:
            try:
                rec = self._service.generate_recommendation_for_incident(inc_payload)
                recommendations.append(rec)

                if self.event_bus:
                    evt = Event(
                        event_type="recommendation.generated",
                        source=self.name,
                        payload=rec.model_dump(mode="json"),
                        metadata={
                            "execution_id": exec_id,
                            "recommendation_id": rec.recommendation_id,
                            "incident_id": rec.incident_id,
                            "device_id": rec.device_id,
                            "interface": rec.interface,
                            "priority": rec.priority.value,
                            "timestamp": str(rec.created_at),
                        },
                    )
                    self.event_bus.publish(evt)

            except Exception as e:
                logger.error(f"Error generating recommendation in RecommendationAgent: {e}", exc_info=True)

        log_execution_event(
            logger,
            self.name,
            "RECOMMENDATIONS_GENERATED",
            f"RecommendationAgent generated {len(recommendations)} recommendation plan(s).",
        )

        # Update execution context
        if context:
            context.results[self.name] = [r.model_dump(mode="json") for r in recommendations]
            context.shared_state["latest_recommendations"] = {
                r.recommendation_id: r.model_dump(mode="json") for r in recommendations
            }

        return recommendations

    def shutdown(self) -> None:
        """Unsubscribe event handlers and shutdown RecommendationAgent."""
        if self.event_bus and self._incident_sub_ids:
            for sub_id in self._incident_sub_ids:
                self.event_bus.unsubscribe(sub_id)
            self._incident_sub_ids.clear()
        super().shutdown()


def register_recommendation_agent(registry: Optional[AgentRegistry] = None) -> RecommendationAgent:
    """
    Convenience function to instantiate and register RecommendationAgent with AgentRegistry.

    Args:
        registry: Target AgentRegistry (defaults to global instance).

    Returns:
        Registered RecommendationAgent instance.
    """
    target_registry = registry or AgentRegistry.get_global()
    agent = RecommendationAgent()
    target_registry.register(agent, allow_override=True)
    return agent
