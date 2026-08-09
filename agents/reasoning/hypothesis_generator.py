"""
Hypothesis Generator for Enterprise AI Reasoning Subsystem.

Generates multiple competing hypotheses to explain network operational failure symptoms
based on correlated evidence signals. Computes coverage scores and missing evidence requirements.
"""

import threading
from typing import Any, Dict, List, Optional
import uuid

from agents.core.logger import get_agent_logger
from agents.reasoning.reasoning_models import (
    EvidenceCorrelation,
    EvidenceGroup,
    Hypothesis,
    HypothesisCategory,
    ReasoningEvidence,
)

logger = get_agent_logger("HypothesisGenerator")


class HypothesisGenerator:
    """
    Thread-safe engine for generating competing root cause hypotheses.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def generate_hypotheses(
        self,
        correlation: EvidenceCorrelation,
        evidence_list: Optional[List[ReasoningEvidence]] = None,
        query_hint: str = "",
    ) -> List[Hypothesis]:
        """
        Generate multiple competing hypotheses based on correlated evidence groups.

        Returns:
            List of competing Hypothesis models.
        """
        with self._lock:
            hypotheses: List[Hypothesis] = []
            ev_map = {e.evidence_id: e for e in (evidence_list or [])}
            all_ev_ids = [e.evidence_id for e in (evidence_list or [])]

            # 1. Hypothesis: WAN Congestion & Bandwidth Saturation
            wan_supporting = self._find_supporting_evidence(
                evidence_list,
                keywords=["bandwidth", "utilization", "congestion", "saturation", "buffer", "high risk", "traffic"],
            )
            h_wan = Hypothesis(
                hypothesis_id=f"hyp-wan-{uuid.uuid4().hex[:8]}",
                title="WAN Link Congestion & Traffic Saturation",
                description="Heavy traffic volume exceeding uplink capacity causing packet drops and latency spikes.",
                category=HypothesisCategory.WAN_CONGESTION,
                supporting_evidence_ids=wan_supporting,
                missing_evidence_descriptions=["NetFlow traffic breakdown by top talkers", "Interface queue depth metrics"],
                initial_likelihood=0.85 if wan_supporting else 0.40,
                coverage_score=len(wan_supporting) / max(1, len(all_ev_ids)),
            )
            hypotheses.append(h_wan)

            # 2. Hypothesis: Routing Instability & BGP/OSPF Flapping
            route_supporting = self._find_supporting_evidence(
                evidence_list,
                keywords=["route", "routing", "flapping", "bgp", "ospf", "converge", "as-path", "packet_loss"],
            )
            h_route = Hypothesis(
                hypothesis_id=f"hyp-route-{uuid.uuid4().hex[:8]}",
                title="Routing Protocol Instability & Route Flapping",
                description="BGP or OSPF route flapping causing intermittent reachability drops and sub-optimal routing paths.",
                category=HypothesisCategory.ROUTING_INSTABILITY,
                supporting_evidence_ids=route_supporting,
                missing_evidence_descriptions=["BGP neighbor state logs", "OSPF LSA update telemetry"],
                initial_likelihood=0.75 if route_supporting else 0.35,
                coverage_score=len(route_supporting) / max(1, len(all_ev_ids)),
            )
            hypotheses.append(h_route)

            # 3. Hypothesis: Hardware Interface Physical Layer CRC Errors / Cable Degradation
            hw_supporting = self._find_supporting_evidence(
                evidence_list,
                keywords=["crc", "error", "interface", "phy", "physical", "port", "cable", "duplex"],
            )
            h_hw = Hypothesis(
                hypothesis_id=f"hyp-hw-{uuid.uuid4().hex[:8]}",
                title="Physical Interface CRC Errors / Transceiver Degradation",
                description="Physical Layer 1 optical transceiver degradation or cable faults injecting CRC error frames.",
                category=HypothesisCategory.HARDWARE_INTERFACE_FLAPPING,
                supporting_evidence_ids=hw_supporting,
                missing_evidence_descriptions=["SFP Digital Optical Monitoring (DOM) Rx/Tx power levels", "Interface CRC error rate counter"],
                initial_likelihood=0.65 if hw_supporting else 0.30,
                coverage_score=len(hw_supporting) / max(1, len(all_ev_ids)),
            )
            hypotheses.append(h_hw)

            # 4. Hypothesis: Upstream ISP / Provider Outage
            isp_supporting = self._find_supporting_evidence(
                evidence_list,
                keywords=["isp", "provider", "external", "upstream", "carrier", "transit"],
            )
            h_isp = Hypothesis(
                hypothesis_id=f"hyp-isp-{uuid.uuid4().hex[:8]}",
                title="Upstream Service Provider (ISP) Degradation",
                description="Packet loss or degradation occurring beyond local demarcation in the upstream carrier network.",
                category=HypothesisCategory.ISP_DEGRADATION,
                supporting_evidence_ids=isp_supporting,
                missing_evidence_descriptions=["MTR traceroute path probes to internet gateway", "ISP looking glass routing tables"],
                initial_likelihood=0.55 if isp_supporting else 0.25,
                coverage_score=len(isp_supporting) / max(1, len(all_ev_ids)),
            )
            hypotheses.append(h_isp)

            # 5. Hypothesis: QoS / Queue Policy Misconfiguration
            qos_supporting = self._find_supporting_evidence(
                evidence_list,
                keywords=["qos", "queue", "policy", "shaper", "policer", "priority", "dscp"],
            )
            h_qos = Hypothesis(
                hypothesis_id=f"hyp-qos-{uuid.uuid4().hex[:8]}",
                title="QoS Queue & Traffic Shaper Misconfiguration",
                description="Strict priority queues or policing policies dropping critical traffic classes erroneously.",
                category=HypothesisCategory.QOS_MISCONFIGURATION,
                supporting_evidence_ids=qos_supporting,
                missing_evidence_descriptions=["QoS class-map drop counters", "Router running configuration diff"],
                initial_likelihood=0.50 if qos_supporting else 0.20,
                coverage_score=len(qos_supporting) / max(1, len(all_ev_ids)),
            )
            hypotheses.append(h_qos)

            logger.info(
                f"HypothesisGenerator produced {len(hypotheses)} competing hypotheses "
                f"across {len(correlation.groups)} evidence groups."
            )
            return hypotheses

    def _find_supporting_evidence(
        self, evidence_list: Optional[List[ReasoningEvidence]], keywords: List[str]
    ) -> List[str]:
        """Match evidence items whose source, type, or payload match target keywords."""
        if not evidence_list:
            return []

        supporting: List[str] = []
        for ev in evidence_list:
            text_repr = f"{ev.source_agent} {ev.evidence_type} {str(ev.payload)}".lower()
            if any(kw in text_repr for kw in keywords):
                supporting.append(ev.evidence_id)

        return supporting
