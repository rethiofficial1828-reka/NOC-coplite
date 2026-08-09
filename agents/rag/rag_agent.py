"""
Production RAG Agent Implementation.

Subclasses BaseAgent to orchestrate Context-Augmented Generation (CAG) state assembly,
Hybrid Retrieval, Semantic Reranking, Quality Evaluation, and Prompt Package construction.
Publishes granular sub-step events onto the EventBus and populates ExecutionContext.
"""

from typing import Any, Dict, List, Optional
import uuid

from agents.base.base_agent import BaseAgent
from agents.core.container import ServiceContainer
from agents.core.logger import get_agent_logger, log_execution_event
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.rag.models import ContextPackage, PromptPackage, RAGResult
from agents.rag.rag_service import RAGService
from agents.registry.registry import AgentRegistry
from agents.schemas.schemas import AgentMetadata, CapabilityFlags, ExecutionContext

logger = get_agent_logger("RAGAgent")


class RAGAgent(BaseAgent):
    """
    Production RAG Agent for NOC Copilot.

    Subscribes to 'knowledge.requested' and 'rag.requested' events, invokes RAGService
    to aggregate CAG context, execute hybrid retrieval and reranking, and publishes
    'rag.context.ready' events with the assembled ContextPackage.
    """

    def __init__(
        self,
        service: Optional[RAGService] = None,
        metadata: Optional[AgentMetadata] = None,
        container: Optional[ServiceContainer] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        agent_metadata = metadata or AgentMetadata(
            name="RAGAgent",
            version="1.0.0",
            description=(
                "Orchestrates Context-Augmented Generation (CAG), Hybrid Retrieval, "
                "Semantic Reranking, and Enterprise Prompt Assembly."
            ),
            author="NOC Copilot Core Team",
            dependencies=["TopologyAgent", "RecommendationAgent"],
            tags=["rag", "retrieval", "knowledge", "context"],
            capabilities=CapabilityFlags(supports_cpu=True, supports_batch=True),
        )

        super().__init__(metadata=agent_metadata, container=container, event_bus=event_bus)
        self._service = service or RAGService()
        self._sub_ids: List[str] = []
        self._setup_event_subscriptions()

    @property
    def service(self) -> RAGService:
        """RAG service instance."""
        return self._service

    def _setup_event_subscriptions(self) -> None:
        """Subscribe to 'knowledge.requested' and 'rag.requested' events."""
        if self.event_bus:
            for topic in ("knowledge.requested", "rag.requested"):
                sub_id = self.event_bus.subscribe(topic=topic, callback=self._handle_request_event)
                self._sub_ids.append(sub_id)
            logger.info("RAGAgent subscribed to 'knowledge.requested' and 'rag.requested' events.")

    def _handle_request_event(self, event: Event) -> None:
        """Callback for incoming RAG/Knowledge request events."""
        try:
            payload = event.payload or {}
            query = payload.get("query") or payload.get("prompt", "")
            device_id = payload.get("device_id", "")

            # Execute pipeline
            context_pkg = self._service.build_context_package(query=query, device_id=device_id)
            prompt_pkg = self._service.assemble_prompt_package(context_pkg)

            # Publish Event
            if self.event_bus:
                evt = Event(
                    event_type="rag.context.ready",
                    source=self.name,
                    payload={
                        "query": query,
                        "device_id": context_pkg.cag_context.device_id,
                        "prompt_text": prompt_pkg.assembled_prompt,
                        "citations": [c.model_dump(mode="json") for c in prompt_pkg.citations],
                        "quality_score": context_pkg.quality.quality_score,
                    },
                )
                self.event_bus.publish(evt)

        except Exception as e:
            logger.error(f"RAGAgent failed to handle event '{event.event_type}': {e}", exc_info=True)

    def validate_input(self, input_data: Any) -> List[Dict[str, Any]]:
        """Validate input payload into list of request dicts."""
        if isinstance(input_data, dict):
            return [input_data]
        if isinstance(input_data, list):
            validated: List[Dict[str, Any]] = []
            for item in input_data:
                if isinstance(item, dict):
                    validated.append(item)
                elif isinstance(item, str):
                    validated.append({"query": item})
                else:
                    raise TypeError(f"RAGAgent expects dict or str items, got {type(item).__name__}")
            return validated
        raise TypeError(f"RAGAgent.validate_input expects dict or list, got {type(input_data).__name__}")

    def _execute_internal(
        self,
        input_data: List[Dict[str, Any]],
        context: Optional[ExecutionContext] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute CAG context assembly and RAG retrieval, returning list of ContextPackages as dicts.
        """
        results: List[Dict[str, Any]] = []

        # Emit context.build.started
        self._publish_status_event("context.build.started", {"requests_count": len(input_data)})

        for req in input_data:
            query = req.get("query", "")
            device_id = req.get("device_id", "")

            # 1. Retrieval started
            self._publish_status_event("retrieval.started", {"query": query, "device_id": device_id})

            pkg = self._service.build_context_package(
                query=query, device_id=device_id, execution_context=context
            )

            # 2. Reranking & Quality completed
            self._publish_status_event("reranking.completed", {"chunks_count": len(pkg.retrieved_results)})
            self._publish_status_event("context.quality.completed", {"quality_score": pkg.quality.quality_score})

            # 3. Prompt Assembly
            prompt_pkg = self._service.assemble_prompt_package(pkg)
            self._publish_status_event("prompt.assembled", {"token_count": prompt_pkg.token_count_estimated})

            res_dict = {
                "package_id": pkg.package_id,
                "cag_context": pkg.cag_context.model_dump(mode="json"),
                "prompt_text": prompt_pkg.assembled_prompt,
                "citations": [c.model_dump(mode="json") for c in prompt_pkg.citations],
                "quality": pkg.quality.model_dump(mode="json"),
            }
            results.append(res_dict)

            # 4. Context Ready & RAG Completed Events
            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        event_type="rag.context.ready",
                        source=self.name,
                        payload=res_dict,
                    )
                )

        self._publish_status_event("rag.completed", {"results_count": len(results)})

        log_execution_event(
            logger,
            self.name,
            "RAG_CONTEXT_COMPLETED",
            f"RAGAgent assembled {len(results)} context package(s).",
        )

        # Update ExecutionContext
        if context:
            context.results[self.name] = results
            context.shared_state["latest_rag_context"] = results[0] if results else {}

        return results

    def _publish_status_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Helper to publish sub-step progress events onto EventBus."""
        if self.event_bus:
            evt = Event(event_type=event_type, source=self.name, payload=payload)
            self.event_bus.publish(evt)

    def shutdown(self) -> None:
        """Unsubscribe handlers and shutdown RAGAgent."""
        if self.event_bus:
            for sub_id in self._sub_ids:
                self.event_bus.unsubscribe(sub_id)
            self._sub_ids.clear()
        super().shutdown()


def register_rag_agent(registry: Optional[AgentRegistry] = None) -> RAGAgent:
    """Convenience helper to instantiate and register RAGAgent with AgentRegistry."""
    target_registry = registry or AgentRegistry.get_global()
    agent = RAGAgent()
    target_registry.register(agent, allow_override=True)
    return agent
