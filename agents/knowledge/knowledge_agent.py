"""
Production Knowledge Agent Implementation.

Subclasses BaseAgent to synthesize operational runbooks, LLM reasoning, and recommendation context,
subscribe to 'recommendation.generated' events, publish 'knowledge.generated' events, and update ExecutionContext.
"""

from typing import Any, Dict, List, Optional, Union
import uuid

from agents.base.base_agent import BaseAgent
from agents.core.container import ServiceContainer
from agents.core.logger import get_agent_logger, log_execution_event
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.knowledge.knowledge_models import KnowledgeResult
from agents.knowledge.knowledge_service import KnowledgeService
from agents.recommendation.recommendation_models import RecommendationRecord
from agents.registry.registry import AgentRegistry
from agents.schemas.schemas import AgentMetadata, CapabilityFlags, ExecutionContext

logger = get_agent_logger("KnowledgeAgent")


class KnowledgeAgent(BaseAgent):
    """
    Production Knowledge Agent for NOC Copilot.

    Subscribes to 'recommendation.generated' events, invokes KnowledgeService to perform context retrieval
    and LLM inference, and emits 'knowledge.generated' events onto the EventBus.
    """

    def __init__(
        self,
        service: Optional[KnowledgeService] = None,
        metadata: Optional[AgentMetadata] = None,
        container: Optional[ServiceContainer] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        """
        Initialize KnowledgeAgent.

        Args:
            service: KnowledgeService instance.
            metadata: AgentMetadata instance.
            container: ServiceContainer instance.
            event_bus: EventBus instance.
        """
        agent_metadata = metadata or AgentMetadata(
            name="KnowledgeAgent",
            version="1.0.0",
            description="Synthesizes operational runbooks, LLM reasoning, and recommendation context into actionable knowledge.",
            author="NOC Copilot Core Team",
            dependencies=["RecommendationAgent"],
            tags=["knowledge", "llm", "analysis"],
            capabilities=CapabilityFlags(supports_cpu=True, supports_batch=True),
        )

        super().__init__(metadata=agent_metadata, container=container, event_bus=event_bus)
        self._service = service or KnowledgeService()
        self._recommendation_sub_id: Optional[str] = None
        self._setup_event_subscription()

    @property
    def service(self) -> KnowledgeService:
        """Knowledge service instance."""
        return self._service

    def _setup_event_subscription(self) -> None:
        """Subscribe to 'recommendation.generated' events on the EventBus."""
        if self.event_bus:
            self._recommendation_sub_id = self.event_bus.subscribe(
                topic="recommendation.generated",
                callback=self._handle_recommendation_event,
            )
            logger.info("KnowledgeAgent subscribed to 'recommendation.generated' events.")

    def _handle_recommendation_event(self, event: Event) -> None:
        """
        Event subscriber callback for 'recommendation.generated' events.

        Args:
            event: Published Recommendation Event object.
        """
        try:
            payload = event.payload or {}
            log_execution_event(
                logger,
                self.name,
                "EVENT_RECEIVED",
                f"KnowledgeAgent received recommendation event for '{payload.get('recommendation_id')}'.",
            )
            self.execute(payload)
        except Exception as e:
            logger.error(f"Error handling recommendation event in KnowledgeAgent: {e}", exc_info=True)

    def validate_input(self, input_data: Any) -> List[Dict[str, Any]]:
        """
        Validate execution input payload.

        Supports RecommendationRecord model, event payload dict, or list of recommendation payloads.
        """
        if input_data is None:
            return []

        if isinstance(input_data, RecommendationRecord):
            return [input_data.model_dump(mode="json")]

        if isinstance(input_data, Event):
            payload = input_data.payload or {}
            return [payload]

        if isinstance(input_data, list):
            validated: List[Dict[str, Any]] = []
            for item in input_data:
                if isinstance(item, RecommendationRecord):
                    validated.append(item.model_dump(mode="json"))
                elif isinstance(item, dict):
                    validated.append(item)
            return validated

        if isinstance(input_data, dict):
            return [input_data]

        return []

    def _execute_internal(
        self, input_data: List[Dict[str, Any]], context: Optional[ExecutionContext] = None
    ) -> List[KnowledgeResult]:
        """
        Execute knowledge synthesis logic, emit knowledge.generated events, and update context.

        Args:
            input_data: Validated list of recommendation payload dictionaries.
            context: Shared ExecutionContext.

        Returns:
            List of generated KnowledgeResult objects.
        """
        knowledge_results: List[KnowledgeResult] = []
        exec_id = context.context_id if context else str(uuid.uuid4())

        for rec_payload in input_data:
            try:
                result = self._service.generate_knowledge_for_recommendation(rec_payload)
                knowledge_results.append(result)

                if self.event_bus:
                    evt = Event(
                        event_type="knowledge.generated",
                        source=self.name,
                        payload=result.model_dump(mode="json"),
                        metadata={
                            "execution_id": exec_id,
                            "result_id": result.result_id,
                            "recommendation_id": result.recommendation_id,
                            "incident_id": result.incident_id,
                            "device_id": result.device_id,
                            "timestamp": str(result.created_at),
                        },
                    )
                    self.event_bus.publish(evt)

            except Exception as e:
                logger.error(f"Error generating knowledge result in KnowledgeAgent: {e}", exc_info=True)

        log_execution_event(
            logger,
            self.name,
            "KNOWLEDGE_GENERATED",
            f"KnowledgeAgent generated {len(knowledge_results)} knowledge result(s).",
        )

        # Update execution context
        if context:
            context.results[self.name] = [k.model_dump(mode="json") for k in knowledge_results]
            context.shared_state["latest_knowledge"] = {
                k.result_id: k.model_dump(mode="json") for k in knowledge_results
            }

        return knowledge_results

    def shutdown(self) -> None:
        """Unsubscribe event handlers and shutdown KnowledgeAgent."""
        if self.event_bus and self._recommendation_sub_id:
            self.event_bus.unsubscribe(self._recommendation_sub_id)
            self._recommendation_sub_id = None
        super().shutdown()


def register_knowledge_agent(registry: Optional[AgentRegistry] = None) -> KnowledgeAgent:
    """
    Convenience function to instantiate and register KnowledgeAgent with AgentRegistry.

    Args:
        registry: Target AgentRegistry (defaults to global instance).

    Returns:
        Registered KnowledgeAgent instance.
    """
    target_registry = registry or AgentRegistry.get_global()
    agent = KnowledgeAgent()
    target_registry.register(agent, allow_override=True)
    return agent
