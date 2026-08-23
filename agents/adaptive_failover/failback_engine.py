"""
Failback Engine Module for Adaptive Multi-Provider Failover Subsystem.

Evaluates primary provider recovery, requires sustained stability windows, prevents provider oscillation,
and produces evidence-grounded failback assessments.
"""

from datetime import datetime, timezone
from typing import Optional

from agents.core.logger import get_agent_logger
from agents.adaptive_failover.adaptive_models import (
    FailbackAssessment,
    FailbackCandidate,
    FailbackStatus,
    HysteresisPolicy,
    ProviderHealthSnapshot,
    StabilityWindow,
)
from agents.adaptive_failover.stability_engine import StabilityEngine

logger = get_agent_logger("FailbackEngine")


class FailbackEngine:
    """
    Evaluates safe failback to recovered primary provider.
    """

    def __init__(
        self,
        hysteresis_policy: Optional[HysteresisPolicy] = None,
        stability_engine: Optional[StabilityEngine] = None,
    ) -> None:
        self.policy = hysteresis_policy or HysteresisPolicy()
        self.stability_engine = stability_engine or StabilityEngine(policy=self.policy)

    def evaluate_failback(
        self,
        primary_snapshot: ProviderHealthSnapshot,
        current_active_snapshot: ProviderHealthSnapshot,
        recovery_duration_sec: float = 0.0,
        override_satisfied: bool = False,
    ) -> FailbackCandidate:
        """
        Evaluate whether failback to primary provider is safe and recommended.

        Args:
            primary_snapshot: Health snapshot of original primary provider.
            current_active_snapshot: Health snapshot of currently active alternate provider.
            recovery_duration_sec: Measured duration primary provider has remained continuously healthy.
            override_satisfied: Override flag for simulation tests.

        Returns:
            FailbackCandidate object.
        """
        req_duration = self.policy.minimum_recovery_duration_sec
        is_satisfied = override_satisfied or (recovery_duration_sec >= req_duration and primary_snapshot.health_score >= 85.0)

        window = StabilityWindow(
            provider_name=primary_snapshot.provider_name,
            required_duration_sec=req_duration,
            elapsed_duration_sec=round(recovery_duration_sec, 1),
            is_satisfied=is_satisfied,
            average_health_score=primary_snapshot.health_score,
        )

        status = FailbackStatus.WAIT_FOR_STABILITY
        justification = ""

        # Condition 1: Primary still unhealthy
        if primary_snapshot.health_score < 80.0 or primary_snapshot.failure_risk > 0.25:
            status = FailbackStatus.FAILBACK_BLOCKED
            justification = f"Primary provider '{primary_snapshot.provider_name}' remains degraded (Health={primary_snapshot.health_score:.1f}, Risk={primary_snapshot.failure_risk*100:.0f}%)."

        # Condition 2: Primary recovering but stability window not satisfied
        elif not is_satisfied:
            status = FailbackStatus.WAIT_FOR_STABILITY
            justification = (
                f"Primary provider '{primary_snapshot.provider_name}' is recovering but stability window "
                f"({recovery_duration_sec:.1f}s / {req_duration:.1f}s) is not yet satisfied."
            )

        # Condition 3: Flapping/Oscillation Risk Check
        else:
            osc = self.stability_engine.evaluate_oscillation_risk(primary_snapshot.provider_name)
            if osc.recommendation != "ALLOW_TRANSITION":
                status = FailbackStatus.FAILBACK_BLOCKED
                justification = f"Failback blocked by oscillation risk: {osc.recommendation}"
            else:
                status = FailbackStatus.FAILBACK_RECOMMENDED
                justification = (
                    f"Primary provider '{primary_snapshot.provider_name}' has demonstrated sustained stability and health "
                    f"(Score={primary_snapshot.health_score:.1f}, Window={recovery_duration_sec:.1f}s). Failback recommended."
                )

        logger.info(
            f"FailbackEngine evaluated primary provider '{primary_snapshot.provider_name}': "
            f"Status='{status.value}', Satisfied={is_satisfied}"
        )

        return FailbackCandidate(
            primary_provider=primary_snapshot.provider_name,
            current_active_provider=current_active_snapshot.provider_name,
            primary_snapshot=primary_snapshot,
            current_snapshot=current_active_snapshot,
            stability_window=window,
            status=status,
            justification=justification,
        )
