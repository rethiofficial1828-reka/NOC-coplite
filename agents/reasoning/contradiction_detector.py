"""
Contradiction Detector for Enterprise AI Reasoning Subsystem.

Identifies conflicting evidence signals across telemetry metrics, predictive risk scores,
incident tickets, topology states, and RAG knowledge items. Computes severity and penalty factors.
"""

import threading
from typing import Any, Dict, List, Optional
import uuid

from agents.core.logger import get_agent_logger
from agents.reasoning.reasoning_models import (
    Contradiction,
    ContradictionSeverity,
    ReasoningEvidence,
)

logger = get_agent_logger("ContradictionDetector")


class ContradictionDetector:
    """
    Thread-safe engine for detecting evidence contradictions and signal conflicts.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def detect_contradictions(
        self, evidence_list: List[ReasoningEvidence]
    ) -> List[Contradiction]:
        """
        Scan evidence list for conflicting signals and inconsistency patterns.

        Returns:
            List of detected Contradiction models.
        """
        with self._lock:
            contradictions: List[Contradiction] = []

            # Extract evidence by category
            telemetry_items = [e for e in evidence_list if "telemetry" in e.evidence_type.lower() or e.source_agent == "TelemetryAgent"]
            prediction_items = [e for e in evidence_list if "predict" in e.evidence_type.lower() or e.source_agent == "PredictionAgent"]
            incident_items = [e for e in evidence_list if "incident" in e.evidence_type.lower() or e.source_agent == "IncidentAgent"]
            topology_items = [e for e in evidence_list if "topolog" in e.evidence_type.lower() or e.source_agent == "TopologyAgent"]

            # Conflict Rule 1: Telemetry healthy vs Risk Prediction Critical
            for t in telemetry_items:
                for p in prediction_items:
                    t_util = t.payload.get("metrics", {}).get("bandwidth_utilization", t.payload.get("bandwidth_utilization", 0.0))
                    p_risk = p.payload.get("risk_score", 0.0)

                    if t_util < 20.0 and p_risk > 0.80:
                        c = Contradiction(
                            contradiction_id=f"cntr-{uuid.uuid4().hex[:8]}",
                            source_a=t.source_agent,
                            source_b=p.source_agent,
                            description=f"Telemetry reports low utilization ({t_util:.1f}%) but Prediction reports critical risk score ({p_risk:.2f}).",
                            severity=ContradictionSeverity.HIGH,
                            conflicting_evidence_ids=[t.evidence_id, p.evidence_id],
                            penalty_factor=0.25,
                        )
                        contradictions.append(c)

            # Conflict Rule 2: Prediction Healthy vs Active Critical Incident
            for p in prediction_items:
                for inc in incident_items:
                    p_risk = p.payload.get("risk_score", 0.0)
                    inc_sev = str(inc.payload.get("severity", "")).upper()

                    if p_risk < 0.15 and inc_sev in ("CRITICAL", "SEVERE"):
                        c = Contradiction(
                            contradiction_id=f"cntr-{uuid.uuid4().hex[:8]}",
                            source_a=p.source_agent,
                            source_b=inc.source_agent,
                            description=f"PredictionAgent reports low risk ({p_risk:.2f}) but IncidentAgent has active {inc_sev} incident ticket.",
                            severity=ContradictionSeverity.MEDIUM,
                            conflicting_evidence_ids=[p.evidence_id, inc.evidence_id],
                            penalty_factor=0.20,
                        )
                        contradictions.append(c)

            # Conflict Rule 3: Topology Link Down vs Telemetry Active Flow
            for top in topology_items:
                for t in telemetry_items:
                    top_status = str(top.payload.get("status", "")).lower()
                    t_bw = t.payload.get("metrics", {}).get("bandwidth_utilization", t.payload.get("bandwidth_utilization", 0.0))

                    if top_status == "down" and t_bw > 10.0:
                        c = Contradiction(
                            contradiction_id=f"cntr-{uuid.uuid4().hex[:8]}",
                            source_a=top.source_agent,
                            source_b=t.source_agent,
                            description=f"Topology reports link is DOWN but Telemetry reports active utilization ({t_bw:.1f}%).",
                            severity=ContradictionSeverity.CRITICAL,
                            conflicting_evidence_ids=[top.evidence_id, t.evidence_id],
                            penalty_factor=0.35,
                        )
                        contradictions.append(c)

            logger.info(
                f"ContradictionDetector evaluated {len(evidence_list)} evidence items "
                f"and detected {len(contradictions)} contradiction(s)."
            )
            return contradictions
