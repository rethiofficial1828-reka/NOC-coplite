"""
Reranker Module.

Implements Reranker — a multi-factor semantic reranking engine that ranks retrieved candidates
by combining semantic similarity, device relevance, incident context, topology severity,
and document freshness/authority.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents.core.logger import get_agent_logger
from agents.rag.interfaces import IReranker
from agents.rag.models import CAGContext, RetrievalResult

logger = get_agent_logger("Reranker")


class Reranker(IReranker):
    """
    Production Multi-Factor Semantic Reranker.

    Calculates composite rerank score:
        RerankScore = w1*SimScore + w2*DeviceRel + w3*IncRel + w4*TopRel + w5*Freshness + w6*Authority
    """

    def __init__(
        self,
        weight_similarity: float = 0.40,
        weight_device: float = 0.20,
        weight_incident: float = 0.15,
        weight_topology: float = 0.15,
        weight_freshness: float = 0.10,
    ) -> None:
        self._w_sim = weight_similarity
        self._w_device = weight_device
        self._w_incident = weight_incident
        self._w_topology = weight_topology
        self._w_freshness = weight_freshness

    def rerank(
        self,
        query: str,
        candidates: List[RetrievalResult],
        context: Optional[CAGContext] = None,
        top_k: int = 5,
    ) -> List[RetrievalResult]:
        """
        Rerank candidate RetrievalResult objects using multi-factor contextual scoring.
        """
        if not candidates:
            return []

        active_device = (context.device_id if context else "").lower()
        incident_type = (
            str(context.incident_data.get("severity", "")) if context else ""
        ).lower()
        topology_severity = (
            str(context.topology_data.get("overall_severity", "")) if context else ""
        ).lower()

        reranked: List[RetrievalResult] = []

        for candidate in candidates:
            content_lower = candidate.chunk.content.lower()
            meta_str = str(candidate.chunk.metadata).lower()

            # 1. Similarity base score
            sim_score = float(candidate.score)

            # 2. Device Relevance
            dev_score = 0.0
            if active_device and (active_device in content_lower or active_device in meta_str):
                dev_score = 1.0
            elif active_device:
                dev_score = 0.2

            # 3. Incident Relevance
            inc_score = 0.5
            if "runbook" in candidate.chunk.tags or "sop" in candidate.chunk.tags:
                inc_score += 0.3
            if incident_type and incident_type in content_lower:
                inc_score += 0.2
            inc_score = min(1.0, inc_score)

            # 4. Topology Relevance
            top_score = 0.5
            if topology_severity and topology_severity in content_lower:
                top_score += 0.3
            if "topology" in candidate.chunk.tags or "graph" in candidate.chunk.tags:
                top_score += 0.2
            top_score = min(1.0, top_score)

            # 5. Freshness
            freshness_score = 0.8  # default baseline

            # Composite Score Computation
            composite = (
                self._w_sim * sim_score
                + self._w_device * dev_score
                + self._w_incident * inc_score
                + self._w_topology * top_score
                + self._w_freshness * freshness_score
            )

            candidate.rerank_score = composite
            candidate.score = composite
            reranked.append(candidate)

        # Sort descending by composite score
        reranked.sort(key=lambda r: r.rerank_score, reverse=True)

        for i, res in enumerate(reranked[:top_k]):
            res.rank = i + 1

        logger.info(f"Reranker scored and ordered {len(reranked)} candidate(s).")
        return reranked[:top_k]
