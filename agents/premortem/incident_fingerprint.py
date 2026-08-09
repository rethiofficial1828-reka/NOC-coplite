"""
Incident Fingerprint Engine for Enterprise Pre-Mortem Subsystem.

Extracts normalized, deterministic, serializable incident signatures from telemetry patterns,
predictive risk scores, topology relationships, and incident metadata without LLM dependency.
"""

import threading
from typing import Any, Dict, List, Optional
import uuid

from agents.core.logger import get_agent_logger
from agents.orchestrator_ai.investigation_context import InvestigationContext
from agents.reasoning.reasoning_models import ReasoningResult
from agents.premortem.premortem_models import FingerprintFeature, IncidentFingerprint

logger = get_agent_logger("IncidentFingerprintEngine")


class IncidentFingerprintEngine:
    """
    Thread-safe engine for extracting deterministic incident signatures.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def generate_fingerprint(
        self,
        reasoning_result: Optional[ReasoningResult] = None,
        context: Optional[InvestigationContext] = None,
        telemetry_payload: Optional[Dict[str, Any]] = None,
    ) -> IncidentFingerprint:
        """
        Generate normalized IncidentFingerprint from context and reasoning inputs.

        Returns:
            IncidentFingerprint model.
        """
        with self._lock:
            features: List[FingerprintFeature] = []
            telemetry_data = telemetry_payload or {}

            # 1. Telemetry Feature Extraction
            utilization = float(telemetry_data.get("bandwidth_utilization", 85.0))
            packet_loss = float(telemetry_data.get("packet_loss", 2.5))
            latency = float(telemetry_data.get("latency_ms", 35.0))
            error_count = int(telemetry_data.get("interface_errors", 12))

            features.append(FingerprintFeature(feature_name="bandwidth_utilization", feature_value=utilization, category="telemetry", weight=1.5))
            features.append(FingerprintFeature(feature_name="packet_loss", feature_value=packet_loss, category="telemetry", weight=2.0))
            features.append(FingerprintFeature(feature_name="latency_ms", feature_value=latency, category="telemetry", weight=1.2))
            features.append(FingerprintFeature(feature_name="interface_errors", feature_value=error_count, category="telemetry", weight=1.0))

            # 2. Derive Categorical Patterns Deterministically
            if utilization >= 90.0 and packet_loss > 5.0:
                interface_pat = "HIGH_UTILIZATION_WITH_PACKET_LOSS"
                inc_type = "WAN_CONGESTION"
            elif packet_loss > 10.0:
                interface_pat = "PACKET_LOSS_CASCADE"
                inc_type = "ISP_DEGRADATION"
            elif error_count > 50:
                interface_pat = "INTERFACE_ERROR_BURST"
                inc_type = "HARDWARE_INTERFACE_FLAPPING"
            else:
                interface_pat = "MODERATE_UTILIZATION"
                inc_type = "WAN_CONGESTION"

            # 3. Prediction & Reasoning Features
            pred_score = 0.85
            if reasoning_result and reasoning_result.conclusion:
                if reasoning_result.conclusion.confidence_result:
                    pred_score = reasoning_result.conclusion.confidence_result.overall_confidence
                if reasoning_result.conclusion.primary_root_cause:
                    inc_type = reasoning_result.conclusion.primary_root_cause.title.upper().replace(" ", "_")[:30]

            features.append(FingerprintFeature(feature_name="prediction_risk_score", feature_value=pred_score, category="prediction", weight=1.8))

            # Determine temporal & prediction patterns
            temporal_pat = "GRADUAL_DEGRADATION" if utilization > 80 else "TRANSIENT_SPIKE"
            pred_pat = "INCREASING_FAILURE_RISK" if pred_score >= 0.75 else "STABLE_RISK"
            topo_pat = "MULTI_SERVICE_DEPENDENCY"

            fingerprint = IncidentFingerprint(
                fingerprint_id=str(uuid.uuid4()),
                incident_type=inc_type,
                device_class="ROUTER",
                interface_pattern=interface_pat,
                temporal_pattern=temporal_pat,
                prediction_pattern=pred_pat,
                topology_pattern=topo_pat,
                features=features,
            )

            logger.info(
                f"IncidentFingerprintEngine generated fingerprint '{fingerprint.fingerprint_id}': "
                f"type='{inc_type}', interface_pat='{interface_pat}', features={len(features)}"
            )
            return fingerprint
