"""
Path Decision Agent Module for Enterprise Intelligent Network Path & Provider Decision Engine.

Production-grade Atomic Agent wrapping PathDecisionService within the NOC Copilot agent framework.
Supports lifecycle management, schema validation, thread-safe metrics, EventBus event subscription/publishing,
and dependency injection via ServiceContainer.
"""

from typing import Any, Dict, Optional

from agents.base.base_agent import BaseAgent
from agents.core.container import ServiceContainer
from agents.core.exceptions import ExecutionError, ValidationError
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.path_decision.decision_service import PathDecisionService
from agents.path_decision.path_models import PathDecisionResult
from agents.schemas.schemas import AgentMetadata, CapabilityFlags, ExecutionContext


class PathDecisionAgent(BaseAgent):
    """
    Atomic Agent responsible for network path and provider decision evaluations.
    """

    def __init__(
        self,
        metadata: Optional[AgentMetadata] = None,
        container: Optional[ServiceContainer] = None,
        event_bus: Optional[EventBus] = None,
        service: Optional[PathDecisionService] = None,
    ) -> None:
        if not metadata:
            metadata = AgentMetadata(
                name="PathDecisionAgent",
                version="1.0.0",
                description="Evidence-driven network path and provider decision engine.",
                dependencies=["TopologyAgent", "TelemetryAgent", "PredictionAgent", "ReasoningAgent", "TrustAgent", "PreMortemAgent"],
                tags=["path", "provider", "failover", "decision", "network"],
                capabilities=CapabilityFlags(
                    supports_async=True,
                    supports_batch=True,
                    supports_parallel_execution=True,
                    supports_cpu=True,
                ),
            )

        super().__init__(metadata=metadata, container=container, event_bus=event_bus)

        # Inject or resolve PathDecisionService
        if service:
            self._service = service
        else:
            self._service = PathDecisionService(event_bus=self.event_bus)

        # Register event bus subscribers if event bus present
        if self.event_bus:
            self.event_bus.subscribe("incident.created", self._handle_incident_event)
            self.event_bus.subscribe("prediction.risk_elevated", self._handle_risk_event)
            self.event_bus.subscribe("path.decision.requested", self._handle_decision_request)

    @property
    def service(self) -> PathDecisionService:
        """Domain service instance."""
        return self._service

    def _execute_internal(self, input_data: Any, context: Optional[ExecutionContext] = None) -> Dict[str, Any]:
        """
        Execute path decision pipeline over an ExecutionContext or input payload.

        Args:
            input_data: Validated input payload or ExecutionContext.
            context: Optional ExecutionContext container with parameters.

        Returns:
            Dict containing serialized PathDecisionResult.
        """
        exec_ctx = input_data if isinstance(input_data, ExecutionContext) else (context or ExecutionContext(parameters={"target": str(input_data)} if isinstance(input_data, str) else (input_data if isinstance(input_data, dict) else {})))
        params = exec_ctx.parameters or {}
        target = params.get("target") or params.get("interface") or params.get("device_id") or "Branch3-Uplink"

        override_telemetry = params.get("override_telemetry")
        override_risk = params.get("override_risk")

        try:
            request_id = exec_ctx.context_id if exec_ctx else (context.context_id if context else None)
            decision_res: PathDecisionResult = self._service.evaluate_path_decision(
                target_interface_or_device=str(target),
                request_id=request_id,
                override_telemetry=override_telemetry,
                override_risk=override_risk,
            )

            result_dict = decision_res.model_dump(mode="json")
            exec_ctx.results[self.name] = result_dict
            return result_dict

        except Exception as exc:
            self._logger.error(f"Error in PathDecisionAgent execution for target '{target}': {exc}", exc_info=True)
            raise ExecutionError(f"PathDecisionAgent execution failed: {exc}") from exc

    def _handle_incident_event(self, event: Event) -> None:
        """Event handler for 'incident.created' topic."""
        payload = event.payload or {}
        target = payload.get("interface") or payload.get("device_id") or "Branch3-Uplink"
        self._logger.info(f"PathDecisionAgent received incident event for target '{target}'")

        ctx = ExecutionContext(parameters={"target": target, "incident_id": payload.get("incident_id")})
        self.execute(ctx)

    def _handle_risk_event(self, event: Event) -> None:
        """Event handler for 'prediction.risk_elevated' topic."""
        payload = event.payload or {}
        target = payload.get("interface") or "Branch3-Uplink"
        self._logger.info(f"PathDecisionAgent received elevated risk event for target '{target}'")

        ctx = ExecutionContext(parameters={"target": target, "risk_score": payload.get("risk_score")})
        self.execute(ctx)

    def _handle_decision_request(self, event: Event) -> None:
        """Event handler for 'path.decision.requested' topic."""
        payload = event.payload or {}
        target = payload.get("target") or payload.get("interface") or "Branch3-Uplink"
        self._logger.info(f"PathDecisionAgent received explicit path decision request for target '{target}'")

        ctx = ExecutionContext(parameters=payload)
        self.execute(ctx)
