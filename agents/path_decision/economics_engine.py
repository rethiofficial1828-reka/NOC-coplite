"""
Network Economics Engine Module for Enterprise Intelligent Network Path & Provider Decision Engine.

Evaluates financial bandwidth costs, SLA penalty terms, and failover economics.
Guarantees NO fake monetary values are invented. If pricing telemetry is missing,
returns UNKNOWN economic status with transparent explanation.
"""

from typing import Any, Dict, Optional

from agents.core.logger import get_agent_logger
from agents.path_decision.path_models import (
    EconomicEvaluationStatus,
    NetworkEconomics,
    PathCandidate,
)

logger = get_agent_logger("NetworkEconomicsEngine")


class NetworkEconomicsEngine:
    """
    Evaluates provider pricing, committed bandwidth, overage rates, and failover economics.
    """

    def evaluate_economics(
        self,
        candidate: PathCandidate,
        economic_config: Optional[Dict[str, Any]] = None,
    ) -> NetworkEconomics:
        """
        Evaluate real economic attributes for a candidate path.

        Args:
            candidate: PathCandidate instance.
            economic_config: Optional dict containing pricing and commit terms.

        Returns:
            NetworkEconomics domain model.
        """
        cfg = economic_config or candidate.metadata.get("economics", {})

        if not cfg or not isinstance(cfg, dict):
            logger.debug(f"No economic data available for provider '{candidate.provider_name}'")
            return NetworkEconomics(
                provider_name=candidate.provider_name,
                economic_status=EconomicEvaluationStatus.UNKNOWN,
                explanation=(
                    "Network economics could not be evaluated because provider pricing data is unavailable."
                ),
            )

        # Parse real pricing attributes if present
        bw_cost = cfg.get("bandwidth_cost_per_gb")
        monthly_cost = cfg.get("provider_monthly_cost")
        committed_bw = cfg.get("committed_bandwidth_mbps")
        overage_cost = cfg.get("overage_cost_per_gb")
        sla_penalty = cfg.get("sla_penalty_rate")
        failover_cost = cfg.get("estimated_failover_cost")
        capacity_avail = cfg.get("capacity_available_mbps", candidate.bandwidth_mbps)
        priority = int(cfg.get("business_priority", 5))

        has_valid_data = any(
            v is not None
            for v in [bw_cost, monthly_cost, committed_bw, overage_cost, sla_penalty, failover_cost]
        )

        if not has_valid_data:
            return NetworkEconomics(
                provider_name=candidate.provider_name,
                economic_status=EconomicEvaluationStatus.UNKNOWN,
                business_priority=priority,
                explanation=(
                    "Network economics could not be evaluated because provider pricing data is unavailable."
                ),
            )

        logger.info(f"NetworkEconomicsEngine evaluated provider '{candidate.provider_name}' successfully.")

        return NetworkEconomics(
            provider_name=candidate.provider_name,
            economic_status=EconomicEvaluationStatus.EVALUATED,
            bandwidth_cost_per_gb=float(bw_cost) if bw_cost is not None else None,
            provider_monthly_cost=float(monthly_cost) if monthly_cost is not None else None,
            committed_bandwidth_mbps=float(committed_bw) if committed_bw is not None else None,
            overage_cost_per_gb=float(overage_cost) if overage_cost is not None else None,
            sla_penalty_rate=float(sla_penalty) if sla_penalty is not None else None,
            estimated_failover_cost=float(failover_cost) if failover_cost is not None else None,
            capacity_available_mbps=float(capacity_avail) if capacity_avail is not None else None,
            business_priority=priority,
            explanation=f"Evaluated provider pricing (priority {priority}).",
        )
