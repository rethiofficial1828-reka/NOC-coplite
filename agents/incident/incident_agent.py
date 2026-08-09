"""
Production Incident Agent Implementation.

Subclasses BaseAgent to manage network incident lifecycle, subscribe to 'prediction.generated'
events, perform deduplication, enforce state transitions, and publish incident events.
"""

from typing import Any, Dict, List, Optional, Union
import uuid

from agents.base.base_agent import BaseAgent
from agents.core.container import ServiceContainer
from agents.core.logger import get_agent_logger, log_execution_event
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.incident.incident_models import IncidentRecord, IncidentStatus
from agents.incident.incident_service import IncidentService
from agents.registry.registry import AgentRegistry
from agents.schemas.schemas import AgentMetadata, CapabilityFlags, ExecutionContext, PredictionResult

logger = get_agent_logger("IncidentAgent")


class IncidentAgent(BaseAgent):
    """
    Production Incident Agent for NOC Copilot.

    Subscribes to 'prediction.generated' events, evaluates risk predictions against business rules,
    performs deduplication, executes state transitions, emits incident events, and maintains audit timelines.
    """

    def __init__(
        self,
        service: Optional[IncidentService] = None,
        metadata: Optional[AgentMetadata] = None,
        container: Optional[ServiceContainer] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        """
        Initialize IncidentAgent.

        Args:
            service: IncidentService instance.
            metadata: AgentMetadata instance.
            container: ServiceContainer instance.
            event_bus: EventBus instance.
        """
        agent_metadata = metadata or AgentMetadata(
            name="IncidentAgent",
            version="1.0.0",
            description="Manages lifecycle, deduplication, state machine transitions, and event emission for NOC incidents.",
            author="NOC Copilot Core Team",
            dependencies=["PredictionAgent"],
            tags=["incident", "management", "workflow"],
            capabilities=CapabilityFlags(supports_cpu=True, supports_batch=True),
        )

        super().__init__(metadata=agent_metadata, container=container, event_bus=event_bus)
        self._service = service or IncidentService()
        self._prediction_subscription_id: Optional[str] = None
        self._setup_event_subscription()

    @property
    def service(self) -> IncidentService:
        """Incident service instance."""
        return self._service

    def _setup_event_subscription(self) -> None:
        """Subscribe to 'prediction.generated' events on the EventBus."""
        if self.event_bus:
            self._prediction_subscription_id = self.event_bus.subscribe(
                topic="prediction.generated",
                callback=self._handle_prediction_event,
            )
            logger.info("IncidentAgent subscribed to 'prediction.generated' events.")

    def _handle_prediction_event(self, event: Event) -> None:
        """
        Event subscriber callback for 'prediction.generated' events.

        Args:
            event: Published Prediction Event object.
        """
        try:
            payload = event.payload or {}
            log_execution_event(
                logger,
                self.name,
                "EVENT_RECEIVED",
                f"IncidentAgent received prediction event for '{payload.get('interface')}'.",
            )
            self.execute(payload)
        except Exception as e:
            logger.error(f"Error handling 'prediction.generated' event in IncidentAgent: {e}", exc_info=True)

    def validate_input(self, input_data: Any) -> List[Dict[str, Any]]:
        """
        Validate execution input payload.

        Supports PredictionResult model, event dict, prediction payload dict, or list of predictions.
        """
        if input_data is None:
            return []

        if isinstance(input_data, PredictionResult):
            return [input_data.model_dump(mode="json")]

        if isinstance(input_data, Event):
            payload = input_data.payload or {}
            return [payload]

        if isinstance(input_data, list):
            validated: List[Dict[str, Any]] = []
            for item in input_data:
                if isinstance(item, PredictionResult):
                    validated.append(item.model_dump(mode="json"))
                elif isinstance(item, dict):
                    validated.append(item)
            return validated

        if isinstance(input_data, dict):
            # Check if dict wraps predictions list or is single prediction
            if "predictions" in input_data and isinstance(input_data["predictions"], list):
                return self.validate_input(input_data["predictions"])
            return [input_data]

        return []

    def _execute_internal(
        self, input_data: List[Dict[str, Any]], context: Optional[ExecutionContext] = None
    ) -> List[IncidentRecord]:
        """
        Execute incident processing logic, emit lifecycle events, and update context.

        Args:
            input_data: Validated list of prediction payload dictionaries.
            context: Shared ExecutionContext.

        Returns:
            List of processed IncidentRecord objects.
        """
        processed_incidents: List[IncidentRecord] = []
        exec_id = context.context_id if context else str(uuid.uuid4())

        for pred_raw in input_data:
            try:
                incident, action_tag = self._service.process_prediction(pred_raw)
                if incident:
                    processed_incidents.append(incident)

                    # Determine event topic based on action_tag
                    event_topic = f"incident.{action_tag}"
                    if action_tag not in ("created", "updated", "severity_changed", "resolved", "closed"):
                        event_topic = "incident.updated"

                    if self.event_bus:
                        evt = Event(
                            event_type=event_topic,
                            source=self.name,
                            payload=incident.model_dump(mode="json"),
                            metadata={
                                "execution_id": exec_id,
                                "incident_id": incident.incident_id,
                                "device_id": incident.device_id,
                                "severity": incident.severity.value,
                                "status": incident.status.value,
                                "timestamp": str(incident.updated_at),
                            },
                        )
                        self.event_bus.publish(evt)

            except Exception as e:
                logger.error(f"Error processing prediction item in IncidentAgent: {e}", exc_info=True)

        log_execution_event(
            logger,
            self.name,
            "INCIDENTS_PROCESSED",
            f"IncidentAgent processed {len(input_data)} prediction(s), resulting in {len(processed_incidents)} incident action(s).",
        )

        # Update execution context
        if context:
            context.results[self.name] = [inc.model_dump(mode="json") for inc in processed_incidents]
            context.shared_state["active_incidents"] = {
                inc.incident_id: inc.model_dump(mode="json") for inc in processed_incidents
            }

        return processed_incidents

    def shutdown(self) -> None:
        """Unsubscribe event handlers and shutdown IncidentAgent."""
        if self.event_bus and self._prediction_subscription_id:
            self.event_bus.unsubscribe(self._prediction_subscription_id)
            self._prediction_subscription_id = None
        super().shutdown()


def register_incident_agent(registry: Optional[AgentRegistry] = None) -> IncidentAgent:
    """
    Convenience function to instantiate and register IncidentAgent with AgentRegistry.

    Args:
        registry: Target AgentRegistry (defaults to global instance).

    Returns:
        Registered IncidentAgent instance.
    """
    target_registry = registry or AgentRegistry.get_global()
    agent = IncidentAgent()
    target_registry.register(agent, allow_override=True)
    return agent
