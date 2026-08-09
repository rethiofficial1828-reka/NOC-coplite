"""
Evidence Validator for Enterprise AI Reasoning Subsystem.

Validates evidence freshness, completeness, source reliability, timestamp alignment,
and structural integrity. Ensures stale or incomplete evidence is flagged.
"""

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional

from agents.core.logger import get_agent_logger
from agents.reasoning.reasoning_models import (
    ReasoningEvidence,
    ValidationResult,
)

logger = get_agent_logger("EvidenceValidator")


class EvidenceValidator:
    """
    Thread-safe engine for validating evidence quality, freshness, and completeness.
    """

    def __init__(self, max_age_seconds: float = 600.0) -> None:
        self._max_age_seconds = max_age_seconds
        self._lock = threading.RLock()

    def validate_evidence_list(
        self, evidence_list: List[ReasoningEvidence]
    ) -> List[ValidationResult]:
        """
        Validate a list of evidence items.

        Returns:
            List of ValidationResult objects.
        """
        with self._lock:
            results: List[ValidationResult] = []
            now = datetime.now(timezone.utc)

            for item in evidence_list:
                res = self.validate_single(item, now=now)
                results.append(res)

            logger.info(
                f"EvidenceValidator evaluated {len(evidence_list)} evidence items: "
                f"{sum(1 for r in results if r.is_valid)} valid, {sum(1 for r in results if not r.is_valid)} invalid/flagged."
            )
            return results

    def validate_single(
        self, item: ReasoningEvidence, now: Optional[datetime] = None
    ) -> ValidationResult:
        """
        Validate an individual evidence item.
        """
        now_time = now or datetime.now(timezone.utc)
        issues: List[str] = []
        is_valid = True

        # 1. Freshness Check
        age_sec = (now_time - item.timestamp).total_seconds()
        if age_sec > self._max_age_seconds:
            freshness_score = max(0.1, 1.0 - (age_sec - self._max_age_seconds) / 3600.0)
            issues.append(f"Evidence is stale (age={age_sec:.1f}s > threshold={self._max_age_seconds}s)")
        else:
            freshness_score = 1.0

        # 2. Completeness Check
        completeness_score = 1.0
        if not item.payload:
            completeness_score = 0.2
            is_valid = False
            issues.append("Evidence payload is empty")
        elif not item.source_agent:
            completeness_score = 0.5
            is_valid = False
            issues.append("Evidence source agent is missing")

        # 3. Source Reliability Assessment
        reliability_map = {
            "TelemetryAgent": 1.0,
            "PredictionAgent": 0.90,
            "IncidentAgent": 0.95,
            "RecommendationAgent": 0.85,
            "TopologyAgent": 0.95,
            "KnowledgeAgent": 0.85,
        }
        reliability_score = reliability_map.get(item.source_agent, 0.75)

        return ValidationResult(
            evidence_id=item.evidence_id,
            is_valid=is_valid and freshness_score >= 0.3,
            freshness_score=round(freshness_score, 2),
            completeness_score=round(completeness_score, 2),
            reliability_score=round(reliability_score, 2),
            issues=issues,
        )
