"""
Trust Service for Enterprise Trust, Verification & Safe Autonomy Subsystem.

Coordinates evidence re-validation, adversarial verification, counterfactual analysis,
blast radius evaluation, trust scoring, autonomy policy enforcement, handoff evaluation,
and decision explanation generation.

CRITICAL SAFETY BOUNDARY: TrustService does not execute network actions under any circumstance.
"""

from datetime import datetime, timezone
import time
import threading
from typing import Any, Dict, List, Optional
import uuid

from agents.core.logger import get_agent_logger
from agents.orchestrator_ai.investigation_context import InvestigationContext
from agents.reasoning.reasoning_models import ReasoningResult
from agents.trust.adversarial_verifier import AdversarialVerifier
from agents.trust.autonomy_policy import AutonomyPolicyEngine
from agents.trust.blast_radius_engine import BlastRadiusEngine
from agents.trust.confidence_handoff import ConfidenceHandoffEngine
from agents.trust.counterfactual_engine import CounterfactualEngine
from agents.trust.decision_explainer import DecisionExplainer
from agents.trust.evidence_revalidator import EvidenceRevalidator
from agents.trust.trust_models import (
    AutonomyDecision,
    DecisionFactor,
    DecisionLifecycleState,
    TrustAssessment,
    TrustDecision,
    TrustScore,
    TrustStatistics,
    VerificationStatus,
)

logger = get_agent_logger("TrustService")


class TrustService:
    """
    Domain service coordinating trust, verification, and safe autonomy evaluation.
    """

    def __init__(
        self,
        revalidator: Optional[EvidenceRevalidator] = None,
        verifier: Optional[AdversarialVerifier] = None,
        counterfactual_engine: Optional[CounterfactualEngine] = None,
        blast_engine: Optional[BlastRadiusEngine] = None,
        policy_engine: Optional[AutonomyPolicyEngine] = None,
        handoff_engine: Optional[ConfidenceHandoffEngine] = None,
        explainer: Optional[DecisionExplainer] = None,
    ) -> None:
        self._revalidator = revalidator or EvidenceRevalidator()
        self._verifier = verifier or AdversarialVerifier()
        self._counterfactual_engine = counterfactual_engine or CounterfactualEngine()
        self._blast_engine = blast_engine or BlastRadiusEngine()
        self._policy_engine = policy_engine or AutonomyPolicyEngine()
        self._handoff_engine = handoff_engine or ConfidenceHandoffEngine()
        self._explainer = explainer or DecisionExplainer()
        self._lock = threading.RLock()

    def evaluate_trust(
        self,
        reasoning_result: ReasoningResult,
        context: Optional[InvestigationContext] = None,
        is_reversible: bool = True,
        has_rollback_plan: bool = True,
    ) -> TrustDecision:
        """
        Execute safe autonomy decision evaluation over reasoning_result.

        Returns:
            Completed TrustDecision object.
        """
        with self._lock:
            start_time = time.perf_counter()
            request_id = reasoning_result.request_id

            # 1. Evidence Re-validation
            if context:
                revalidation = self._revalidator.revalidate_context_evidence(context)
            else:
                revalidation = self._revalidator.revalidate_evidence_list([])

            # 2. Adversarial Verification
            adversarial_result = self._verifier.verify_hypothesis(reasoning_result, context)

            # Determine Verification Status
            if adversarial_result.is_disproved:
                verif_status = VerificationStatus.CONTRADICTED
            elif adversarial_result.failed_challenges > 0:
                verif_status = VerificationStatus.FAILED
            elif sum(1 for c in adversarial_result.challenges if c.result_status == VerificationStatus.WARNING) > 0:
                verif_status = VerificationStatus.WARNING
            else:
                verif_status = VerificationStatus.PASSED

            # 3. Counterfactual Analysis
            counterfactual_result = self._counterfactual_engine.evaluate_counterfactuals(reasoning_result)

            # 4. Blast Radius Analysis
            blast_radius = self._blast_engine.calculate_blast_radius(reasoning_result, context)

            # 5. Calculate Multi-dimensional Trust Score
            reasoning_conf = reasoning_result.conclusion.confidence_result.overall_confidence
            ev_conf = revalidation.overall_quality_score
            verif_conf = max(0.1, 1.0 - adversarial_result.penalty_factor)
            safety_score = max(0.1, 1.0 - blast_radius.score)

            factors = [
                DecisionFactor(factor_name="Reasoning Confidence", score=reasoning_conf, weight=0.30, contribution=round(reasoning_conf * 0.30, 2), rationale="Reasoning engine confidence score"),
                DecisionFactor(factor_name="Evidence Quality", score=ev_conf, weight=0.25, contribution=round(ev_conf * 0.25, 2), rationale="Evidence freshness and completeness"),
                DecisionFactor(factor_name="Adversarial Verification", score=verif_conf, weight=0.25, contribution=round(verif_conf * 0.25, 2), rationale="Adversarial probing outcome"),
                DecisionFactor(factor_name="Operational Safety", score=safety_score, weight=0.20, contribution=round(safety_score * 0.20, 2), rationale="Topology & blast radius safety score"),
            ]

            raw_trust = sum(f.contribution for f in factors) + counterfactual_result.confidence_adjustment
            overall_trust = max(0.05, min(1.0, raw_trust))

            trust_score = TrustScore(
                reasoning_confidence=round(reasoning_conf, 2),
                evidence_confidence=round(ev_conf, 2),
                verification_confidence=round(verif_conf, 2),
                operational_safety_score=round(safety_score, 2),
                overall_trust_score=round(overall_trust, 2),
                breakdown=factors,
            )

            # 6. Autonomy Policy Evaluation
            decision_outcome = self._policy_engine.evaluate_decision(
                trust_score=trust_score,
                verification_status=verif_status,
                blast_radius=blast_radius,
                adversarial_result=adversarial_result,
                is_reversible=is_reversible,
                has_rollback_plan=has_rollback_plan,
            )

            # 7. Confidence Handoff Assessment
            handoff = self._handoff_engine.evaluate_handoff(
                decision=decision_outcome,
                confidence_score=trust_score.overall_trust_score,
                evidence_revalidation=revalidation,
                adversarial_result=adversarial_result,
                counterfactual_result=counterfactual_result,
                blast_radius=blast_radius,
            )

            # 8. Synthesize Decision Explanation
            explanation = self._explainer.generate_explanation(
                decision=decision_outcome,
                reasoning_result=reasoning_result,
                trust_score=trust_score,
                adversarial_result=adversarial_result,
                counterfactual_result=counterfactual_result,
                blast_radius=blast_radius,
                revalidation=revalidation,
            )

            # Construct TrustAssessment
            assessment = TrustAssessment(
                assessment_id=str(uuid.uuid4()),
                trust_score=trust_score,
                verification_status=verif_status,
                blast_radius=blast_radius,
                lifecycle_state=DecisionLifecycleState.AUTONOMY_EVALUATED,
                created_at=datetime.now(timezone.utc),
            )

            decision = TrustDecision(
                decision_id=str(uuid.uuid4()),
                investigation_id=context.context_id if context else str(uuid.uuid4()),
                request_id=request_id,
                decision=decision_outcome,
                lifecycle_state=DecisionLifecycleState.DECISION_READY,
                trust_assessment=assessment,
                handoff=handoff,
                explanation=explanation,
                policy_applied=self._policy_engine.policy,
                created_at=datetime.now(timezone.utc),
            )

            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            logger.info(
                f"TrustService evaluated request '{request_id}' in {elapsed_ms:.2f}ms: "
                f"decision='{decision_outcome.value}', trust_score={overall_trust:.2f}, "
                f"blast_radius='{blast_radius.potential_action_level.value}'"
            )

            return decision
