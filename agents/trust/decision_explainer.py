"""
Decision Explainer for Enterprise Trust & Safe Autonomy Subsystem.

Synthesizes structured, auditable explanations for final trust and autonomy decisions
without exposing internal chain-of-thought.
"""

import threading
from typing import Any, Dict, List, Optional

from agents.core.logger import get_agent_logger
from agents.reasoning.reasoning_models import ReasoningResult, RootCause
from agents.trust.trust_models import (
    AdversarialResult,
    AutonomyDecision,
    BlastRadius,
    BlastRadiusLevel,
    CounterfactualResult,
    DecisionExplanation,
    EvidenceRevalidation,
    TrustScore,
)

logger = get_agent_logger("DecisionExplainer")


class DecisionExplainer:
    """
    Thread-safe engine for constructing auditable decision explanations.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def generate_explanation(
        self,
        decision: AutonomyDecision,
        reasoning_result: ReasoningResult,
        trust_score: TrustScore,
        adversarial_result: AdversarialResult,
        counterfactual_result: CounterfactualResult,
        blast_radius: BlastRadius,
        revalidation: EvidenceRevalidation,
    ) -> DecisionExplanation:
        """
        Synthesize concise, auditable DecisionExplanation model.

        Returns:
            DecisionExplanation model.
        """
        with self._lock:
            primary_cause: Optional[RootCause] = reasoning_result.conclusion.primary_root_cause
            top_title = primary_cause.title if primary_cause else "Unknown Anomaly"

            # Why selected
            why_sel = (
                f"Selected decision '{decision.value}' for hypothesis '{top_title}'. "
                f"Overall trust score = {trust_score.overall_trust_score * 100:.1f}%, "
                f"reasoning confidence = {trust_score.reasoning_confidence * 100:.1f}%."
            )

            # Why not alternative
            why_not = (
                "Alternative root cause hypotheses had lower evidence coverage and confidence scores."
                if len(reasoning_result.conclusion.ranked_root_causes) > 1
                else "No alternative hypothesis met the minimum evidence threshold."
            )

            # Supporting / Contradicting evidence
            ev_refs = getattr(reasoning_result.conclusion, "evidence_references", None) or getattr(reasoning_result, "evidence_references", None) or revalidation.revalidated_items
            supporting = [
                f"Evidence signal from {getattr(ref, 'source_agent', 'Agent')} (quality={getattr(ref, 'freshness_score', getattr(ref, 'confidence', 0.9)):.2f})"
                for ref in ev_refs[:5]
            ]
            contradicting = [
                f"Contradiction: {c.description}"
                for c in reasoning_result.conclusion.contradictions
            ]
            missing_text = reasoning_result.conclusion.explanation.missing_evidence_summary if reasoning_result.conclusion.explanation else "None"
            missing = missing_text.split(".")

            # Verifications & Counterfactual
            verif_res = (
                f"Adversarial verification {'PASSED' if not adversarial_result.is_disproved else 'FAILED'} "
                f"({adversarial_result.passed_challenges}/{adversarial_result.challenge_count} challenges passed)."
            )

            # Blast radius & Autonomy reason
            blast_reason = (
                f"Potential action blast radius rated '{blast_radius.potential_action_level.value}' "
                f"affecting {len(blast_radius.potential_affected_devices)} device(s) and "
                f"{len(blast_radius.potential_affected_services)} service(s)."
            )
            if blast_radius.is_action_larger_than_incident:
                blast_reason += " (Note: Action blast radius is larger than current incident blast radius)."

            if decision == AutonomyDecision.AUTO_ELIGIBLE:
                autonomy_reason = "Action meets all safety policy thresholds for autonomous execution: high trust score and low blast radius."
            elif decision == AutonomyDecision.HUMAN_APPROVAL_REQUIRED:
                autonomy_reason = f"Potential action blast radius ({blast_radius.potential_action_level.value}) exceeds policy threshold for automatic execution. Operator approval required."
            elif decision == AutonomyDecision.ADDITIONAL_EVIDENCE_REQUIRED:
                autonomy_reason = "Overall trust score or evidence completeness is insufficient to grant execution eligibility."
            else:
                autonomy_reason = "Action is BLOCKED due to disproved adversarial verification or unaddressed signal contradictions."

            # Risk factors
            risk_factors = []
            if blast_radius.potential_action_level in (BlastRadiusLevel.HIGH, BlastRadiusLevel.CRITICAL):
                risk_factors.append("High blast radius impacting critical core network services")
            if revalidation.stale_count > 0:
                risk_factors.append(f"Contains {revalidation.stale_count} stale evidence item(s)")
            if len(contradicting) > 0:
                risk_factors.append(f"Contains {len(contradicting)} conflicting evidence signal(s)")

            # Next step
            if primary_cause and primary_cause.recommended_actions:
                next_step = primary_cause.recommended_actions[0]
            else:
                next_step = "Present findings to Network Operations Center operator for manual review."

            explanation = DecisionExplanation(
                why_selected=why_sel,
                why_not_alternative=why_not,
                supporting_evidence=supporting,
                contradicting_evidence=contradicting,
                missing_evidence=[m.strip() for m in missing if m.strip()],
                verification_result=verif_res,
                counterfactual_result=counterfactual_result.conclusion,
                blast_radius_reason=blast_reason,
                autonomy_reason=autonomy_reason,
                risk_factors=risk_factors,
                recommended_next_step=next_step,
            )

            logger.info(f"DecisionExplainer generated explanation for decision '{decision.value}'")
            return explanation
