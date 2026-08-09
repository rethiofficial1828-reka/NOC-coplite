"""
Time-to-Impact Estimator for Enterprise Pre-Mortem Subsystem.

Estimates realistic time-to-impact windows and service degradation bounds
without false pinpoint precision.
"""

import threading
from typing import Any, Dict, Optional

from agents.core.logger import get_agent_logger
from agents.premortem.premortem_models import TimeToImpact

logger = get_agent_logger("TimeToImpactEstimator")


class TimeToImpactEstimator:
    """
    Thread-safe engine for estimating realistic impact time windows.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def estimate_time_to_impact(
        self,
        current_utilization: float = 95.0,
        prediction_risk: float = 0.85,
    ) -> TimeToImpact:
        """
        Estimate time-to-impact range based on metric severity and risk slope.

        Returns:
            TimeToImpact model.
        """
        with self._lock:
            if current_utilization >= 95.0 or prediction_risk >= 0.90:
                min_t = 3.0
                max_t = 10.0
                exp_t = 5.0
                conf = 0.88
                desc = "Critical threshold breach & severe SLA degradation expected within 3–10 minutes if unmitigated."
            elif current_utilization >= 85.0 or prediction_risk >= 0.70:
                min_t = 10.0
                max_t = 30.0
                exp_t = 15.0
                conf = 0.82
                desc = "Moderate degradation & latency increase expected within 10–30 minutes."
            else:
                min_t = 30.0
                max_t = 120.0
                exp_t = 60.0
                conf = 0.75
                desc = "Potential degradation expected within 30–120 minutes."

            result = TimeToImpact(
                min_time_minutes=min_t,
                max_time_minutes=max_t,
                expected_time_minutes=exp_t,
                confidence=conf,
                threshold_type="SLA_LATENCY_BREACH",
                impact_description=desc,
            )

            logger.info(f"TimeToImpactEstimator calculated window: {min_t:.0f}–{max_t:.0f} mins (exp={exp_t:.0f}m, conf={conf:.2f})")
            return result
