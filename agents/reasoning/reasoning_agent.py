"""
Enterprise Reasoning Agent for Enterprise AI Investigation Platform.

Atomic Agent responsible for performing evidence-driven reasoning, hypothesis validation,
contradiction analysis, and root-cause selection. Subscribes to EventBus investigation events,
publishes detailed reasoning lifecycle events, and populates shared context state.
"""

from typing import Any, Dict, Optional

from agents.base.base_agent import BaseAgent
from agents.core.container import ServiceContainer
from agents.core.exceptions import ValidationError
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.orchestrator_ai.investigation_context import InvestigationContext
from agents.orchestrator_ai.investigation_models import InvestigationRequest
from agents.reasoning.reasoning_models import (
    InvestigationConclusion,
    ReasoningResult,
)
from agents.reasoning.reasoning_service import ReasoningService
from agents.schemas.schemas import AgentMetadata, CapabilityFlags, ExecutionContext


class ReasoningAgent(BaseAgent):
    """
    Atomic Agent providing evidence correlation, hypothesis generation, and root cause reasoning.
    """

    def __init__(
        self,
        metadata: Optional[AgentMetadata] = None,
        container: Optional[ServiceContainer] = None,
        event_bus: Optional[EventBus] = None,
        reasoning_service: Optional[ReasoningService] = None,
    ) -> None:
        default_meta = AgentMetadata(
            name="ReasoningAgent",
            version="1.0.0",
            description="Enterprise AI Reasoning Agent providing evidence correlation, hypothesis validation, and root cause selection.",
            capabilities=CapabilityFlags(supports_cpu=True, supports_parallel_execution=True),
        )
        super().__init__(metadata=metadata or default_meta, container=container, event_bus=event_bus)
        self._service = reasoning_service or ReasoningService()
        self._register_event_subscribers()

    def _register_event_subscribers(self) -> None:
        """Subscribe to EventBus investigation events."""
        bus = self.event_bus or EventBus.get_global()
        try:
            bus.subscribe("investigation.completed", self._handle_investigation_completed)
            bus.subscribe("reasoning.requested", self._handle_reasoning_requested)
        except Exception as e:
            self._logger.debug(f"EventBus subscription notice: {e}")

    def _handle_investigation_completed(self, event: Event) -> None:
        """EventBus callback handling investigation.completed."""
        self._logger.info(f"ReasoningAgent received 'investigation.completed' event for request '{event.payload.get('request_id')}'")

    def _handle_reasoning_requested(self, event: Event) -> None:
        """EventBus callback handling reasoning.requested."""
        self._logger.info(f"ReasoningAgent received 'reasoning.requested' event.")

    def validate_input(self, input_data: Any) -> Any:
        """Validate input payload."""
        if isinstance(input_data, (InvestigationContext, InvestigationRequest, dict, str)):
            return input_data
        raise ValidationError(f"ReasoningAgent expects InvestigationContext, InvestigationRequest, dict, or str, got {type(input_data)}")

    def validate_output(self, output_data: Any) -> ReasoningResult:
        """Validate output is ReasoningResult."""
        if isinstance(output_data, ReasoningResult):
            return output_data
        raise ValidationError(f"ReasoningAgent output must be ReasoningResult, got {type(output_data)}")

    def _execute_internal(
        self, input_data: Any, context: Optional[ExecutionContext] = None
    ) -> ReasoningResult:
        """
        Perform evidence reasoning and publish lifecycle events.
        """
        bus = self.event_bus or EventBus.get_global()

        # Build or resolve InvestigationContext
        if isinstance(input_data, InvestigationContext):
            inv_context = input_data
        elif isinstance(input_data, InvestigationRequest):
            inv_context = InvestigationContext(request=input_data)
        elif isinstance(input_data, dict):
            req = InvestigationRequest(**input_data)
            inv_context = InvestigationContext(request=req)
        elif isinstance(input_data, str):
            req = InvestigationRequest(operator_query=input_data)
            inv_context = InvestigationContext(request=req)
        else:
            req = InvestigationRequest(operator_query="General Network Diagnostics")
            inv_context = InvestigationContext(request=req)

        request_id = inv_context.request.request_id

        # Lifecycle Event: reasoning.started
        bus.publish(Event(event_type="reasoning.started", source=self.name, payload={"request_id": request_id}))

        try:
            # 1. Correlate evidence
            correlation = self._service._correlator.correlate(context=inv_context)
            bus.publish(
                Event(
                    event_type="reasoning.evidence.correlated",
                    source=self.name,
                    payload={"request_id": request_id, "group_count": len(correlation.groups)},
                )
            )

            # 2. Generate hypotheses & validate
            result = self._service.process_reasoning(inv_context)

            bus.publish(
                Event(
                    event_type="reasoning.hypotheses.generated",
                    source=self.name,
                    payload={"request_id": request_id, "count": len(result.conclusion.ranked_hypotheses)},
                )
            )
            bus.publish(
                Event(
                    event_type="reasoning.validation.completed",
                    source=self.name,
                    payload={"request_id": request_id, "valid": True},
                )
            )
            bus.publish(
                Event(
                    event_type="reasoning.confidence.calculated",
                    source=self.name,
                    payload={"request_id": request_id, "confidence": result.conclusion.confidence_result.overall_confidence},
                )
            )

            if result.conclusion.primary_root_cause:
                bus.publish(
                    Event(
                        event_type="reasoning.rootcause.selected",
                        source=self.name,
                        payload={
                            "request_id": request_id,
                            "root_cause": result.conclusion.primary_root_cause.title,
                            "probability": result.conclusion.primary_root_cause.probability,
                        },
                    )
                )

            # Update ExecutionContext / shared_state
            if context:
                if hasattr(context, "results") and isinstance(context.results, dict):
                    context.results[self.name] = result.model_dump(mode="json")
                if hasattr(context, "shared_state") and isinstance(context.shared_state, dict):
                    context.shared_state["reasoning_conclusion"] = result.conclusion.model_dump(mode="json")

            inv_context.set_agent_output(self.name, result)
            inv_context.set_shared("reasoning_conclusion", result.conclusion.model_dump(mode="json"))

            # Lifecycle Event: reasoning.completed
            bus.publish(
                Event(
                    event_type="reasoning.completed",
                    source=self.name,
                    payload={"request_id": request_id, "reasoning_id": result.reasoning_id},
                )
            )

            return result

        except Exception as e:
            bus.publish(
                Event(
                    event_type="reasoning.failed",
                    source=self.name,
                    payload={"request_id": request_id, "error": str(e)},
                )
            )
            raise
