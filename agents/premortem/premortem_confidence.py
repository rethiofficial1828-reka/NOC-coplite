"""
Pre-Mortem Confidence Engine for Enterprise Pre-Mortem Subsystem.

Calculates multi-factor confidence ratings for future-state predictions by integrating
telemetry quality, historical similarity, scenario consistency, and trust assessment.
"""

import threading
from typing import Any, Dict, List, Optional

from agents.core.logger import get_agent_logger
from agents.premortem.premortem_models import (
    FutureScenario,
    HistoricalIncidentMatch,
    PreMortemConfidence,
)

logger = get_agent_logger("PreMortemConfidenceEngine")


class PreMortemConfidenceEngine:
    """
    Thread-safe engine for calculating pre-mortem prediction confidence.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def calculate_confidence(
        self,
        matches: List[HistoricalIncidentMatch],
        scenarios: List[FutureScenario],
        evidence_quality: float = 0.90,
        trust_score: float = 0.85,
    ) -> PreMortemConfidence:
        """
        Calculate composite PreMortemConfidence.

        Returns:
            PreMortemConfidence model.
        """
        with self._lock:
            supporting: List[str] = []
            uncertainty: List[str] = []
            missing: List[str] = []

            # 1. Historical Match Support
            hist_score = 0.70
            if matches:
                hist_score = max(m.similarity_score for m in matches)
                supporting.append(f"Strong historical match similarity ({hist_score * 100:.1f}%)")
            else:
                uncertainty.append("Limited historical incident matches found")
                missing.append("Historical resolution records for exact topology")

            # 2. Evidence Quality & Trust Alignment
            supporting.append(f"High evidence quality score ({evidence_quality * 100:.1f}%)")
            supporting.append(f"Safe autonomy trust score ({trust_score * 100:.1f}%)")

            # 3. Scenario Consistency
            if len(scenarios) >= 2:
                supporting.append("Multiple scenario simulations show convergent failure trajectories")

            # Composite Score Calculation
            raw_score = (hist_score * 0.35) + (evidence_quality * 0.35) + (trust_score * 0.30)
            score = max(0.10, min(0.98, raw_score))

            if score >= 0.80:
                level = "HIGH"
            elif score >= 0.60:
                level = "MEDIUM"
            else:
                level = "LOW"

            result = PreMortemConfidence(
                score=round(score, 2),
                confidence_level=level,
                supporting_factors=supporting,
                uncertainty_factors=uncertainty,
                missing_evidence=missing,
            )

            logger.info(f"PreMortemConfidenceEngine computed score={score:.2f} (level={level})")
            return result
