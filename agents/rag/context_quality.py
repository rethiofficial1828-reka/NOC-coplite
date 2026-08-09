"""
Context Quality Engine Module.

Implements ContextQualityEvaluator to score coverage, completeness, freshness, diversity, and evidence sufficiency.
If context quality falls below threshold, reports insufficient evidence.
"""

from typing import List, Optional

from agents.core.logger import get_agent_logger
from agents.rag.interfaces import IContextQualityEvaluator
from agents.rag.models import (
    CAGContext,
    ContextQuality,
    ContextQualityStatus,
    RetrievalResult,
)

logger = get_agent_logger("ContextQuality")


class ContextQualityEvaluator(IContextQualityEvaluator):
    """
    Evaluates CAG context and retrieved knowledge chunks for evidence quality and completeness.
    """

    def __init__(self, min_quality_threshold: float = 0.40) -> None:
        self._min_quality_threshold = min_quality_threshold

    def evaluate_quality(
        self, context: CAGContext, retrieved_chunks: List[RetrievalResult]
    ) -> ContextQuality:
        """
        Evaluate completeness, relevance, diversity, and evidence sufficiency.

        Returns:
            ContextQuality model.
        """
        warnings: List[str] = []
        missing_fields: List[str] = []

        # 1. Completeness Score
        present_count = 0
        total_dimensions = 4  # Telemetry, Incident, Topology, Retrieved Knowledge

        if context.telemetry_data:
            present_count += 1
        else:
            missing_fields.append("telemetry")
            warnings.append("Missing live telemetry metrics.")

        if context.incident_data:
            present_count += 1
        else:
            missing_fields.append("incident")
            warnings.append("Missing incident record.")

        if context.topology_data:
            present_count += 1
        else:
            missing_fields.append("topology")
            warnings.append("Missing network topology context.")

        if retrieved_chunks:
            present_count += 1
        else:
            missing_fields.append("retrieved_knowledge")
            warnings.append("No relevant runbook chunks retrieved.")

        completeness_score = present_count / total_dimensions

        # 2. Relevance Score (mean score of top chunks)
        relevance_score = 0.5
        if retrieved_chunks:
            scores = [r.score for r in retrieved_chunks[:3]]
            relevance_score = sum(scores) / len(scores)

        # 3. Diversity Score (distinct document sources)
        diversity_score = 0.5
        if retrieved_chunks:
            distinct_sources = {r.chunk.source for r in retrieved_chunks}
            diversity_score = min(1.0, len(distinct_sources) / 3.0)

        # 4. Freshness Score
        freshness_score = 0.9

        # Composite Quality Score
        quality_score = (
            0.35 * completeness_score
            + 0.35 * relevance_score
            + 0.15 * diversity_score
            + 0.15 * freshness_score
        )

        is_sufficient = quality_score >= self._min_quality_threshold

        if quality_score >= 0.80:
            status = ContextQualityStatus.HIGH_QUALITY
        elif quality_score >= 0.60:
            status = ContextQualityStatus.ACCEPTABLE
        elif is_sufficient:
            status = ContextQualityStatus.DEGRADED
        else:
            status = ContextQualityStatus.INSUFFICIENT

        if not is_sufficient:
            warnings.append("Evidence quality below minimum threshold. LLM should report insufficient evidence.")

        logger.info(f"ContextQuality evaluated: score={quality_score:.2f}, status='{status.value}', sufficient={is_sufficient}.")

        return ContextQuality(
            quality_score=round(quality_score, 2),
            status=status,
            completeness_score=round(completeness_score, 2),
            freshness_score=round(freshness_score, 2),
            relevance_score=round(relevance_score, 2),
            diversity_score=round(diversity_score, 2),
            is_sufficient=is_sufficient,
            warnings=warnings,
            missing_fields=missing_fields,
        )
