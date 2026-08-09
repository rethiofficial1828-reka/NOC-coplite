"""
Reasoning Service for Enterprise AI Reasoning Subsystem.

Coordinates evidence correlation, hypothesis generation, validation, contradiction detection,
dynamic confidence computation, root cause ranking, and conclusion generation.
"""

from datetime import datetime, timezone
import time
import threading
from typing import Any, Dict, List, Optional
import uuid

from agents.core.logger import get_agent_logger
from agents.orchestrator_ai.investigation_context import InvestigationContext
from agents.reasoning.confidence_engine import ConfidenceEngine
from agents.reasoning.contradiction_detector import ContradictionDetector
from agents.reasoning.evidence_correlator import EvidenceCorrelator
from agents.reasoning.evidence_validator import EvidenceValidator
from agents.reasoning.hypothesis_generator import HypothesisGenerator
from agents.reasoning.reasoning_models import (
    InvestigationConclusion,
    ReasoningResult,
    ReasoningStatistics,
)
from agents.reasoning.root_cause_ranker import RootCauseRanker

logger = get_agent_logger("ReasoningService")


class ReasoningService:
    """
    Domain service coordinating the Enterprise AI Reasoning pipeline.
    """

    def __init__(
        self,
        correlator: Optional[EvidenceCorrelator] = None,
        hypothesis_generator: Optional[HypothesisGenerator] = None,
        contradiction_detector: Optional[ContradictionDetector] = None,
        validator: Optional[EvidenceValidator] = None,
        confidence_engine: Optional[ConfidenceEngine] = None,
        ranker: Optional[RootCauseRanker] = None,
    ) -> None:
        self._correlator = correlator or EvidenceCorrelator()
        self._hypothesis_generator = hypothesis_generator or HypothesisGenerator()
        self._contradiction_detector = contradiction_detector or ContradictionDetector()
        self._validator = validator or EvidenceValidator()
        self._confidence_engine = confidence_engine or ConfidenceEngine()
        self._ranker = ranker or RootCauseRanker()
        self._lock = threading.RLock()

    def process_reasoning(self, context: InvestigationContext) -> ReasoningResult:
        """
        Execute full reasoning pipeline over an InvestigationContext.

        Returns:
            ReasoningResult containing InvestigationConclusion and evidence correlation.
        """
        with self._lock:
            start_time = time.perf_counter()
            req = context.request

            # Step 1: Evidence Correlation & Grouping
            correlation = self._correlator.correlate(context=context)

            # Reconstruct list of normalized evidence
            evidence_list = []
            if context.evidence_registry:
                for ref in context.evidence_registry.get_all():
                    evidence_list.append(self._correlator._convert_reference(ref))

            # Step 2: Validate Evidence Freshness & Completeness
            validation_results = self._validator.validate_evidence_list(evidence_list)

            # Step 3: Generate Competing Hypotheses
            hypotheses = self._hypothesis_generator.generate_hypotheses(
                correlation=correlation,
                evidence_list=evidence_list,
                query_hint=req.operator_query,
            )

            # Step 4: Detect Contradictions & Signal Conflicts
            contradictions = self._contradiction_detector.detect_contradictions(evidence_list)

            # Step 5: Compute Dynamic Composite Confidence
            confidence_result = self._confidence_engine.calculate_confidence(
                evidence_list=evidence_list,
                validation_results=validation_results,
                contradictions=contradictions,
                hypotheses=hypotheses,
            )

            # Step 6: Rank Root Causes & Generate Explainable Explanation
            ranked_root_causes = self._ranker.rank_root_causes(
                hypotheses=hypotheses,
                evidence_list=evidence_list,
                contradictions=contradictions,
                confidence_result=confidence_result,
            )

            explanation = self._ranker.generate_explanation(
                ranked_causes=ranked_root_causes,
                contradictions=contradictions,
                confidence_result=confidence_result,
                query=req.operator_query,
            )

            # Step 7: Formulate Final Conclusion
            primary_rc = ranked_root_causes[0].root_cause if ranked_root_causes else None

            conclusion = InvestigationConclusion(
                conclusion_id=str(uuid.uuid4()),
                request_id=req.request_id,
                primary_root_cause=primary_rc,
                ranked_root_causes=ranked_root_causes,
                ranked_hypotheses=hypotheses,
                contradictions=contradictions,
                confidence_result=confidence_result,
                explanation=explanation,
                created_at=datetime.now(timezone.utc),
            )

            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            stats = ReasoningStatistics(
                evidence_processed=len(evidence_list),
                hypotheses_evaluated=len(hypotheses),
                contradictions_found=len(contradictions),
                processing_duration_ms=elapsed_ms,
            )

            result = ReasoningResult(
                reasoning_id=str(uuid.uuid4()),
                request_id=req.request_id,
                conclusion=conclusion,
                correlation=correlation,
                statistics=stats,
                created_at=datetime.now(timezone.utc),
            )

            logger.info(
                f"ReasoningService completed analysis for request '{req.request_id}' "
                f"in {elapsed_ms:.2f}ms (primary='{primary_rc.title if primary_rc else 'None'}', "
                f"confidence={confidence_result.overall_confidence:.2f})"
            )
            return result
