"""
Path Simulation Engine Module for Enterprise Intelligent Network Path & Provider Decision Engine.

Simulates network path performance under various scenarios (current path, candidate failover,
traffic surge, provider degradation, no-action impact) and explicitly labels data origin.
Guarantees simulation outputs are never confused with observed live telemetry.
"""

from typing import Optional

from agents.core.logger import get_agent_logger
from agents.path_decision.path_models import (
    DataOrigin,
    PathCandidate,
    PathEvaluation,
    PathSimulationResult,
    SimulationScenario,
)

logger = get_agent_logger("PathSimulationEngine")


class PathSimulationEngine:
    """
    Simulates network path performance across standard operational scenarios.
    """

    def simulate_scenario(
        self,
        candidate: PathCandidate,
        evaluation: PathEvaluation,
        scenario: SimulationScenario,
    ) -> PathSimulationResult:
        """
        Execute deterministic path simulation for a scenario.

        Args:
            candidate: PathCandidate target.
            evaluation: PathEvaluation object.
            scenario: SimulationScenario enum.

        Returns:
            PathSimulationResult object with explicit origin labels.
        """
        if scenario == SimulationScenario.CURRENT_PATH and candidate.is_primary:
            return PathSimulationResult(
                scenario=scenario,
                path_id=candidate.path_id,
                provider_name=candidate.provider_name,
                data_origin=DataOrigin.OBSERVED,
                expected_latency_ms=evaluation.latency_ms,
                expected_packet_loss_percent=evaluation.packet_loss_percent,
                expected_utilization_percent=evaluation.utilization_percent,
                expected_failure_risk=evaluation.failure_risk,
                expected_impact_summary=f"Observed live telemetry on primary provider '{candidate.provider_name}'.",
                display_label="OBSERVED",
            )

        elif scenario in (SimulationScenario.ALTERNATIVE_PATH, SimulationScenario.FAILOVER_SCENARIO):
            # Estimated candidate path metrics
            sim_lat = max(10.0, evaluation.latency_ms * 0.2) if evaluation.latency_ms > 50 else evaluation.latency_ms
            sim_loss = max(0.1, evaluation.packet_loss_percent * 0.1) if evaluation.packet_loss_percent > 1.0 else evaluation.packet_loss_percent
            sim_util = min(60.0, evaluation.utilization_percent * 0.5)
            sim_risk = min(0.10, evaluation.failure_risk * 0.1)

            summary = (
                f"Simulated failover to alternative provider '{candidate.provider_name}': "
                f"expected latency ~{sim_lat:.1f}ms (vs {evaluation.latency_ms:.1f}ms), "
                f"loss ~{sim_loss:.2f}% (vs {evaluation.packet_loss_percent:.1f}%)."
            )

            return PathSimulationResult(
                scenario=scenario,
                path_id=candidate.path_id,
                provider_name=candidate.provider_name,
                data_origin=DataOrigin.SIMULATED,
                expected_latency_ms=round(sim_lat, 1),
                expected_packet_loss_percent=round(sim_loss, 2),
                expected_utilization_percent=round(sim_util, 1),
                expected_failure_risk=round(sim_risk, 3),
                expected_impact_summary=summary,
                display_label="SIMULATED / ESTIMATED",
            )

        elif scenario == SimulationScenario.TRAFFIC_SURGE:
            surge_util = min(100.0, evaluation.utilization_percent * 1.4)
            surge_lat = evaluation.latency_ms + (20.0 if surge_util > 85 else 5.0)
            surge_loss = evaluation.packet_loss_percent + (2.5 if surge_util > 90 else 0.2)
            surge_risk = min(1.0, evaluation.failure_risk + 0.25)

            return PathSimulationResult(
                scenario=scenario,
                path_id=candidate.path_id,
                provider_name=candidate.provider_name,
                data_origin=DataOrigin.SIMULATED,
                expected_latency_ms=round(surge_lat, 1),
                expected_packet_loss_percent=round(surge_loss, 2),
                expected_utilization_percent=round(surge_util, 1),
                expected_failure_risk=round(surge_risk, 3),
                expected_impact_summary=f"Simulated +40% traffic surge on '{candidate.provider_name}'.",
                display_label="SIMULATED / ESTIMATED",
            )

        elif scenario in (SimulationScenario.PROVIDER_DEGRADATION, SimulationScenario.NO_ACTION):
            deg_lat = evaluation.latency_ms + 80.0
            deg_loss = evaluation.packet_loss_percent + 6.0
            deg_util = min(100.0, evaluation.utilization_percent + 15.0)
            deg_risk = min(1.0, max(0.90, evaluation.failure_risk + 0.35))

            return PathSimulationResult(
                scenario=scenario,
                path_id=candidate.path_id,
                provider_name=candidate.provider_name,
                data_origin=DataOrigin.PREDICTED,
                expected_latency_ms=round(deg_lat, 1),
                expected_packet_loss_percent=round(deg_loss, 2),
                expected_utilization_percent=round(deg_util, 1),
                expected_failure_risk=round(deg_risk, 3),
                expected_impact_summary=f"Predicted impact if no failover action is taken on degrading provider '{candidate.provider_name}'.",
                display_label="SIMULATED / ESTIMATED",
            )

        else:
            return PathSimulationResult(
                scenario=scenario,
                path_id=candidate.path_id,
                provider_name=candidate.provider_name,
                data_origin=DataOrigin.UNKNOWN,
                expected_latency_ms=evaluation.latency_ms,
                expected_packet_loss_percent=evaluation.packet_loss_percent,
                expected_utilization_percent=evaluation.utilization_percent,
                expected_failure_risk=evaluation.failure_risk,
                expected_impact_summary="Default simulation baseline.",
                display_label="SIMULATED / ESTIMATED",
            )
