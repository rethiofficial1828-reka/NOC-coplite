"""
Production Prediction Agent Implementation.

Subclasses BaseAgent to execute predictive risk assessments, subscribe to 'telemetry.updated'
events, publish 'prediction.generated' events, and update workflow ExecutionContext.
"""

from typing import Any, Dict, List, Optional, Union
import uuid

from agents.base.base_agent import BaseAgent
from agents.core.container import ServiceContainer
from agents.core.logger import get_agent_logger, log_execution_event
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.prediction.prediction_service import PredictionService
from agents.registry.registry import AgentRegistry
from agents.schemas.schemas import (
    AgentMetadata,
    CapabilityFlags,
    ExecutionContext,
    PredictionResult,
    TelemetryPacket,
)
from config.config_manager import ConfigManager

logger = get_agent_logger("PredictionAgent")


class PredictionAgent(BaseAgent):
    """
    Production Prediction Agent for NOC Copilot.

    Interfaces with PredictionService to compute ML risk predictions, listens for 'telemetry.updated'
    events, emits 'prediction.generated' events, and records workflow state.
    """

    def __init__(
        self,
        service: Optional[PredictionService] = None,
        metadata: Optional[AgentMetadata] = None,
        container: Optional[ServiceContainer] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        """
        Initialize PredictionAgent.

        Args:
            service: PredictionService instance.
            metadata: AgentMetadata instance.
            container: ServiceContainer instance.
            event_bus: EventBus instance.
        """
        agent_metadata = metadata or AgentMetadata(
            name="PredictionAgent",
            version="1.0.0",
            description="Wraps predictive XGBoost ML engine to assess network failure risks and time-to-impact.",
            author="NOC Copilot Core Team",
            dependencies=["TelemetryAgent"],
            tags=["ml", "prediction", "risk"],
            capabilities=CapabilityFlags(supports_cpu=True, supports_batch=True),
        )

        super().__init__(metadata=agent_metadata, container=container, event_bus=event_bus)
        self._service = service or PredictionService()
        self._telemetry_subscription_id: Optional[str] = None
        self._setup_event_subscription()

    @property
    def service(self) -> PredictionService:
        """Prediction service instance."""
        return self._service

    def _setup_event_subscription(self) -> None:
        """Subscribe to 'telemetry.updated' events on the EventBus."""
        if self.event_bus:
            self._telemetry_subscription_id = self.event_bus.subscribe(
                topic="telemetry.updated",
                callback=self._handle_telemetry_event,
            )
            logger.info("PredictionAgent subscribed to 'telemetry.updated' events.")

    def _handle_telemetry_event(self, event: Event) -> None:
        """
        Event subscriber callback for 'telemetry.updated' events. Automatically triggers prediction.

        Args:
            event: Published Telemetry Event object.
        """
        try:
            payload = event.payload or {}
            interface_name = payload.get("interface") or event.metadata.get("interface") or "all"
            log_execution_event(
                logger,
                self.name,
                "EVENT_RECEIVED",
                f"PredictionAgent received telemetry update for '{interface_name}'.",
            )
            self.execute({"interface": interface_name})
        except Exception as e:
            logger.error(f"Error handling 'telemetry.updated' event in PredictionAgent: {e}", exc_info=True)

    def validate_input(self, input_data: Any) -> Dict[str, Any]:
        """
        Validate execution input options.

        Expected format dict:
            {
                "interface": "Branch3-Uplink",  # Specific interface name, list, or "all"
                "telemetry_packet": TelemetryPacket  # Optional packet model
            }
        """
        if input_data is None:
            return {"interface": "all"}

        if isinstance(input_data, str):
            return {"interface": input_data}

        if isinstance(input_data, TelemetryPacket):
            return {"interface": input_data.interface, "telemetry_packet": input_data}

        if isinstance(input_data, Event):
            payload = input_data.payload or {}
            iface = payload.get("interface") or input_data.metadata.get("interface") or "all"
            return {"interface": iface}

        if isinstance(input_data, dict):
            iface = input_data.get("interface") or input_data.get("device_id") or "all"
            return {"interface": iface}

        return {"interface": "all"}

    def _execute_internal(
        self, input_data: Dict[str, Any], context: Optional[ExecutionContext] = None
    ) -> List[PredictionResult]:
        """
        Execute predictive risk engine, publish 'prediction.generated' events, and update context.

        Args:
            input_data: Validated execution options.
            context: Shared ExecutionContext.

        Returns:
            List of PredictionResult objects.
        """
        target = input_data.get("interface", "all")
        results: List[PredictionResult] = []

        if target == "all" or not target:
            results = self._service.predict_fleet()
        elif isinstance(target, list):
            results = self._service.predict_fleet(interfaces=target)
        else:
            single_res = self._service.predict_for_interface(str(target))
            results = [single_res]

        exec_id = context.context_id if context else str(uuid.uuid4())

        # Publish prediction.generated events
        published_count = 0
        if self.event_bus:
            for pred in results:
                evt = Event(
                    event_type="prediction.generated",
                    source=self.name,
                    payload=pred.model_dump(mode="json"),
                    metadata={
                        "execution_id": exec_id,
                        "device_id": pred.interface,
                        "interface": pred.interface,
                        "timestamp": str(pred.timestamp),
                        "risk_score": pred.risk_score,
                        "confidence": pred.confidence,
                    },
                )
                self.event_bus.publish(evt)
                published_count += 1

        log_execution_event(
            logger,
            self.name,
            "PREDICTIONS_GENERATED",
            f"PredictionAgent computed {len(results)} risk prediction(s) (published {published_count} events).",
        )

        # Update execution context
        if context:
            context.results[self.name] = [p.model_dump(mode="json") for p in results]
            context.shared_state["latest_predictions"] = {
                p.interface: p.model_dump(mode="json") for p in results
            }

        return results

    def shutdown(self) -> None:
        """Unsubscribe event handlers and shutdown PredictionAgent."""
        if self.event_bus and self._telemetry_subscription_id:
            self.event_bus.unsubscribe(self._telemetry_subscription_id)
            self._telemetry_subscription_id = None
        super().shutdown()


def register_prediction_agent(registry: Optional[AgentRegistry] = None) -> PredictionAgent:
    """
    Convenience function to instantiate and register PredictionAgent with AgentRegistry.

    Args:
        registry: Target AgentRegistry (defaults to global instance).

    Returns:
        Registered PredictionAgent instance.
    """
    target_registry = registry or AgentRegistry.get_global()
    agent = PredictionAgent()
    target_registry.register(agent, allow_override=True)
    return agent
