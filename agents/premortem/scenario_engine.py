"""
Future Scenario Engine for Enterprise Pre-Mortem Subsystem.

Simulates what-if scenarios (baseline persistence, traffic surge, path degradation,
remediation applied vs. no remediation applied) clearly distinguishing simulation from execution.
"""

import threading
from typing import Any, Dict, List, Optional
import uuid

from agents.core.logger import get_agent_logger
from agents.premortem.premortem_models import (
    FutureScenario,
    ObservationType,
    PreMortemSeverity,
    ScenarioEvidence,
    ScenarioType,
)

logger = get_agent_logger("FutureScenarioEngine")


class FutureScenarioEngine:
    """
    Thread-safe engine for evaluating what-if future-state scenario simulations.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def generate_scenarios(
        self,
        target_device: str = "Router-A",
        current_utilization: float = 95.0,
        current_packet_loss: float = 8.0,
    ) -> List[FutureScenario]:
        """
        Generate candidate future scenarios for current incident state.

        Returns:
            List of FutureScenario models.
        """
        with self._lock:
            scenarios: List[FutureScenario] = []

            # 1. Scenario A: Baseline Persistence (Do Nothing)
            scenarios.append(
                FutureScenario(
                    scenario_id=str(uuid.uuid4()),
                    scenario_type=ScenarioType.BASELINE_PERSISTENCE,
                    description="Current condition persists without operator intervention.",
                    trigger_conditions=["Utilization remains > 90% for 10 minutes"],
                    expected_signals=[
                        "Packet loss increases from 8% to 15%",
                        "Latency spikes to > 75ms",
                        "Dependent VoIP & VPN services experience degradation",
                    ],
                    affected_devices=[target_device, "Dist-Switch-01", "Core-Router-01"],
                    affected_services=["Corporate VPN", "VoIP SIP Gateway"],
                    affected_paths=["Path Router-A -> Router-B -> Branch"],
                    estimated_probability=0.85,
                    severity=PreMortemSeverity.HIGH,
                    estimated_time_to_impact_minutes=10.0,
                    confidence=0.88,
                    evidence=[
                        ScenarioEvidence(
                            source="TelemetryAgent",
                            observation_type=ObservationType.OBSERVED,
                            description=f"Current bandwidth utilization is {current_utilization}%",
                        ),
                        ScenarioEvidence(
                            source="PredictionAgent",
                            observation_type=ObservationType.PREDICTED,
                            description="Failure risk score projected to reach 0.95 within 15 minutes",
                        ),
                    ],
                    mitigation_options=[
                        "Apply egress rate-limiting on non-critical VLANs",
                        "Enable secondary link path reroute",
                    ],
                )
            )

            # 2. Scenario B: Traffic Surge / Escalation
            scenarios.append(
                FutureScenario(
                    scenario_id=str(uuid.uuid4()),
                    scenario_type=ScenarioType.TRAFFIC_SURGE,
                    description="Off-peak to peak hour transition increases ingress load by 20%.",
                    trigger_conditions=["Peak business hour traffic surge at 14:00 UTC"],
                    expected_signals=[
                        "Utilization hits 100% capacity",
                        "Severe queue drop and interface error burst",
                    ],
                    affected_devices=[target_device, "FW-Edge-01"],
                    affected_services=["All Campus Traffic"],
                    affected_paths=["All Uplinks"],
                    estimated_probability=0.65,
                    severity=PreMortemSeverity.CRITICAL,
                    estimated_time_to_impact_minutes=5.0,
                    confidence=0.80,
                    evidence=[
                        ScenarioEvidence(
                            source="HistoricalMatcher",
                            observation_type=ObservationType.HISTORICAL,
                            description="Historical incidents show peak-hour escalation pattern in 75% of occurrences",
                        ),
                    ],
                    mitigation_options=["Pre-emptively throttle backup jobs"],
                )
            )

            # 3. Scenario C: Remediation Applied (Traffic Shaping / Reroute)
            scenarios.append(
                FutureScenario(
                    scenario_id=str(uuid.uuid4()),
                    scenario_type=ScenarioType.REMEDIATION_APPLIED,
                    description="Recommended QoS traffic shaping policy is applied to egress port.",
                    trigger_conditions=["Operator approves remediation plan"],
                    expected_signals=[
                        "Utilization drops to 65%",
                        "Packet loss recovers to < 0.5%",
                        "Latency normalizes to 12ms",
                    ],
                    affected_devices=[target_device],
                    affected_services=["Non-critical Video Streaming (Throttled)"],
                    affected_paths=["Path Router-A -> Router-B -> Branch"],
                    estimated_probability=0.90,
                    severity=PreMortemSeverity.LOW,
                    estimated_time_to_impact_minutes=2.0,
                    confidence=0.92,
                    evidence=[
                        ScenarioEvidence(
                            source="ReasoningAgent",
                            observation_type=ObservationType.INFERRED,
                            description="Remediation plan verified by safe autonomy policy engine",
                        ),
                    ],
                    mitigation_options=["Monitor post-remediation telemetry"],
                )
            )

            logger.info(f"FutureScenarioEngine generated {len(scenarios)} future scenarios")
            return scenarios
