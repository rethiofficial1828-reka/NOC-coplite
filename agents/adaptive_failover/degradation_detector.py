"""
Degradation Detector Module for Adaptive Multi-Provider Failover Subsystem.

Evaluates multi-signal telemetry streams to detect hard failures, gradual degradation, predicted degradation,
partial failures, and provider recoveries. Classifies severity and produces correlated DegradationEvents.
"""

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from agents.core.logger import get_agent_logger
from agents.adaptive_failover.adaptive_models import (
    DegradationEvent,
    ProviderHealthSnapshot,
    ProviderState,
)

logger = get_agent_logger("DegradationDetector")


class DegradationDetector:
    """
    Multi-signal degradation detector classifying severity and failure types.
    """

    def detect_degradation(
        self,
        snapshot: ProviderHealthSnapshot,
        previous_snapshot: Optional[ProviderHealthSnapshot] = None,
        duration_sec: float = 0.0,
    ) -> Optional[DegradationEvent]:
        """
        Evaluate snapshot metrics and correlate signals to detect degradation.

        Args:
            snapshot: Current ProviderHealthSnapshot.
            previous_snapshot: Optional preceding snapshot.
            duration_sec: Observed persistence duration of degradation in seconds.

        Returns:
            DegradationEvent if degradation detected, else None.
        """
        correlated_signals: List[str] = []
        is_hard_failure = False
        primary_metric = "none"
        observed_val = 0.0
        thresh_val = 0.0
        severity = ProviderState.HEALTHY

        # Signal 1: Packet Loss Spike
        if snapshot.packet_loss_percent >= 10.0:
            is_hard_failure = True
            severity = ProviderState.FAILED
            primary_metric = "packet_loss_percent"
            observed_val = snapshot.packet_loss_percent
            thresh_val = 10.0
            correlated_signals.append(f"Severe packet loss ({snapshot.packet_loss_percent:.1f}%)")
        elif snapshot.packet_loss_percent >= 3.0:
            severity = ProviderState.CRITICAL
            primary_metric = "packet_loss_percent"
            observed_val = snapshot.packet_loss_percent
            thresh_val = 3.0
            correlated_signals.append(f"Packet loss elevation ({snapshot.packet_loss_percent:.1f}%)")

        # Signal 2: Latency Spike
        if snapshot.latency_ms >= 150.0:
            if severity not in (ProviderState.FAILED, ProviderState.CRITICAL):
                severity = ProviderState.CRITICAL
                primary_metric = "latency_ms"
                observed_val = snapshot.latency_ms
                thresh_val = 150.0
            correlated_signals.append(f"High latency ({snapshot.latency_ms:.1f} ms)")

        # Signal 3: XGBoost Predictive Risk Elevation
        if snapshot.failure_risk >= 0.70:
            if severity not in (ProviderState.FAILED, ProviderState.CRITICAL):
                severity = ProviderState.CRITICAL
                primary_metric = "failure_risk"
                observed_val = snapshot.failure_risk
                thresh_val = 0.70
            correlated_signals.append(f"Predictive failure risk elevated ({snapshot.failure_risk*100:.0f}%)")
        elif snapshot.failure_risk >= 0.30:
            if severity == ProviderState.HEALTHY:
                severity = ProviderState.DEGRADED
                primary_metric = "failure_risk"
                observed_val = snapshot.failure_risk
                thresh_val = 0.30
            correlated_signals.append(f"Predictive risk warning ({snapshot.failure_risk*100:.0f}%)")

        # Signal 4: Interface Flaps & Errors
        if snapshot.interface_flaps >= 3:
            correlated_signals.append(f"Interface flapping ({snapshot.interface_flaps} flaps)")

        # Signal 5: Rapid Trend Degradation
        if snapshot.health_trend == "RAPIDLY_DEGRADED":
            correlated_signals.append("Rapid health score drop")

        # Require correlated signals or hard failure before issuing transition event
        if len(correlated_signals) == 0 and snapshot.health_score >= 80.0:
            return None

        if len(correlated_signals) < 2 and not is_hard_failure and snapshot.health_score > 60.0:
            logger.debug(f"DegradationDetector ignored single weak signal: {correlated_signals}")
            return None

        event = DegradationEvent(
            provider_name=snapshot.provider_name,
            severity=severity if severity != ProviderState.HEALTHY else ProviderState.DEGRADED,
            primary_metric=primary_metric,
            observed_value=observed_val,
            threshold_value=thresh_val,
            duration_sec=duration_sec,
            correlated_signals=correlated_signals,
            is_hard_failure=is_hard_failure,
            timestamp=datetime.now(timezone.utc),
        )

        logger.info(
            f"DegradationDetector generated DegradationEvent for '{snapshot.provider_name}': "
            f"Severity='{event.severity.value}', Correlated Signals={len(correlated_signals)}"
        )
        return event
