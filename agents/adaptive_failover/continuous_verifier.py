"""
Continuous Verification Engine Module for Adaptive Multi-Provider Failover Subsystem.

Continuously monitors network performance following a transition.
Compares BEFORE vs CURRENT vs EXPECTED metrics to detect sustained improvements, regressions,
or secondary provider degradations.
"""

from datetime import datetime, timezone
from typing import Dict, Optional
import uuid

from agents.core.logger import get_agent_logger
from agents.adaptive_failover.adaptive_models import ContinuousVerificationResult, ProviderHealthSnapshot

logger = get_agent_logger("ContinuousVerificationEngine")


class ContinuousVerificationEngine:
    """
    Continuous post-transition closed-loop verification engine.
    """

    def evaluate_continuous_verification(
        self,
        before_snapshot: ProviderHealthSnapshot,
        current_snapshot: ProviderHealthSnapshot,
        expected_health: float = 85.0,
    ) -> ContinuousVerificationResult:
        """
        Evaluate continuous performance comparison.

        Args:
            before_snapshot: Health snapshot of original provider prior to transition.
            current_snapshot: Health snapshot of newly active provider.
            expected_health: Minimum expected health target.

        Returns:
            ContinuousVerificationResult object.
        """
        verif_id = str(uuid.uuid4())
        before_h = before_snapshot.health_score
        curr_h = current_snapshot.health_score

        is_improvement = curr_h > (before_h + 10.0)
        regression_detected = curr_h < before_h or curr_h < 50.0

        rec_action = "MAINTAIN_CURRENT"
        if regression_detected:
            rec_action = "TRIGGER_ROLLBACK_OR_FAILBACK"
            logger.warning(
                f"ContinuousVerificationEngine REGRESSION DETECTED on active provider '{current_snapshot.provider_name}': "
                f"Before={before_h:.1f}, Current={curr_h:.1f}"
            )
        elif not is_improvement:
            rec_action = "MONITOR_PARTIAL_IMPROVEMENT"
        else:
            logger.info(
                f"ContinuousVerificationEngine VERIFIED IMPROVEMENT on active provider '{current_snapshot.provider_name}': "
                f"Before={before_h:.1f} -> Current={curr_h:.1f}"
            )

        return ContinuousVerificationResult(
            verification_id=verif_id,
            active_provider=current_snapshot.provider_name,
            before_health=before_h,
            current_health=curr_h,
            expected_health=expected_health,
            is_improvement=is_improvement,
            regression_detected=regression_detected,
            recommended_action=rec_action,
            timestamp=datetime.now(timezone.utc),
        )
