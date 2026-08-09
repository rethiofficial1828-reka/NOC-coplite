"""
Dynamic Confidence Engine for Enterprise AI Reasoning Subsystem.

Calculates multi-factor confidence scores dynamically based on evidence quality,
completeness, cross-source agreement, prediction certainty, topology certainty,
validation scores, and contradiction penalties.
"""

import threading
from typing import Any, Dict, List, Optional

from agents.core.logger import get_agent_logger
from agents.reasoning.reasoning_models import (
    ConfidenceFactors,
    ConfidenceResult,
    Contradiction,
    Hypothesis,
    ReasoningEvidence,
    ValidationResult,
)

logger = get_agent_logger("ConfidenceEngine")


class ConfidenceEngine:
    """
    Thread-safe engine for dynamic multi-factor confidence computation.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def calculate_confidence(
        self,
        evidence_list: List[ReasoningEvidence],
        validation_results: List[ValidationResult],
        contradictions: List[Contradiction],
        hypotheses: List[Hypothesis],
    ) -> ConfidenceResult:
        """
        Calculate composite confidence metrics across evidence, validations, contradictions, and hypotheses.

        Returns:
            ConfidenceResult object.
        """
        with self._lock:
            # 1. Quality & Validation Score
            val_scores = [v.reliability_score * v.completeness_score for v in validation_results]
            evidence_quality = sum(val_scores) / len(val_scores) if val_scores else 1.0

            # 2. Freshness Score
            freshness_scores = [v.freshness_score for v in validation_results]
            avg_freshness = sum(freshness_scores) / len(freshness_scores) if freshness_scores else 1.0

            # 3. Completeness & Sufficiency
            evidence_types_present = set(e.evidence_type for e in evidence_list)
            desired_types = {"telemetry", "prediction", "incident", "recommendation", "topology", "knowledge"}
            completeness = len(evidence_types_present.intersection(desired_types)) / len(desired_types)

            # 4. Cross-Source Agreement
            agent_sources = set(e.source_agent for e in evidence_list)
            cross_agreement = min(1.0, len(agent_sources) / 4.0)

            # 5. Prediction Certainty
            pred_items = [e for e in evidence_list if "predict" in e.evidence_type or e.source_agent == "PredictionAgent"]
            pred_certainty = sum(e.confidence for e in pred_items) / len(pred_items) if pred_items else 0.85

            # 6. Topology Certainty
            top_items = [e for e in evidence_list if "topolog" in e.evidence_type or e.source_agent == "TopologyAgent"]
            top_certainty = sum(e.confidence for e in top_items) / len(top_items) if top_items else 0.90

            # 7. Contradiction Penalty
            total_penalty = sum(c.penalty_factor for c in contradictions)
            bounded_penalty = min(0.50, total_penalty)

            # Composite Factors
            factors = ConfidenceFactors(
                evidence_quality=round(evidence_quality, 2),
                evidence_completeness=round(completeness, 2),
                cross_source_agreement=round(cross_agreement, 2),
                prediction_certainty=round(pred_certainty, 2),
                topology_certainty=round(top_certainty, 2),
                retrieval_quality=0.85,
                validation_score=round(evidence_quality, 2),
                contradiction_penalty=round(bounded_penalty, 2),
                freshness=round(avg_freshness, 2),
            )

            # Calculate Raw Composite Overall Confidence
            base_score = (
                0.25 * factors.evidence_quality
                + 0.20 * factors.evidence_completeness
                + 0.20 * factors.cross_source_agreement
                + 0.15 * factors.prediction_certainty
                + 0.10 * factors.topology_certainty
                + 0.10 * factors.freshness
            )
            overall_confidence = max(0.10, min(1.0, base_score - factors.contradiction_penalty))

            # Per-Hypothesis Confidence Mapping
            per_hyp: Dict[str, float] = {}
            for h in hypotheses:
                h_score = (h.initial_likelihood * 0.5) + (h.coverage_score * 0.5)
                h_conf = max(0.05, min(1.0, (h_score * overall_confidence)))
                per_hyp[h.hypothesis_id] = round(h_conf, 2)

            res = ConfidenceResult(
                overall_confidence=round(overall_confidence, 2),
                per_hypothesis_confidence=per_hyp,
                evidence_sufficiency_score=round(completeness, 2),
                investigation_completeness_score=round(min(1.0, (len(evidence_list) / 5.0)), 2),
                factors=factors,
            )

            logger.info(
                f"ConfidenceEngine computed overall_confidence={res.overall_confidence:.2f} "
                f"(penalty={bounded_penalty:.2f}, completeness={res.investigation_completeness_score:.2f})"
            )
            return res
