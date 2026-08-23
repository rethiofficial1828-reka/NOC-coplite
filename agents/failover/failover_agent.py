"""
Failover Agent Module for Enterprise Controlled Failover Execution & Closed-Loop Verification Engine.

Production-grade Atomic Agent wrapping FailoverService within the NOC Copilot agent framework.
Supports lifecycle management, schema validation, thread-safe metrics, EventBus event subscription/publishing,
and dependency injection via ServiceContainer.
"""

from typing import Any, Dict, Optional

from agents.base.base_agent import BaseAgent
from agents.core.container import ServiceContainer
from agents.core.exceptions import ExecutionError, ValidationError
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.failover.failover_models import ExecutionMode, FailoverResult, VerificationStatus
from agents.failover.failover_service import FailoverService
from agents.schemas.schemas import AgentMetadata, CapabilityFlags, ExecutionContext


class FailoverAgent(BaseAgent):
    """
    Atomic Agent responsible for network failover execution, approval validation,
    16-point pre-execution validation, closed-loop verification, and automated rollback.
    """

    def __init__(
        self,
        metadata: Optional[AgentMetadata] = None,
        container: Optional[ServiceContainer] = None,
        event_bus: Optional[EventBus] = None,
        service: Optional[FailoverService] = None,
    ) -> None:
        if not metadata:
            metadata = AgentMetadata(
                name="FailoverAgent",
                version="1.0.0",
                description="Enterprise Controlled Failover Execution & Closed-Loop Verification Engine.",
                dependencies=["PathDecisionAgent", "TrustAgent", "PreMortemAgent", "ReasoningAgent", "RuntimeAgent"],
                tags=["failover", "execution", "verification", "rollback", "approval", "network"],
                capabilities=CapabilityFlags(
                    supports_async=True,
                    supports_batch=True,
                    supports_parallel_execution=True,
                    supports_cpu=True,
                ),
            )

        super().__init__(metadata=metadata, container=container, event_bus=event_bus)

        # Inject or resolve FailoverService
        if service:
            self._service = service
        else:
            self._service = FailoverService(event_bus=self.event_bus)

        # Register EventBus subscribers
        if self.event_bus:
            self.event_bus.subscribe("failover.requested", self._handle_failover_requested)
            self.event_bus.subscribe("failover.approved", self._handle_failover_approved)
            self.event_bus.subscribe("trust.decision.completed", self._handle_trust_decision)
            self.event_bus.subscribe("path.decision.completed", self._handle_path_decision)

    @property
    def service(self) -> FailoverService:
        """Domain service instance."""
        return self._service

    def _execute_internal(self, input_data: Any, context: Optional[ExecutionContext] = None) -> Dict[str, Any]:
        """
        Execute closed-loop failover execution over an ExecutionContext or input payload.

        Args:
            input_data: Validated input payload or ExecutionContext.
            context: Optional ExecutionContext container with parameters.

        Returns:
            Dict output containing serialized FailoverResult.
        """
        exec_ctx = input_data if isinstance(input_data, ExecutionContext) else (context or ExecutionContext(payload=input_data if isinstance(input_data, dict) else {}))
        payload = (exec_ctx.payload if hasattr(exec_ctx, "payload") and exec_ctx.payload else None) or (exec_ctx.parameters if hasattr(exec_ctx, "parameters") and exec_ctx.parameters else None) or {}
        target = payload.get("target_interface", payload.get("target_device", payload.get("target", "Branch3-Uplink")))
        mode_str = payload.get("mode", "DRY_RUN")
        execution_mode = ExecutionMode.APPROVED_EXECUTION if mode_str == "APPROVED_EXECUTION" else ExecutionMode.DRY_RUN
        operator_id = payload.get("operator_id", "SYSTEM_OPERATOR")
        auto_approve = bool(payload.get("auto_approve", False))
        adapter_name = payload.get("adapter_name", "DryRunExecutionAdapter")
        over_verif = payload.get("override_verification_status")

        override_verif_status: Optional[VerificationStatus] = None
        if over_verif:
            override_verif_status = VerificationStatus(over_verif)

        result: FailoverResult = self._service.execute_failover_pipeline(
            target_interface_or_device=target,
            execution_mode=execution_mode,
            operator_id=operator_id,
            auto_approve=auto_approve,
            adapter_name=adapter_name,
            override_verification_status=override_verif_status,
        )

        output_dict = result.model_dump(mode="json")
        return {"failover_result": output_dict, "status": result.final_status.value}

    def _handle_failover_requested(self, event: Event) -> None:
        """Event handler for failover.requested."""
        payload = event.payload or {}
        target = payload.get("target", "Branch3-Uplink")
        self.logger.info(f"FailoverAgent received failover.requested event for target '{target}'")

    def _handle_failover_approved(self, event: Event) -> None:
        """Event handler for failover.approved."""
        payload = event.payload or {}
        app_id = payload.get("approval_id")
        self.logger.info(f"FailoverAgent received failover.approved event for approval '{app_id}'")

    def _handle_trust_decision(self, event: Event) -> None:
        """Event handler for trust.decision.completed."""
        pass

    def _handle_path_decision(self, event: Event) -> None:
        """Event handler for path.decision.completed."""
        pass
