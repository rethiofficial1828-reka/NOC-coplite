"""
Adaptive Path Scoring Engine Module for Adaptive Multi-Provider Failover Subsystem.

Extends PathScoringEngine from Sprint 17 by integrating temporal trend direction, failure risk,
oscillation risk, and provider stickiness weights into path ranking decisions.
"""

from typing import Dict, List, Optional

from agents.core.logger import get_agent_logger
from agents.adaptive_failover.adaptive_models import ProviderHealthSnapshot
from agents.path_decision.path_scoring import PathScoringEngine

logger = get_agent_logger("AdaptivePathScoringEngine")


class AdaptivePathScoringEngine:
    """
    Adaptive Path Scoring Engine considering health trends, failure probabilities, and stability.
    """

    def __init__(self, base_scoring_engine: Optional[PathScoringEngine] = None) -> None:
        self._base_engine = base_scoring_engine or PathScoringEngine()

    def score_adaptive_providers(
        self,
        provider_snapshots: List[ProviderHealthSnapshot],
        active_provider_name: Optional[str] = None,
        stickiness_weight: float = 15.0,
    ) -> List[ProviderHealthSnapshot]:
        """
        Rank candidate provider snapshots considering temporal health trends and stability.

        Args:
            provider_snapshots: List of ProviderHealthSnapshot objects.
            active_provider_name: Currently active provider name.
            stickiness_weight: Bonus points awarded to active provider to prevent micro-switching.

        Returns:
            Sorted list of ProviderHealthSnapshot objects (highest adaptive score first).
        """
        scored_items: List[tuple[float, ProviderHealthSnapshot]] = []

        for p in provider_snapshots:
            base_score = p.health_score

            # 1. Trend Penalty/Bonus
            trend_adj = 0.0
            if p.health_trend == "RAPIDLY_DEGRADED":
                trend_adj = -30.0
            elif p.health_trend == "DEGRADED":
                trend_adj = -15.0
            elif p.health_trend == "IMPROVING":
                trend_adj = 10.0

            # 2. Failure Risk Penalty
            risk_penalty = p.failure_risk * 40.0

            # 3. Active Provider Stickiness Bonus
            stickiness_bonus = stickiness_weight if (active_provider_name and p.provider_name == active_provider_name) else 0.0

            adaptive_score = max(0.0, min(100.0, base_score + trend_adj - risk_penalty + stickiness_bonus))
            scored_items.append((adaptive_score, p))

            logger.debug(
                f"AdaptivePathScoring: '{p.provider_name}' -> Base={base_score:.1f}, "
                f"TrendAdj={trend_adj:.1f}, RiskPen={risk_penalty:.1f}, AdaptiveScore={adaptive_score:.1f}"
            )

        # Sort descending by adaptive score
        scored_items.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored_items]
