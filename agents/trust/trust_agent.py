"""
Trust Agent for Enterprise Trust, Verification & Safe Autonomy Subsystem.

Atomic Agent responsible for evidence re-validation, adversarial verification,
counterfactual probing, blast radius calculation, and safe autonomy policy evaluation.
Subscribes to EventBus events, publishes structured lifecycle events, and populates shared context.
"""

from typing import Any, Dict, Optional

from agents.base.base_agent import BaseAgent
from agents.core.container import ServiceContainer
from agents.core.exceptions import ValidationError
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.orchestrator_ai.investigation_context import InvestigationContext
from agents.orchestrator_ai.investigation_models import InvestigationRequest
from agents.reasoning.reasoning_models import ReasoningResult
from agents.schemas.schemas import AgentMetadata, CapabilityFlags, ExecutionContext
from agents.trust.trust_models import TrustDecision
from agents.trust.trust_service import TrustService


class TrustAgent(BaseAgent):
    """
    Atomic Agent providing safe autonomy policy evaluation and trust decision generation.
    """

    def __init__(
        self,
        metadata: Optional[AgentMetadata] = None,
        container: Optional[ServiceContainer] = None,
        event_bus: Optional[EventBus] = None,
        trust_service: Optional[TrustService] = None,
    ) -> None:
        default_meta = AgentMetadata(
            name="TrustAgent",
            version="1.0.0",
            description="Enterprise Safe Autonomy Agent evaluating evidence validity, adversarial challenges, blast radius, and approval policy.",
            capabilities=CapabilityFlags(supports_cpu=True, supports_parallel_execution=True),
        )
        super().__init__(metadata=metadata or default_meta, container=container, event_bus=event_bus)
        self._service = trust_service or TrustService()
        self._register_event_subscribers()

    def _register_event_subscribers(self) -> None:
        """Subscribe to EventBus trust and investigation events."""
        bus = self.event_bus or EventBus.get_global()
        try:
            bus.subscribe("trust.requested", self._handle_trust_requested)
            bus.subscribe("reasoning.completed", self._handle_reasoning_completed)
            bus.subscribe("investigation.completed", self._handle_investigation_completed)
        except Exception as e:
            self._logger.debug(f"EventBus subscription notice: {e}")

    def _handle_trust_requested(self, event: Event) -> None:
        """EventBus callback handling trust.requested."""
        self._logger.info("TrustAgent received 'trust.requested' event.")

    def _handle_reasoning_completed(self, event: Event) -> None:
        """EventBus callback handling reasoning.completed."""
        self._logger.info(f"TrustAgent received 'reasoning.completed' event for request '{event.payload.get('request_id')}'.")

    def _handle_investigation_completed(self, event: Event) -> None:
        """EventBus callback handling investigation.completed."""
        self._logger.info(f"TrustAgent received 'investigation.completed' event for request '{event.payload.get('request_id')}'.")

    def validate_input(self, input_data: Any) -> Any:
        """Validate input payload."""
        if isinstance(input_data, (ReasoningResult, InvestigationContext, InvestigationRequest, dict, str)):
            return input_data
        raise ValidationError(f"TrustAgent expects ReasoningResult, InvestigationContext, dict, or str, got {type(input_data)}")

    def validate_output(self, output_data: Any) -> TrustDecision:
        """Validate output is TrustDecision."""
        if isinstance(output_data, TrustDecision):
            return output_data
        raise ValidationError(f"TrustAgent output must be TrustDecision, got {type(output_data)}")

    def _execute_internal(
        self, input_data: Any, context: Optional[ExecutionContext] = None
    ) -> TrustDecision:
        """
        Execute trust evaluation pipeline and publish lifecycle events.
        """
        bus = self.event_bus or EventBus.get_global()

        # Resolve ReasoningResult and InvestigationContext
        inv_context: Optional[InvestigationContext] = None
        reasoning_result: Optional[ReasoningResult] = None

        if isinstance(input_data, ReasoningResult):
            reasoning_result = input_data
        elif isinstance(input_data, InvestigationContext):
            inv_context = input_data
            reasoning_result = inv_context.get_agent_output("ReasoningAgent")
        elif isinstance(input_data, (dict, str, InvestigationRequest)):
            # Create transient reasoning result if none present
            req = input_data if isinstance(input_data, InvestigationRequest) else (
                InvestigationRequest(**input_data) if isinstance(input_data, dict) else InvestigationRequest(operator_query=input_data)
            )
            inv_context = InvestigationContext(request=req)
            from agents.reasoning.reasoning_agent import ReasoningAgent
            reasoning_agent = ReasoningAgent()
            reasoning_result = reasoning_agent.execute(inv_context)

        if not reasoning_result:
            # Execute transient reasoning to produce ReasoningResult
            from agents.reasoning.reasoning_agent import ReasoningAgent
            reasoning_agent = ReasoningAgent()
            req = InvestigationRequest(operator_query="Safety Autonomy Validation")
            inv_context = inv_context or InvestigationContext(request=req)
            reasoning_result = reasoning_agent.execute(inv_context)

        request_id = reasoning_result.request_id

        # Lifecycle Event: trust.started
        bus.publish(Event(event_type="trust.started", source=self.name, payload={"request_id": request_id}))

        try:
            # 1. Evidence Re-validation Event
            bus.publish(Event(event_type="trust.evidence.revalidated", source=self.name, payload={"request_id": request_id}))

            # 2. Execute Trust Service Pipeline
            decision = self._service.evaluate_trust(reasoning_result=reasoning_result, context=inv_context)

            # Publish Intermediate Lifecycle Events
            bus.publish(
                Event(
                    event_type="trust.adversarial.completed",
                    source=self.name,
                    payload={"request_id": request_id, "disproved": decision.trust_assessment.verification_status.value},
                )
            )
            bus.publish(
                Event(
                    event_type="trust.counterfactual.completed",
                    source=self.name,
                    payload={"request_id": request_id, "conclusion": decision.explanation.counterfactual_result},
                )
            )
            bus.publish(
                Event(
                    event_type="trust.blastradius.completed",
                    source=self.name,
                    payload={"request_id": request_id, "level": decision.trust_assessment.blast_radius.potential_action_level.value},
                )
            )
            bus.publish(
                Event(
                    event_type="trust.confidence.assessed",
                    source=self.name,
                    payload={"request_id": request_id, "trust_score": decision.trust_assessment.trust_score.overall_trust_score},
                )
            )
            bus.publish(
                Event(
                    event_type="trust.autonomy.decided",
                    source=self.name,
                    payload={"request_id": request_id, "decision": decision.decision.value},
                )
            )

            # Update ExecutionContext and InvestigationContext
            if context:
                if hasattr(context, "results") and isinstance(context.results, dict):
                    context.results[self.name] = decision.model_dump(mode="json")
                if hasattr(context, "shared_state") and isinstance(context.shared_state, dict):
                    context.shared_state["trust_decision"] = decision.model_dump(mode="json")

            if inv_context:
                inv_context.set_agent_output(self.name, decision)
                inv_context.set_shared("trust_decision", decision.model_dump(mode="json"))

            # Lifecycle Event: trust.decision.completed
            bus.publish(
                Event(
                    event_type="trust.decision.completed",
                    source=self.name,
                    payload={"request_id": request_id, "decision_id": decision.decision_id, "decision": decision.decision.value},
                )
            )

            return decision

        except Exception as e:
            bus.publish(
                Event(
                    event_type="trust.failed",
                    source=self.name,
                    payload={"request_id": request_id, "error": str(e)},
                )
            )
            raise
