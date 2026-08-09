"""
Confidence-Aware Handoff Engine for Enterprise Trust & Safe Autonomy Subsystem.

Determines handoff recommendation based on evidence quality, contradiction penalty,
adversarial verification, counterfactual support, and operational safety.
"""

import threading
from typing import Any, Dict, Optional

from agents.core.logger import get_agent_logger
from agents.trust.trust_models import (
    AdversarialResult,
    AutonomyDecision,
    BlastRadius,
    ConfidenceHandoff,
    CounterfactualResult,
    EvidenceRevalidation,
)

logger = get_agent_logger("ConfidenceHandoffEngine")


class ConfidenceHandoffEngine:
    """
    Thread-safe engine for evaluating confidence-aware operator handoff criteria.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def evaluate_handoff(
        self,
        decision: AutonomyDecision,
        confidence_score: float,
        evidence_revalidation: EvidenceRevalidation,
        adversarial_result: AdversarialResult,
        counterfactual_result: CounterfactualResult,
        blast_radius: BlastRadius,
    ) -> ConfidenceHandoff:
        """
        Synthesize confidence handoff assessment model.

        Returns:
            ConfidenceHandoff model.
        """
        with self._lock:
            penalty = adversarial_result.penalty_factor
            quality = evidence_revalidation.overall_quality_score

            if decision == AutonomyDecision.AUTO_ELIGIBLE:
                summary = (
                    f"Action is eligible for autonomous execution. High reasoning confidence ({confidence_score:.2f}), "
                    f"quality evidence ({quality:.2f}), passed adversarial probing, and low blast radius."
                )
            elif decision == AutonomyDecision.HUMAN_APPROVAL_REQUIRED:
                summary = (
                    f"Operator approval required before proceeding. Reasoning confidence is {confidence_score:.2f}, "
                    f"but potential action blast radius is {blast_radius.potential_action_level.value}."
                )
            elif decision == AutonomyDecision.ADDITIONAL_EVIDENCE_REQUIRED:
                summary = (
                    f"Additional evidence collection required. Reasoning confidence or evidence quality "
                    f"is insufficient ({confidence_score:.2f}) to make a definitive autonomy decision."
                )
            else:
                summary = (
                    f"Action is BLOCKED by safe autonomy policy. Adversarial verification failed or critical "
                    f"contradictions disproved the proposed root cause hypothesis."
                )

            handoff = ConfidenceHandoff(
                recommendation_id=None,
                handoff_decision=decision,
                confidence_score=round(confidence_score, 2),
                evidence_quality=round(quality, 2),
                contradiction_penalty=round(penalty, 2),
                reasoning_summary=summary,
            )

            logger.info(f"ConfidenceHandoffEngine decision: {decision.value} - '{summary}'")
            return handoff
