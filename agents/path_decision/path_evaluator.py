"""
Path Evaluation Engine Module for Enterprise Intelligent Network Path & Provider Decision Engine.

Evaluates each candidate network path across 14 critical dimensions:
1. Health, 2. Reliability, 3. Predicted failure risk, 4. Latency, 5. Packet loss,
6. Jitter, 7. Capacity, 8. Utilization, 9. SLA status, 10. Topology independence,
11. Blast radius, 12. Historical reliability, 13. Evidence freshness, 14. Collector confidence.
"""

from typing import Any, Dict, Optional

from agents.core.logger import get_agent_logger
from agents.path_decision.path_models import (
    PathCandidate,
    PathEvaluation,
    ProviderHealthScore,
    SLAStatus,
)

logger = get_agent_logger("PathEvaluationEngine")


class PathEvaluationEngine:
    """
    Evaluates candidate network paths across all 14 required dimensions into a
    structured PathEvaluation domain model.
    """

    def evaluate_path(
        self,
        candidate: PathCandidate,
        health_score: ProviderHealthScore,
        blast_radius_score: float = 0.0,
        historical_reliability: float = 100.0,
    ) -> PathEvaluation:
        """
        Produce structured PathEvaluation across all 14 technical and operational dimensions.

        Args:
            candidate: PathCandidate object.
            health_score: ProviderHealthScore computed by ProviderHealthEngine.
            blast_radius_score: Operational blast radius score (0.0 to 1.0).
            historical_reliability: Historical reliability rating percentage (0 to 100).

        Returns:
            PathEvaluation instance.
        """
        metrics = health_score.metric_values

        lat = float(metrics.get("latency", 25.0))
        loss = float(metrics.get("packet_loss", 0.1))
        jit = float(metrics.get("jitter", 2.0))
        util = float(metrics.get("utilization", 45.0))

        # Check SLA threshold from candidate metadata or defaults
        max_lat_sla = float(candidate.metadata.get("sla_latency_max_ms", 100.0))
        max_loss_sla = float(candidate.metadata.get("sla_loss_max_percent", 2.0))

        if lat > max_lat_sla or loss > max_loss_sla:
            sla_status = SLAStatus.VIOLATED
        elif not health_score.metrics_available.get("latency", True):
            sla_status = SLAStatus.UNKNOWN
        else:
            sla_status = SLAStatus.COMPLIANT

        # Topology independence score
        topology_independence = 100.0 if candidate.is_independent else 50.0
        if candidate.single_points_of_failure:
            topology_independence = max(20.0, topology_independence - (len(candidate.single_points_of_failure) * 20.0))

        # Reliability index calculation
        rel_base = health_score.health_score * 0.5 + historical_reliability * 0.5
        rel_penalty = (loss * 8.0) + (1.0 - health_score.confidence) * 20.0
        reliability = max(0.0, min(100.0, rel_base - rel_penalty))

        details: Dict[str, Any] = {
            "is_primary": candidate.is_primary,
            "wan_interface": candidate.wan_interface,
            "hop_count": len(candidate.hops),
            "single_points_of_failure": candidate.single_points_of_failure,
            "dependencies": candidate.dependencies,
            "metrics_available": health_score.metrics_available,
            "health_rationale": health_score.rationale,
        }

        logger.debug(
            f"PathEvaluationEngine evaluated '{candidate.provider_name}': "
            f"Health={health_score.health_score:.1f}, Reliability={reliability:.1f}, SLA={sla_status.value}"
        )

        return PathEvaluation(
            path_id=candidate.path_id,
            provider_name=candidate.provider_name,
            health=health_score.health_score,
            reliability=round(reliability, 1),
            failure_risk=health_score.xgboost_risk,
            latency_ms=round(lat, 1),
            packet_loss_percent=round(loss, 2),
            jitter_ms=round(jit, 1),
            capacity_mbps=candidate.bandwidth_mbps,
            utilization_percent=round(util, 1),
            sla_status=sla_status,
            topology_independence=round(topology_independence, 1),
            blast_radius_score=round(blast_radius_score, 3),
            historical_reliability=round(historical_reliability, 1),
            evidence_freshness_sec=health_score.evidence_freshness_sec,
            collector_confidence=health_score.confidence,
            evaluation_details=details,
        )
