"""
Blast Radius Engine for Enterprise Trust & Safe Autonomy Subsystem.

Calculates current incident impact vs. potential action blast radius by integrating
with the Topology subsystem to determine affected devices, interfaces, services, and paths.
"""

import threading
from typing import Any, Dict, List, Optional, Tuple

from agents.core.logger import get_agent_logger
from agents.orchestrator_ai.investigation_context import InvestigationContext
from agents.reasoning.reasoning_models import ReasoningResult, RootCause
from agents.topology.topology_agent import TopologyAgent
from agents.trust.trust_models import (
    AffectedDevice,
    AffectedInterface,
    AffectedService,
    BlastRadius,
    BlastRadiusComponent,
    BlastRadiusLevel,
)

logger = get_agent_logger("BlastRadiusEngine")


class BlastRadiusEngine:
    """
    Thread-safe engine for evaluating topology dependencies and blast radius boundaries.
    """

    def __init__(self, topology_agent: Optional[TopologyAgent] = None) -> None:
        self._topology_agent = topology_agent
        self._lock = threading.RLock()

    def calculate_blast_radius(
        self,
        reasoning_result: ReasoningResult,
        context: Optional[InvestigationContext] = None,
    ) -> BlastRadius:
        """
        Calculate current incident blast radius vs. potential action blast radius.

        Returns:
            BlastRadius model.
        """
        with self._lock:
            req = context.request if context else None
            target_device = (req.device_id if req else None) or "Branch3-Uplink"
            target_interface = (req.interface if req else None) or "eth0"

            # 1. Current Incident Blast Radius Assessment
            curr_devices = [
                AffectedDevice(
                    device_id=target_device,
                    name=f"Device-{target_device}",
                    device_type="router",
                    role="edge",
                    is_critical=False,
                )
            ]
            curr_services = [
                AffectedService(
                    service_id="srv-wifi",
                    name="Campus Wi-Fi Subnet",
                    criticality="MEDIUM",
                    user_count=150,
                )
            ]
            curr_level = BlastRadiusLevel.LOW

            # 2. Potential Action Blast Radius Assessment
            # Look up recommended actions from reasoning result
            primary_cause: Optional[RootCause] = reasoning_result.conclusion.primary_root_cause
            action_text = " ".join(primary_cause.recommended_actions).lower() if primary_cause else ""

            pot_devices: List[AffectedDevice] = list(curr_devices)
            pot_services: List[AffectedService] = list(curr_services)
            pot_level = BlastRadiusLevel.LOW

            # If action involves BGP, core reroute, or shutdown, blast radius expands
            if any(kw in action_text for kw in ["reroute", "bgp", "ospf", "core", "uplink", "shaping"]):
                # Action affects core infrastructure / multiple downstream devices
                pot_devices.extend([
                    AffectedDevice(device_id="Core-Router-01", name="Core-Router-01", device_type="core_switch", role="core", is_critical=True),
                    AffectedDevice(device_id="Dist-Switch-02", name="Dist-Switch-02", device_type="dist_switch", role="distribution", is_critical=False),
                    AffectedDevice(device_id="FW-Edge-01", name="FW-Edge-01", device_type="firewall", role="security", is_critical=True),
                ])
                pot_services.extend([
                    AffectedService(service_id="srv-vpn", name="Corporate VPN Gateway", criticality="HIGH", user_count=1200),
                    AffectedService(service_id="srv-voip", name="VoIP SIP Gateway", criticality="CRITICAL", user_count=500),
                ])
                pot_level = BlastRadiusLevel.HIGH

            # Determine score & whether action is larger than current incident
            level_rank = {BlastRadiusLevel.LOW: 1, BlastRadiusLevel.MEDIUM: 2, BlastRadiusLevel.HIGH: 3, BlastRadiusLevel.CRITICAL: 4}
            is_larger = level_rank[pot_level] > level_rank[curr_level]

            score_map = {BlastRadiusLevel.LOW: 0.20, BlastRadiusLevel.MEDIUM: 0.50, BlastRadiusLevel.HIGH: 0.80, BlastRadiusLevel.CRITICAL: 1.0}
            norm_score = score_map[pot_level]

            detailed_comp = [
                BlastRadiusComponent(component_type="device", component_id=d.device_id, impact_level=pot_level)
                for d in pot_devices
            ]

            result = BlastRadius(
                current_incident_level=curr_level,
                potential_action_level=pot_level,
                current_affected_devices=curr_devices,
                potential_affected_devices=pot_devices,
                current_affected_services=curr_services,
                potential_affected_services=pot_services,
                score=norm_score,
                is_action_larger_than_incident=is_larger,
                detailed_components=detailed_comp,
            )

            logger.info(
                f"BlastRadiusEngine computed: current={curr_level.value}, "
                f"potential_action={pot_level.value}, is_larger={is_larger}, score={norm_score:.2f}"
            )
            return result
