"""
Adaptive Failover Agent Module for Adaptive Multi-Provider Failover Subsystem.

Production-grade Atomic Agent wrapping AdaptiveFailoverService within the NOC Copilot agent framework.
Supports lifecycle management, schema validation, thread-safe metrics, EventBus event subscription/publishing,
and dependency injection via ServiceContainer.
"""

from typing import Any, Dict, Optional

from agents.base.base_agent import BaseAgent
from agents.core.container import ServiceContainer
from agents.core.exceptions import ExecutionError, ValidationError
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.adaptive_failover.adaptive_failover_service import AdaptiveFailoverService
from agents.adaptive_failover.adaptive_models import AdaptiveFailoverResult
from agents.schemas.schemas import AgentMetadata, CapabilityFlags, ExecutionContext


class AdaptiveFailoverAgent(BaseAgent):
    """
    Atomic Agent responsible for continuous adaptive provider monitoring, hysteresis enforcement,
    flapping protection, failover triggers, continuous verification, and safe failback.
    """

    def __init__(
        self,
        metadata: Optional[AgentMetadata] = None,
        container: Optional[ServiceContainer] = None,
        event_bus: Optional[EventBus] = None,
        service: Optional[AdaptiveFailoverService] = None,
    ) -> None:
        if not metadata:
            metadata = AgentMetadata(
                name="AdaptiveFailoverAgent",
                version="1.0.0",
                description="Adaptive Multi-Provider Failover, Failback & Network Stability Intelligence Engine.",
                dependencies=["FailoverAgent", "PathDecisionAgent", "TrustAgent", "PreMortemAgent", "RuntimeAgent"],
                tags=["adaptive", "failover", "failback", "stability", "hysteresis", "multi-provider"],
                capabilities=CapabilityFlags(
                    supports_async=True,
                    supports_batch=True,
                    supports_parallel_execution=True,
                    supports_cpu=True,
                ),
            )

        super().__init__(metadata=metadata, container=container, event_bus=event_bus)

        # Inject or resolve AdaptiveFailoverService
        if service:
            self._service = service
        else:
            self._service = AdaptiveFailoverService(event_bus=self.event_bus)

        # Register EventBus subscribers
        if self.event_bus:
            self.event_bus.subscribe("adaptive_failover.requested", self._handle_adaptive_requested)
            self.event_bus.subscribe("telemetry.updated", self._handle_telemetry_updated)
            self.event_bus.subscribe("prediction.updated", self._handle_prediction_updated)
            self.event_bus.subscribe("path.decision.completed", self._handle_path_decision)
            self.event_bus.subscribe("failover.completed", self._handle_failover_completed)
            self.event_bus.subscribe("provider.recovered", self._handle_provider_recovered)

    @property
    def service(self) -> AdaptiveFailoverService:
        """Domain service instance."""
        return self._service

    def _execute_internal(self, input_data: Any, context: Optional[ExecutionContext] = None) -> Dict[str, Any]:
        """
        Execute adaptive failover monitoring and stability evaluation cycle.

        Args:
            input_data: Validated input payload or ExecutionContext.
            context: Optional ExecutionContext container with parameters.

        Returns:
            Dict containing serialized AdaptiveFailoverResult.
        """
        exec_ctx = input_data if isinstance(input_data, ExecutionContext) else (context or ExecutionContext(payload=input_data if isinstance(input_data, dict) else {}))
        payload = (exec_ctx.payload if hasattr(exec_ctx, "payload") and exec_ctx.payload else None) or (exec_ctx.parameters if hasattr(exec_ctx, "parameters") and exec_ctx.parameters else None) or {}
        active_p = payload.get("active_provider", "ISP-A")
        candidate_p = payload.get("candidate_provider", "ISP-B")
        deg_duration = float(payload.get("degradation_duration_sec", 0.0))
        rec_duration = float(payload.get("recovery_duration_sec", 0.0))
        active_metrics = payload.get("active_metrics")
        candidate_metrics = payload.get("candidate_metrics")

        result: AdaptiveFailoverResult = self._service.process_adaptive_failover_cycle(
            active_provider=active_p,
            candidate_provider=candidate_p,
            active_metrics_override=active_metrics,
            candidate_metrics_override=candidate_metrics,
            degradation_duration_sec=deg_duration,
            recovery_duration_sec=rec_duration,
        )

        output_dict = result.model_dump(mode="json")
        return {"adaptive_failover_result": output_dict, "status": result.transition_status.value}

    def _handle_adaptive_requested(self, event: Event) -> None:
        """Event handler for adaptive_failover.requested."""
        self.logger.info("AdaptiveFailoverAgent received adaptive_failover.requested event")

    def _handle_telemetry_updated(self, event: Event) -> None:
        """Event handler for telemetry.updated."""
        pass

    def _handle_prediction_updated(self, event: Event) -> None:
        """Event handler for prediction.updated."""
        pass

    def _handle_path_decision(self, event: Event) -> None:
        """Event handler for path.decision.completed."""
        pass

    def _handle_failover_completed(self, event: Event) -> None:
        """Event handler for failover.completed."""
        pass

    def _handle_provider_recovered(self, event: Event) -> None:
        """Event handler for provider.recovered."""
        pass
