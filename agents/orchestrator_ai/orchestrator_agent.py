"""
AI Orchestrator Agent for Enterprise AI Investigation Platform.

Central entry point and intelligent coordinator for AI-driven network investigations.
Invokes PlannerAgent, constructs ExecutionGraph DAGs, schedules execution, collects evidence,
and returns merged InvestigationResults while publishing lifecycle EventBus events.

CRITICAL PRINCIPLE: OrchestratorAgent coordinates execution only; it performs no direct domain logic.
"""

from typing import Any, Dict, Optional

from agents.base.base_agent import BaseAgent
from agents.core.container import ServiceContainer
from agents.core.exceptions import ValidationError
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.orchestrator_ai.investigation_context import InvestigationContext
from agents.orchestrator_ai.investigation_models import (
    InvestigationRequest,
    InvestigationResult,
    PlanStatus,
)
from agents.orchestrator_ai.orchestration_service import OrchestrationService
from agents.schemas.schemas import AgentMetadata, CapabilityFlags, ExecutionContext


class OrchestratorAgent(BaseAgent):
    """
    Central Atomic Agent responsible for orchestrating enterprise AI network investigations.
    """

    def __init__(
        self,
        metadata: Optional[AgentMetadata] = None,
        container: Optional[ServiceContainer] = None,
        event_bus: Optional[EventBus] = None,
        orchestration_service: Optional[OrchestrationService] = None,
    ) -> None:
        default_meta = AgentMetadata(
            name="OrchestratorAgent",
            version="1.0.0",
            description="Enterprise AI Investigation Orchestrator agent coordinating Atomic Agents.",
            capabilities=CapabilityFlags(supports_cpu=True, supports_parallel_execution=True),
        )
        super().__init__(metadata=metadata or default_meta, container=container, event_bus=event_bus)
        self._service = orchestration_service or OrchestrationService(
            event_bus=self.event_bus,
            registry=self.container.resolve(type(self._get_registry())) if self.container.has_service(type(self._get_registry())) else None,
        )

    def _get_registry(self) -> Any:
        from agents.registry.registry import AgentRegistry
        return AgentRegistry.get_global()

    def validate_input(self, input_data: Any) -> InvestigationRequest:
        """Validate and parse input into InvestigationRequest."""
        if isinstance(input_data, InvestigationRequest):
            return input_data
        elif isinstance(input_data, dict):
            return InvestigationRequest(**input_data)
        elif isinstance(input_data, str):
            return InvestigationRequest(operator_query=input_data)
        else:
            raise ValidationError(f"OrchestratorAgent expects InvestigationRequest, dict, or str, got {type(input_data)}")

    def validate_output(self, output_data: Any) -> InvestigationResult:
        """Validate output payload is an InvestigationResult."""
        if isinstance(output_data, InvestigationResult):
            return output_data
        raise ValidationError(f"OrchestratorAgent output must be an InvestigationResult, got {type(output_data)}")

    def _execute_internal(
        self, input_data: InvestigationRequest, context: Optional[ExecutionContext] = None
    ) -> InvestigationResult:
        """
        Orchestrate investigation workflow and publish lifecycle events.
        """
        bus = self.event_bus or EventBus.get_global()
        request_id = input_data.request_id

        # Lifecycle Event: investigation.started
        bus.publish(
            Event(
                event_type="investigation.started",
                source=self.name,
                payload={"request_id": request_id, "query": input_data.operator_query},
            )
        )

        inv_context = InvestigationContext(request=input_data)

        try:
            result = self._service.orchestrate(request=input_data, context=inv_context)

            # Lifecycle Event: investigation.planned
            if inv_context.plan:
                bus.publish(
                    Event(
                        event_type="investigation.planned",
                        source=self.name,
                        payload={
                            "request_id": request_id,
                            "plan_id": inv_context.plan.plan_id,
                            "stages": len(inv_context.plan.stages),
                        },
                    )
                )

            # Final Lifecycle Events: investigation.completed or investigation.failed
            if result.status == PlanStatus.COMPLETED:
                bus.publish(
                    Event(
                        event_type="investigation.completed",
                        source=self.name,
                        payload={
                            "request_id": request_id,
                            "investigation_id": result.investigation_id,
                            "confidence": result.overall_confidence,
                        },
                    )
                )
            else:
                bus.publish(
                    Event(
                        event_type="investigation.failed",
                        source=self.name,
                        payload={
                            "request_id": request_id,
                            "investigation_id": result.investigation_id,
                            "summary": result.summary,
                        },
                    )
                )

            return result

        except Exception as e:
            bus.publish(
                Event(
                    event_type="investigation.failed",
                    source=self.name,
                    payload={"request_id": request_id, "error": str(e)},
                )
            )
            raise
