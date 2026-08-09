"""
Knowledge Service Module.

Business logic service for orchestrating context retrieval, prompt construction,
LLM provider execution, validation, caching, and persistence of KnowledgeResults.
"""

from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List, Optional, Union

from agents.core.logger import get_agent_logger
from agents.knowledge.knowledge_cache import KnowledgeCache
from agents.knowledge.knowledge_models import KnowledgeResult, KnowledgeStatistics
from agents.knowledge.knowledge_prompt_builder import KnowledgePromptBuilder
from agents.knowledge.knowledge_repository import KnowledgeRepository
from agents.knowledge.knowledge_validator import KnowledgeValidator
from agents.knowledge.llm_provider import LLMProvider
from agents.knowledge.mock_provider import MockProvider
from agents.knowledge.provider_factory import ProviderFactory
from agents.recommendation.recommendation_models import RecommendationRecord

logger = get_agent_logger("KnowledgeService")


class KnowledgeService:
    """
    Business service layer managing prompt construction, LLM inference, caching, and result storage.
    """

    def __init__(
        self,
        provider: Optional[LLMProvider] = None,
        repository: Optional[KnowledgeRepository] = None,
        validator: Optional[KnowledgeValidator] = None,
        prompt_builder: Optional[KnowledgePromptBuilder] = None,
        cache: Optional[KnowledgeCache] = None,
        rag_service: Optional[Any] = None,
    ) -> None:
        """
        Initialize KnowledgeService.

        Args:
            provider: LLMProvider instance (defaults to ProviderFactory.create_provider()).
            repository: KnowledgeRepository instance.
            validator: KnowledgeValidator instance.
            prompt_builder: KnowledgePromptBuilder instance.
            cache: KnowledgeCache instance.
            rag_service: Optional RAGService instance for enterprise CAG + RAG.
        """
        self._provider = provider or ProviderFactory.create_provider()
        self._repository = repository or KnowledgeRepository()
        self._validator = validator or KnowledgeValidator()
        self._prompt_builder = prompt_builder or KnowledgePromptBuilder()
        self._cache = cache or KnowledgeCache()
        self._rag_service = rag_service

        # Initialize provider
        self._provider.initialize()

    @property
    def rag_service(self) -> Optional[Any]:
        """RAG Service instance."""
        return self._rag_service

    @property
    def provider(self) -> LLMProvider:
        """LLM provider instance."""
        return self._provider

    @property
    def repository(self) -> KnowledgeRepository:
        """Repository instance."""
        return self._repository

    @property
    def cache(self) -> KnowledgeCache:
        """Cache instance."""
        return self._cache

    def parse_llm_response(self, text: str) -> Dict[str, Any]:
        """
        Parse raw LLM response text into structured root cause, steps, and confidence metrics.

        Args:
            text: Raw generated response text.

        Returns:
            Dict containing parsed fields.
        """
        root_cause = ""
        steps: List[str] = []
        confidence = 0.85

        lines = text.splitlines()
        current_section = ""

        for line in lines:
            line_str = line.strip()
            if line_str.startswith("ROOT CAUSE ANALYSIS:"):
                current_section = "root_cause"
                continue
            elif line_str.startswith("RECOMMENDED ACTIONS:"):
                current_section = "steps"
                continue
            elif line_str.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line_str.split(":")[1].strip())
                    confidence = max(0.0, min(1.0, confidence))
                except Exception:
                    pass
                continue

            if current_section == "root_cause" and line_str:
                root_cause += (" " + line_str) if root_cause else line_str
            elif current_section == "steps" and line_str:
                if line_str.startswith(("1.", "2.", "3.", "4.", "5.", "•", "-")):
                    steps.append(line_str.lstrip("1234567890.•- "))
                else:
                    steps.append(line_str)

        if not root_cause:
            root_cause = "Predictive telemetry anomaly indicates potential resource degradation."
        if not steps:
            steps = ["Inspect interface status", "Verify QoS policy limits", "Check WAN router logs"]

        return {
            "root_cause_analysis": root_cause.strip(),
            "recommended_steps": steps,
            "confidence_score": confidence,
        }

    def generate_knowledge_for_recommendation(
        self, recommendation_data: Union[RecommendationRecord, Dict[str, Any]]
    ) -> KnowledgeResult:
        """
        Generate KnowledgeResult for a recommendation record or payload.

        Args:
            recommendation_data: RecommendationRecord instance or dictionary payload.

        Returns:
            Generated KnowledgeResult model instance.
        """
        if isinstance(recommendation_data, RecommendationRecord):
            rec_dict = recommendation_data.model_dump(mode="json")
        else:
            rec_dict = dict(recommendation_data)

        self._validator.validate_recommendation_payload(rec_dict)

        rec_id = str(rec_dict["recommendation_id"])
        inc_id = str(rec_dict["incident_id"])
        device_id = str(rec_dict.get("device_id") or rec_dict.get("interface"))

        # Check Cache
        cache_key = f"rec_{rec_id}"
        cached_result = self._cache.get(cache_key)
        if cached_result:
            logger.info(f"Knowledge cache hit for recommendation '{rec_id}'.")
            return cached_result

        # Check Repository
        existing_res = self._repository.find_by_recommendation(rec_id)
        if existing_res:
            self._cache.set(cache_key, existing_res)
            logger.info(f"Retrieved stored knowledge result for recommendation '{rec_id}'.")
            return existing_res

        # Retrieve context documents
        topology = self._repository.retrieve_topology(device_id)
        incident_type = str(rec_dict.get("metadata", {}).get("incident_type", "NETWORK_CONGESTION"))
        runbooks = self._repository.retrieve_runbooks(incident_type)

        # Extract TopologyAnalysis if embedded in recommendation metadata
        # (populated when TopologyAgent runs before KnowledgeAgent in the chain)
        topology_analysis: Optional[Dict[str, Any]] = rec_dict.get("metadata", {}).get(
            "topology_analysis"
        )

        # Build Prompt
        incident_info = {
            "incident_id": inc_id,
            "title": rec_dict.get("summary", "Incident Triage"),
            "severity": rec_dict.get("priority", "MEDIUM"),
            "risk_score": float(rec_dict.get("metadata", {}).get("risk_score", 0.75)),
            "contributing_signals": rec_dict.get("recommended_actions", []),
        }
        prompt_text = self._prompt_builder.build_prompt(
            incident_info,
            rec_dict,
            topology,
            runbooks,
            topology_analysis=topology_analysis,
        )

        # Call LLM Provider
        raw_completion = self._provider.generate(prompt_text)
        parsed = self.parse_llm_response(raw_completion)

        result_id = self._repository.generate_next_id()
        query_id = str(uuid.uuid4())

        knowledge_result = KnowledgeResult(
            result_id=result_id,
            query_id=query_id,
            recommendation_id=rec_id,
            incident_id=inc_id,
            device_id=device_id,
            generated_explanation=raw_completion,
            root_cause_analysis=parsed["root_cause_analysis"],
            recommended_steps=parsed["recommended_steps"],
            confidence_score=parsed["confidence_score"],
            cited_sources=[rb["source"] for rb in runbooks if "source" in rb],
            created_at=datetime.now(timezone.utc),
            provider_metadata=self._provider.metadata(),
        )

        self._validator.validate_knowledge_result(knowledge_result)
        self._repository.save_knowledge_result(knowledge_result)
        self._cache.set(cache_key, knowledge_result)

        logger.info(f"Generated new knowledge result '{result_id}' for recommendation '{rec_id}'.")
        return knowledge_result

    def generate_knowledge_with_topology(
        self,
        recommendation_data: "Union[RecommendationRecord, Dict[str, Any]]",
        topology_analysis: Optional["Dict[str, Any]"] = None,
    ) -> "KnowledgeResult":
        """
        Generate a KnowledgeResult with an explicitly supplied TopologyAnalysis.

        This method is the primary integration point for the TopologyAgent → KnowledgeAgent
        handoff.  When *topology_analysis* is not None it is injected into the LLM prompt
        via build_topology_section, providing graph-level context.

        If *topology_analysis* is None the method falls back to the standard
        generate_knowledge_for_recommendation behaviour.

        Args:
            recommendation_data: RecommendationRecord or dict payload.
            topology_analysis: TopologyAnalysis.model_dump(mode='json') dict or None.

        Returns:
            Generated KnowledgeResult model instance.
        """
        if topology_analysis is not None:
            # Embed the topology analysis into the recommendation metadata so that
            # generate_knowledge_for_recommendation can pick it up transparently.
            if isinstance(recommendation_data, RecommendationRecord):
                rec_dict = recommendation_data.model_dump(mode="json")
            else:
                rec_dict = dict(recommendation_data)

            meta = dict(rec_dict.get("metadata") or {})
            meta["topology_analysis"] = topology_analysis
            rec_dict["metadata"] = meta

            return self.generate_knowledge_for_recommendation(rec_dict)

        return self.generate_knowledge_for_recommendation(recommendation_data)

    def get_statistics(self) -> KnowledgeStatistics:
        """Retrieve aggregated knowledge statistics."""
        return self._repository.get_statistics()
