"""
Stability Engine Module for Adaptive Multi-Provider Failover Subsystem.

Enforces configurable HysteresisPolicy parameters (hold times, cooldowns, transition limits)
and calculates OscillationAssessments to prevent provider flapping and micro-switching.
"""

from datetime import datetime, timezone
import threading
from typing import Dict, List, Optional, Tuple

from agents.core.logger import get_agent_logger
from agents.adaptive_failover.adaptive_models import (
    HysteresisPolicy,
    OscillationAssessment,
    OscillationRisk,
    TransitionRecord,
)

logger = get_agent_logger("StabilityEngine")


class StabilityEngine:
    """
    Hysteresis and Anti-Flapping Engine enforcing provider stability policies.
    """

    def __init__(self, policy: Optional[HysteresisPolicy] = None) -> None:
        self.policy = policy or HysteresisPolicy()
        self._transition_history: List[TransitionRecord] = []
        self._last_transition_time: Dict[str, datetime] = {}
        self._lock = threading.RLock()

    def record_transition(self, record: TransitionRecord) -> None:
        """Record a completed transition in history."""
        with self._lock:
            self._transition_history.append(record)
            self._last_transition_time[record.from_provider] = record.timestamp
            self._last_transition_time[record.to_provider] = record.timestamp
            logger.info(f"StabilityEngine recorded transition '{record.from_provider}' -> '{record.to_provider}'")

    def evaluate_oscillation_risk(self, provider_name: str) -> OscillationAssessment:
        """
        Evaluate oscillation risk and flapping history for a given provider.

        Args:
            provider_name: Provider name string.

        Returns:
            OscillationAssessment object.
        """
        with self._lock:
            now = datetime.now(timezone.utc)
            one_hour_ago = now.timestamp() - 3600.0

            recent_transitions = [
                r for r in self._transition_history
                if r.timestamp.timestamp() >= one_hour_ago and (r.from_provider == provider_name or r.to_provider == provider_name)
            ]

            count = len(recent_transitions)
            last_time = self._last_transition_time.get(provider_name)
            time_since_sec = (now - last_time).total_seconds() if last_time else 99999.0

            risk = OscillationRisk.LOW
            is_flapping = False
            rec = "ALLOW_TRANSITION"

            if count >= self.policy.maximum_transitions_per_hour:
                risk = OscillationRisk.CRITICAL
                is_flapping = True
                rec = "BLOCK_TRANSITION_MAX_HOURLY_LIMIT"
            elif time_since_sec < self.policy.cooldown_after_failover_sec:
                risk = OscillationRisk.HIGH
                rec = "BLOCK_TRANSITION_COOLDOWN_ACTIVE"
            elif count >= 2:
                risk = OscillationRisk.MEDIUM

            logger.info(
                f"StabilityEngine evaluated oscillation risk for '{provider_name}': "
                f"Risk='{risk.value}', Flapping={is_flapping}, Rec='{rec}', TransitionsInHour={count}"
            )

            return OscillationAssessment(
                provider_name=provider_name,
                risk_level=risk,
                transitions_last_hour=count,
                time_since_last_transition_sec=round(time_since_sec, 1),
                is_flapping=is_flapping,
                recommendation=rec,
            )

    def validate_hysteresis_preconditions(
        self,
        active_provider: str,
        target_provider: str,
        degradation_duration_sec: float = 0.0,
        is_hard_failure: bool = False,
        recovery_duration_sec: float = 0.0,
    ) -> Tuple[bool, str]:
        """
        Validate whether a proposed transition satisfies all HysteresisPolicy requirements.

        Args:
            active_provider: Currently active provider name.
            target_provider: Candidate provider name.
            degradation_duration_sec: Observed persistence duration of degradation.
            is_hard_failure: True if hard network failure (bypasses degradation duration requirement).
            recovery_duration_sec: Duration primary provider has been continuously healthy before failback.

        Returns:
            Tuple of (is_satisfied_bool, rationale_message).
        """
        with self._lock:
            # 1. Hard failure bypasses degradation window requirement
            if is_hard_failure:
                return True, "Hard failure detected — hysteresis duration check bypassed."

            # 2. Recovery duration check (for failback)
            if recovery_duration_sec > 0 and recovery_duration_sec < self.policy.minimum_recovery_duration_sec:
                return (
                    False,
                    f"Recovery duration ({recovery_duration_sec:.1f}s) is below minimum "
                    f"recovery confirmation window ({self.policy.minimum_recovery_duration_sec:.1f}s)."
                )

            # 3. Minimum degradation duration check
            if degradation_duration_sec > 0 and degradation_duration_sec < self.policy.minimum_degradation_duration_sec:
                return (
                    False,
                    f"Degradation duration ({degradation_duration_sec:.1f}s) is below minimum "
                    f"confirmation window ({self.policy.minimum_degradation_duration_sec:.1f}s)."
                )

            # 3. Oscillation & Cooldown checks
            osc_assessment = self.evaluate_oscillation_risk(active_provider)
            if osc_assessment.recommendation != "ALLOW_TRANSITION":
                return False, f"Hysteresis policy blocked transition: {osc_assessment.recommendation}"

            # 4. Minimum hold time on active provider
            last_active_t = self._last_transition_time.get(active_provider)
            if last_active_t:
                hold_sec = (datetime.now(timezone.utc) - last_active_t).total_seconds()
                if hold_sec < self.policy.minimum_hold_time_sec:
                    return (
                        False,
                        f"Active provider hold time ({hold_sec:.1f}s) is below minimum "
                        f"required hold time ({self.policy.minimum_hold_time_sec:.1f}s)."
                    )

            return True, "Hysteresis policy checks satisfied."
