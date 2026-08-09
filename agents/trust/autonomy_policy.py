"""
Autonomy Policy Engine for Enterprise Trust & Safe Autonomy Subsystem.

Evaluates configurable policy rules to determine actionable safety decisions:
AUTO_ELIGIBLE, HUMAN_APPROVAL_REQUIRED, ADDITIONAL_EVIDENCE_REQUIRED, or BLOCKED.
"""

import threading
from typing import Any, Dict, Optional

from agents.core.logger import get_agent_logger
from agents.trust.trust_models import (
    AdversarialResult,
    AutonomyDecision,
    AutonomyPolicy,
    BlastRadius,
    BlastRadiusLevel,
    TrustScore,
    VerificationStatus,
)

logger = get_agent_logger("AutonomyPolicyEngine")


class AutonomyPolicyEngine:
    """
    Thread-safe engine for deterministic autonomy policy evaluation.
    """

    def __init__(self, policy: Optional[AutonomyPolicy] = None) -> None:
        self._policy = policy or AutonomyPolicy()
        self._lock = threading.RLock()

    @property
    def policy(self) -> AutonomyPolicy:
        """Current autonomy policy parameters."""
        with self._lock:
            return self._policy.model_copy()

    @policy.setter
    def policy(self, policy: AutonomyPolicy) -> None:
        """Set custom autonomy policy parameters."""
        with self._lock:
            self._policy = policy

    def evaluate_decision(
        self,
        trust_score: TrustScore,
        verification_status: VerificationStatus,
        blast_radius: BlastRadius,
        adversarial_result: AdversarialResult,
        is_reversible: bool = True,
        has_rollback_plan: bool = True,
    ) -> AutonomyDecision:
        """
        Evaluate inputs against centralized autonomy policy rules.

        Returns:
            AutonomyDecision enum.
        """
        with self._lock:
            p = self._policy

            # Rule 1: Adversarial Disproof -> BLOCKED
            if adversarial_result.is_disproved or verification_status == VerificationStatus.CONTRADICTED:
                logger.info("Policy Decision: BLOCKED (Adversarial challenge disproved hypothesis)")
                return AutonomyDecision.BLOCKED

            # Rule 2: Low Trust / Insufficient Evidence -> ADDITIONAL_EVIDENCE_REQUIRED
            if trust_score.overall_trust_score < 0.60 or verification_status == VerificationStatus.INSUFFICIENT_EVIDENCE:
                logger.info("Policy Decision: ADDITIONAL_EVIDENCE_REQUIRED (Trust score below 0.60)")
                return AutonomyDecision.ADDITIONAL_EVIDENCE_REQUIRED

            # Rule 3: High / Critical Blast Radius -> HUMAN_APPROVAL_REQUIRED
            level_rank = {BlastRadiusLevel.LOW: 1, BlastRadiusLevel.MEDIUM: 2, BlastRadiusLevel.HIGH: 3, BlastRadiusLevel.CRITICAL: 4}
            if level_rank[blast_radius.potential_action_level] > level_rank[p.max_blast_radius]:
                logger.info(
                    f"Policy Decision: HUMAN_APPROVAL_REQUIRED (Blast radius {blast_radius.potential_action_level.value} "
                    f"exceeds policy max {p.max_blast_radius.value})"
                )
                return AutonomyDecision.HUMAN_APPROVAL_REQUIRED

            # Rule 4: Reversibility & Rollback Policy Requirements
            if p.require_reversibility and not is_reversible:
                logger.info("Policy Decision: HUMAN_APPROVAL_REQUIRED (Action is non-reversible)")
                return AutonomyDecision.HUMAN_APPROVAL_REQUIRED

            if p.require_rollback_plan and not has_rollback_plan:
                logger.info("Policy Decision: HUMAN_APPROVAL_REQUIRED (No rollback plan available)")
                return AutonomyDecision.HUMAN_APPROVAL_REQUIRED

            # Rule 5: Auto-Execution Disabled globally -> HUMAN_APPROVAL_REQUIRED
            if not p.allow_auto_execution:
                logger.info("Policy Decision: HUMAN_APPROVAL_REQUIRED (Global auto-execution disabled)")
                return AutonomyDecision.HUMAN_APPROVAL_REQUIRED

            # Rule 6: High Trust + Low Blast Radius + Reversible -> AUTO_ELIGIBLE
            if trust_score.overall_trust_score >= p.min_trust_score and blast_radius.potential_action_level == BlastRadiusLevel.LOW:
                logger.info("Policy Decision: AUTO_ELIGIBLE (High trust & low blast radius)")
                return AutonomyDecision.AUTO_ELIGIBLE

            # Default fallback for moderate conditions
            logger.info("Policy Decision: HUMAN_APPROVAL_REQUIRED (Default policy requirement)")
            return AutonomyDecision.HUMAN_APPROVAL_REQUIRED
