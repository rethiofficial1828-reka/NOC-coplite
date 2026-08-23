"""
Path Scoring Engine Module for Enterprise Intelligent Network Path & Provider Decision Engine.

Ranks candidate paths using deterministic, transparent weighted scoring across technical health,
predicted risk, SLA compliance, telemetry quality, topology independence, and economics.
"""

from typing import Dict, List, Optional

from agents.core.logger import get_agent_logger
from agents.path_decision.path_models import (
    EconomicEvaluationStatus,
    NetworkEconomics,
    PathEvaluation,
    PathScore,
    SLAStatus,
)

logger = get_agent_logger("PathScoringEngine")


class PathScoringEngine:
    """
    Ranks candidate network paths using configurable weighted scoring.
    """

    DEFAULT_WEIGHTS = {
        "health_weight": 0.20,
        "reliability_weight": 0.15,
        "risk_weight": 0.20,
        "latency_weight": 0.15,
        "packet_loss_weight": 0.10,
        "sla_weight": 0.05,
        "economics_weight": 0.05,
        "topology_weight": 0.10,
    }

    def __init__(self, custom_weights: Optional[Dict[str, float]] = None) -> None:
        self._weights = dict(self.DEFAULT_WEIGHTS)
        if custom_weights:
            self._weights.update(custom_weights)

        # Normalize weights to sum to 1.0
        total_w = sum(self._weights.values())
        if total_w > 0:
            for k in self._weights:
                self._weights[k] /= total_w

    @property
    def weights(self) -> Dict[str, float]:
        """Configured scoring weights."""
        return dict(self._weights)

    def rank_paths(
        self,
        evaluations: List[PathEvaluation],
        economics_list: Optional[List[NetworkEconomics]] = None,
    ) -> List[PathScore]:
        """
        Rank a list of PathEvaluations in descending order of total suitability score.

        Args:
            evaluations: List of PathEvaluation domain objects.
            economics_list: Optional list of NetworkEconomics per provider.

        Returns:
            List of PathScore sorted by rank (rank 1 = best candidate).
        """
        if not evaluations:
            return []

        econ_map = {e.provider_name: e for e in (economics_list or [])}
        scored_candidates: List[PathScore] = []

        w = self._weights

        for ev in evaluations:
            econ = econ_map.get(ev.provider_name)

            # Sub-score normalization (0 to 100)
            h_score = ev.health
            rel_score = ev.reliability
            risk_score = max(0.0, (1.0 - ev.failure_risk) * 100.0)
            lat_score = max(0.0, 100.0 - min(100.0, (ev.latency_ms / 200.0) * 100.0))
            loss_score = max(0.0, 100.0 - min(100.0, ev.packet_loss_percent * 10.0))

            if ev.sla_status == SLAStatus.COMPLIANT:
                sla_score = 100.0
            elif ev.sla_status == SLAStatus.UNKNOWN:
                sla_score = 60.0
            else:
                sla_score = 0.0

            topo_score = ev.topology_independence

            if econ and econ.economic_status == EconomicEvaluationStatus.EVALUATED:
                econ_score = min(100.0, max(0.0, float(econ.business_priority) * 10.0))
            else:
                econ_score = 50.0  # Neutral baseline when economics unavailable

            breakdown = {
                "health": round(h_score, 1),
                "reliability": round(rel_score, 1),
                "risk": round(risk_score, 1),
                "latency": round(lat_score, 1),
                "packet_loss": round(loss_score, 1),
                "sla": round(sla_score, 1),
                "topology": round(topo_score, 1),
                "economics": round(econ_score, 1),
            }

            total = (
                w["health_weight"] * h_score
                + w["reliability_weight"] * rel_score
                + w["risk_weight"] * risk_score
                + w["latency_weight"] * lat_score
                + w["packet_loss_weight"] * loss_score
                + w["sla_weight"] * sla_score
                + w["topology_weight"] * topo_score
                + w["economics_weight"] * econ_score
            )

            total_final = max(0.0, min(100.0, total))

            rationale = (
                f"Total score {total_final:.1f}/100 (Health={h_score:.1f}, "
                f"Latency={ev.latency_ms:.1f}ms, Loss={ev.packet_loss_percent:.1f}%, Risk={ev.failure_risk*100:.0f}%)"
            )

            scored_candidates.append(
                PathScore(
                    path_id=ev.path_id,
                    provider_name=ev.provider_name,
                    total_score=round(total_final, 1),
                    score_breakdown=breakdown,
                    rank=1,  # Temporary before sorting
                    rationale=rationale,
                )
            )

        # Sort descending by total score
        scored_candidates.sort(key=lambda s: s.total_score, reverse=True)

        # Assign explicit ranks
        for idx, ps in enumerate(scored_candidates, start=1):
            ps.rank = idx

        logger.info(
            f"PathScoringEngine ranked {len(scored_candidates)} candidate(s). "
            f"Top provider: '{scored_candidates[0].provider_name}' (Score: {scored_candidates[0].total_score:.1f})"
        )

        return scored_candidates
