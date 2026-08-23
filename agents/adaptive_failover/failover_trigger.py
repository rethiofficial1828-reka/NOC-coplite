"""
Failover Trigger Engine Module for Adaptive Multi-Provider Failover Subsystem.

Evaluates multi-signal degradation severity, hysteresis preconditions, oscillation assessments,
TrustDecisions, and PreMortemResults to determine failover trigger outcomes.
"""

from datetime import datetime, timezone
from typing import Optional

from agents.core.logger import get_agent_logger
from agents.adaptive_failover.adaptive_models import (
    DegradationEvent,
    FailoverTrigger,
    OscillationAssessment,
    OscillationRisk,
    ProviderHealthSnapshot,
    TransitionReason,
)
from agents.trust.trust_models import TrustDecision

logger = get_agent_logger("FailoverTriggerEngine")


class FailoverTriggerEngine:
    """
    Evaluates system inputs to generate evidence-grounded failover triggers.
    """

    def evaluate_trigger(
        self,
        active_snapshot: ProviderHealthSnapshot,
        candidate_snapshot: Optional[ProviderHealthSnapshot] = None,
        degradation_event: Optional[DegradationEvent] = None,
        oscillation_assessment: Optional[OscillationAssessment] = None,
        trust_decision: Optional[TrustDecision] = None,
        hysteresis_passed: bool = True,
        hysteresis_reason: str = "",
    ) -> FailoverTrigger:
        """
        Evaluate whether a provider failover trigger should be generated.

        Returns:
            FailoverTrigger object.
        """
        if not candidate_snapshot:
            return FailoverTrigger(
                action="NO_ACTION",
                reason=TransitionReason.UNKNOWN,
                active_provider=active_snapshot.provider_name,
                requires_approval=True,
                confidence=1.0,
            )

        # 1. No degradation detected & provider healthy
        if not degradation_event and active_snapshot.health_score >= 80.0:
            return FailoverTrigger(
                action="NO_ACTION",
                reason=TransitionReason.UNKNOWN,
                active_provider=active_snapshot.provider_name,
                target_provider=candidate_snapshot.provider_name,
                requires_approval=True,
                confidence=1.0,
            )

        # 2. Hysteresis or Flapping Blocked
        if not hysteresis_passed:
            logger.warning(f"FailoverTriggerEngine: Failover BLOCKED by hysteresis: {hysteresis_reason}")
            return FailoverTrigger(
                action="FAILOVER_BLOCKED",
                reason=TransitionReason.HIGH_LATENCY if active_snapshot.latency_ms > 100 else TransitionReason.FAILURE_RISK,
                active_provider=active_snapshot.provider_name,
                target_provider=candidate_snapshot.provider_name,
                degradation_event=degradation_event,
                oscillation_assessment=oscillation_assessment,
                requires_approval=True,
                confidence=0.9,
            )

        # 3. Trust Gate Check
        if trust_decision:
            t_status = trust_decision.decision.value if hasattr(trust_decision.decision, 'value') else str(trust_decision.decision)
            if t_status.upper() == "BLOCKED":
                return FailoverTrigger(
                    action="FAILOVER_BLOCKED",
                    reason="TrustAgent decision: BLOCKED by operational policy",
                    active_provider=active_snapshot.provider_name,
                    target_provider=candidate_snapshot.provider_name,
                    degradation_event=degradation_event,
                    requires_approval=True,
                    confidence=0.95,
                )

        # 4. Generate Valid Failover Trigger
        reason = TransitionReason.HARD_FAILURE if (degradation_event and degradation_event.is_hard_failure) else TransitionReason.HIGH_LATENCY
        action = "REQUEST_FAILOVER"

        logger.info(
            f"FailoverTriggerEngine generated '{action}' trigger for '{active_snapshot.provider_name}' -> "
            f"'{candidate_snapshot.provider_name}' (Reason: {reason.value})"
        )

        return FailoverTrigger(
            action=action,
            reason=reason,
            active_provider=active_snapshot.provider_name,
            target_provider=candidate_snapshot.provider_name,
            degradation_event=degradation_event,
            oscillation_assessment=oscillation_assessment,
            requires_approval=True,
            confidence=0.95,
            timestamp=datetime.now(timezone.utc),
        )
