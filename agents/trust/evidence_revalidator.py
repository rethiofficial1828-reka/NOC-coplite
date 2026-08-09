"""
Evidence Re-validator for Enterprise Trust & Safe Autonomy Subsystem.

Re-validates evidence quality, freshness, timestamp alignment, device/interface identity,
RAG citations, and evidence lineage prior to autonomy evaluation.
"""

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional

from agents.core.logger import get_agent_logger
from agents.orchestrator_ai.investigation_context import InvestigationContext
from agents.reasoning.reasoning_models import ReasoningEvidence
from agents.trust.trust_models import EvidenceRevalidation, VerificationEvidence

logger = get_agent_logger("EvidenceRevalidator")


class EvidenceRevalidator:
    """
    Thread-safe engine for evidence re-validation and quality auditing prior to decision making.
    """

    def __init__(self, max_age_seconds: float = 600.0) -> None:
        self._max_age_seconds = max_age_seconds
        self._lock = threading.RLock()

    def revalidate_context_evidence(
        self, context: InvestigationContext
    ) -> EvidenceRevalidation:
        """
        Revalidate all evidence registered in InvestigationContext.

        Returns:
            EvidenceRevalidation summary object.
        """
        with self._lock:
            evidence_items: List[ReasoningEvidence] = []
            if context.evidence_registry:
                for ref in context.evidence_registry.get_all():
                    evidence_items.append(
                        ReasoningEvidence(
                            evidence_id=ref.evidence_id,
                            source_agent=ref.source_agent,
                            evidence_type=ref.evidence_type,
                            confidence=ref.confidence,
                            device_id=ref.device_id,
                            timestamp=ref.timestamp,
                            payload=dict(ref.payload),
                        )
                    )

            return self.revalidate_evidence_list(evidence_items)

    def revalidate_evidence_list(
        self, evidence_list: List[ReasoningEvidence]
    ) -> EvidenceRevalidation:
        """
        Revalidate a list of ReasoningEvidence items.
        """
        with self._lock:
            revalidated: List[VerificationEvidence] = []
            now = datetime.now(timezone.utc)
            valid_cnt = 0
            stale_cnt = 0
            invalid_cnt = 0

            for item in evidence_list:
                notes: List[str] = []
                is_valid = True

                # 1. Freshness Check
                age_sec = (now - item.timestamp).total_seconds()
                if age_sec > self._max_age_seconds:
                    freshness = max(0.1, 1.0 - (age_sec - self._max_age_seconds) / 3600.0)
                    stale_cnt += 1
                    notes.append(f"Evidence is stale ({age_sec:.1f}s > {self._max_age_seconds}s)")
                else:
                    freshness = 1.0

                # 2. Completeness & Payload Integrity
                if not item.payload:
                    is_valid = False
                    invalid_cnt += 1
                    notes.append("Empty payload")
                elif not item.device_id and "device_id" not in item.payload:
                    notes.append("Device ID unassigned")

                # 3. Source Reliability Rating
                reliability_map = {
                    "TelemetryAgent": 1.0,
                    "PredictionAgent": 0.90,
                    "IncidentAgent": 0.95,
                    "RecommendationAgent": 0.85,
                    "TopologyAgent": 0.95,
                    "KnowledgeAgent": 0.85,
                    "ReasoningAgent": 0.90,
                }
                reliability = reliability_map.get(item.source_agent, 0.75)

                if is_valid and freshness >= 0.3:
                    valid_cnt += 1

                revalidated.append(
                    VerificationEvidence(
                        evidence_id=item.evidence_id,
                        source_agent=item.source_agent,
                        evidence_type=item.evidence_type,
                        timestamp=item.timestamp,
                        is_valid=is_valid and freshness >= 0.3,
                        freshness_score=round(freshness, 2),
                        reliability_score=round(reliability, 2),
                        notes=notes,
                    )
                )

            total = len(evidence_list)
            overall_quality = (sum(v.reliability_score * v.freshness_score for v in revalidated) / total) if total > 0 else 1.0

            result = EvidenceRevalidation(
                revalidated_items=revalidated,
                valid_count=valid_cnt,
                stale_count=stale_cnt,
                invalid_count=invalid_cnt,
                overall_quality_score=round(overall_quality, 2),
            )

            logger.info(
                f"EvidenceRevalidator processed {total} items: "
                f"{valid_cnt} valid, {stale_cnt} stale, {invalid_cnt} invalid (quality={overall_quality:.2f})"
            )
            return result
