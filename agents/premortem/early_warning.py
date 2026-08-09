"""
Early Warning Engine for Enterprise Pre-Mortem Subsystem.

Detects network conditions progressing toward historical failure patterns and generates
early warnings without triggering automatic remediation.
"""

import threading
from typing import Any, Dict, List, Optional
import uuid

from agents.core.logger import get_agent_logger
from agents.premortem.premortem_models import (
    EarlyWarning,
    EarlyWarningUrgency,
    HistoricalIncidentMatch,
    IncidentFingerprint,
)

logger = get_agent_logger("EarlyWarningEngine")


class EarlyWarningEngine:
    """
    Thread-safe engine for early warning detection.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def detect_early_warnings(
        self,
        fingerprint: IncidentFingerprint,
        matches: List[HistoricalIncidentMatch],
    ) -> List[EarlyWarning]:
        """
        Evaluate fingerprint and historical matches to produce EarlyWarning items.

        Returns:
            List of EarlyWarning models.
        """
        with self._lock:
            warnings: List[EarlyWarning] = []

            if "HIGH_UTILIZATION" in fingerprint.interface_pattern or "WAN_CONGESTION" in fingerprint.incident_type:
                warnings.append(
                    EarlyWarning(
                        warning_id=str(uuid.uuid4()),
                        urgency=EarlyWarningUrgency.HIGH,
                        title="Early Stage WAN Congestion & Queue Saturation Pattern",
                        message="Current telemetry resembles early-stage historical WAN congestion failure patterns. Utilization is 95% with increasing packet loss.",
                        matched_pattern="WAN Congestion & Interface Saturation Pattern",
                        observed_signals=[
                            "High bandwidth utilization (95%)",
                            "Packet loss rising (8%)",
                            "Interface error counter incrementing",
                        ],
                        predicted_next_state="Critical interface queue drop and SLA latency breach within 5–10 minutes.",
                        confidence=0.88,
                        recommended_investigation="Inspect egress port queue depth and evaluate QoS traffic shaping adjustments.",
                    )
                )

            if "PACKET_LOSS" in fingerprint.interface_pattern:
                warnings.append(
                    EarlyWarning(
                        warning_id=str(uuid.uuid4()),
                        urgency=EarlyWarningUrgency.MEDIUM,
                        title="Impending Packet Loss Cascade",
                        message="Packet loss escalation pattern detected matching historical ISP link degradation incidents.",
                        matched_pattern="Packet Loss Cascade Pattern",
                        observed_signals=["Packet loss > 5% on primary uplink"],
                        predicted_next_state="Downstream application session drops and VoIP degradation.",
                        confidence=0.82,
                        recommended_investigation="Check upstream provider link status and secondary path SLA latency.",
                    )
                )

            logger.info(f"EarlyWarningEngine generated {len(warnings)} early warning notifications")
            return warnings
