"""
Pre-Mortem Agent for Enterprise Pre-Mortem Subsystem.

Atomic Agent responsible for generating incident fingerprints, matching historical incidents,
simulating what-if scenarios, calculating time-to-impact windows, and issuing early warnings.
Subscribes to EventBus events, publishes structured lifecycle events, and populates context.
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
from agents.premortem.premortem_models import PreMortemResult
from agents.premortem.premortem_service import PreMortemService


class PreMortemAgent(BaseAgent):
    """
    Atomic Agent providing incident fingerprinting and pre-mortem future-state intelligence.
    """

    def __init__(
        self,
        metadata: Optional[AgentMetadata] = None,
        container: Optional[ServiceContainer] = None,
        event_bus: Optional[EventBus] = None,
        premortem_service: Optional[PreMortemService] = None,
    ) -> None:
        default_meta = AgentMetadata(
            name="PreMortemAgent",
            version="1.0.0",
            description="Enterprise Pre-Mortem Intelligence Agent generating incident fingerprints, historical matches, future scenarios, and early warnings.",
            capabilities=CapabilityFlags(supports_cpu=True, supports_parallel_execution=True),
        )
        super().__init__(metadata=metadata or default_meta, container=container, event_bus=event_bus)
        self._service = premortem_service or PreMortemService()
        self._register_event_subscribers()

    def _register_event_subscribers(self) -> None:
        """Subscribe to EventBus premortem, reasoning, and trust events."""
        bus = self.event_bus or EventBus.get_global()
        try:
            bus.subscribe("premortem.requested", self._handle_premortem_requested)
            bus.subscribe("trust.decision.completed", self._handle_trust_completed)
            bus.subscribe("reasoning.completed", self._handle_reasoning_completed)
        except Exception as e:
            self._logger.debug(f"EventBus subscription notice: {e}")

    def _handle_premortem_requested(self, event: Event) -> None:
        """EventBus callback handling premortem.requested."""
        self._logger.info("PreMortemAgent received 'premortem.requested' event.")

    def _handle_trust_completed(self, event: Event) -> None:
        """EventBus callback handling trust.decision.completed."""
        self._logger.info(f"PreMortemAgent received 'trust.decision.completed' event for request '{event.payload.get('request_id')}'.")

    def _handle_reasoning_completed(self, event: Event) -> None:
        """EventBus callback handling reasoning.completed."""
        self._logger.info(f"PreMortemAgent received 'reasoning.completed' event for request '{event.payload.get('request_id')}'.")

    def validate_input(self, input_data: Any) -> Any:
        """Validate input payload."""
        if isinstance(input_data, (PreMortemResult, TrustDecision, ReasoningResult, InvestigationContext, InvestigationRequest, dict, str)):
            return input_data
        raise ValidationError(f"PreMortemAgent expects TrustDecision, ReasoningResult, InvestigationContext, dict, or str, got {type(input_data)}")

    def validate_output(self, output_data: Any) -> PreMortemResult:
        """Validate output is PreMortemResult."""
        if isinstance(output_data, PreMortemResult):
            return output_data
        raise ValidationError(f"PreMortemAgent output must be PreMortemResult, got {type(output_data)}")

    def _execute_internal(
        self, input_data: Any, context: Optional[ExecutionContext] = None
    ) -> PreMortemResult:
        """
        Execute pre-mortem prediction pipeline and publish lifecycle events.
        """
        bus = self.event_bus or EventBus.get_global()

        # Resolve inputs
        inv_context: Optional[InvestigationContext] = None
        reasoning_result: Optional[ReasoningResult] = None
        trust_decision: Optional[TrustDecision] = None
        telemetry_payload: Optional[Dict[str, Any]] = None

        if isinstance(input_data, InvestigationContext):
            inv_context = input_data
            reasoning_result = inv_context.get_agent_output("ReasoningAgent")
            trust_decision = inv_context.get_agent_output("TrustAgent")
        elif isinstance(input_data, ReasoningResult):
            reasoning_result = input_data
        elif isinstance(input_data, TrustDecision):
            trust_decision = input_data
        elif isinstance(input_data, dict):
            telemetry_payload = input_data
            req = InvestigationRequest(**input_data) if "operator_query" in input_data else InvestigationRequest(operator_query="Pre-Mortem Analysis")
            inv_context = InvestigationContext(request=req)

        req_id = reasoning_result.request_id if reasoning_result else (
            trust_decision.request_id if trust_decision else (
                inv_context.request.request_id if inv_context and inv_context.request else "req-premortem-transient"
            )
        )

        # Lifecycle Event: premortem.started
        bus.publish(Event(event_type="premortem.started", source=self.name, payload={"request_id": req_id}))

        try:
            # Execute PreMortem Service Pipeline
            result = self._service.run_premortem_analysis(
                reasoning_result=reasoning_result,
                trust_decision=trust_decision,
                context=inv_context,
                telemetry_payload=telemetry_payload,
            )

            # Publish Intermediate Lifecycle Events
            bus.publish(
                Event(
                    event_type="premortem.fingerprint.generated",
                    source=self.name,
                    payload={"request_id": req_id, "fingerprint_id": result.fingerprint.fingerprint_id, "type": result.fingerprint.incident_type},
                )
            )
            bus.publish(
                Event(
                    event_type="premortem.history.matched",
                    source=self.name,
                    payload={"request_id": req_id, "match_count": len(result.historical_matches)},
                )
            )
            bus.publish(
                Event(
                    event_type="premortem.scenarios.generated",
                    source=self.name,
                    payload={"request_id": req_id, "scenario_count": len(result.scenarios)},
                )
            )
            bus.publish(
                Event(
                    event_type="premortem.time_to_impact.calculated",
                    source=self.name,
                    payload={"request_id": req_id, "min_time": result.time_to_impact.min_time_minutes, "max_time": result.time_to_impact.max_time_minutes},
                )
            )

            if result.early_warnings:
                bus.publish(
                    Event(
                        event_type="premortem.early_warning.detected",
                        source=self.name,
                        payload={"request_id": req_id, "warning_count": len(result.early_warnings), "title": result.early_warnings[0].title},
                    )
                )

            bus.publish(
                Event(
                    event_type="premortem.confidence.calculated",
                    source=self.name,
                    payload={"request_id": req_id, "score": result.confidence.score, "level": result.confidence.confidence_level},
                )
            )

            # Update ExecutionContext and InvestigationContext
            if context:
                if hasattr(context, "results") and isinstance(context.results, dict):
                    context.results[self.name] = result.model_dump(mode="json")
                if hasattr(context, "shared_state") and isinstance(context.shared_state, dict):
                    context.shared_state["premortem_result"] = result.model_dump(mode="json")

            if inv_context:
                inv_context.set_agent_output(self.name, result)
                inv_context.set_shared("premortem_result", result.model_dump(mode="json"))

            # Lifecycle Event: premortem.completed
            bus.publish(
                Event(
                    event_type="premortem.completed",
                    source=self.name,
                    payload={"request_id": req_id, "premortem_id": result.premortem_id, "confidence": result.confidence.score},
                )
            )

            return result

        except Exception as e:
            bus.publish(
                Event(
                    event_type="premortem.failed",
                    source=self.name,
                    payload={"request_id": req_id, "error": str(e)},
                )
            )
            raise
