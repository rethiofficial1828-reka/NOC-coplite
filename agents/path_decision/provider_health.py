"""
Provider Health Engine Module for Enterprise Intelligent Network Path & Provider Decision Engine.

Calculates normalized 0-100 health index for network providers and WAN paths based on
real telemetry, XGBoost predictive failure risk, interface errors/drops/flaps,
and open incidents. Explicitly tracks metric availability and adjusts confidence.
"""

from typing import Any, Dict, List, Optional

from agents.core.logger import get_agent_logger
from agents.path_decision.path_models import ProviderHealthScore

logger = get_agent_logger("ProviderHealthEngine")


class ProviderHealthEngine:
    """
    Evaluates provider operational health deterministically from live telemetry metrics,
    ML failure risk, and incident history.
    """

    def calculate_health(
        self,
        provider_name: str,
        interface_key: str,
        telemetry_metrics: Optional[Dict[str, float]] = None,
        xgboost_risk: float = 0.0,
        active_incidents: int = 0,
        evidence_freshness_sec: float = 0.0,
        collector_health_status: str = "HEALTHY",
    ) -> ProviderHealthScore:
        """
        Compute transparent health index (0-100) and confidence rating.

        Args:
            provider_name: Human-readable provider or WAN link name.
            interface_key: Monitored interface identifier.
            telemetry_metrics: Map of raw telemetry key-values (latency, packet_loss, etc.).
            xgboost_risk: XGBoost predicted failure risk (0.0 to 1.0).
            active_incidents: Number of open incidents impacting this provider.
            evidence_freshness_sec: Age of telemetry data in seconds.
            collector_health_status: Health status of telemetry collector ("HEALTHY", "DEGRADED", "OFFLINE").

        Returns:
            ProviderHealthScore object with transparent score breakdown and rationale.
        """
        metrics = telemetry_metrics or {}
        availability_map: Dict[str, bool] = {}
        rationale: List[str] = []

        base_score = 100.0
        confidence = 1.0

        # Required operational metrics to check
        core_metric_keys = [
            "latency",
            "packet_loss",
            "jitter",
            "utilization",
            "drops",
            "routing_flaps",
            "interface_errors",
        ]

        for k in core_metric_keys:
            availability_map[k] = k in metrics and metrics[k] is not None

        # 1. Latency penalty
        if availability_map["latency"]:
            lat = float(metrics["latency"])
            if lat > 30.0:
                penalty = min(35.0, (lat - 30.0) * 0.4)
                base_score -= penalty
                rationale.append(f"High round-trip latency ({lat:.1f} ms, -{penalty:.1f} pts)")
        else:
            confidence -= 0.15
            rationale.append("Latency telemetry unavailable (-15% confidence)")

        # 2. Packet Loss penalty
        if availability_map["packet_loss"]:
            loss = float(metrics["packet_loss"])
            if loss > 0.1:
                penalty = min(45.0, loss * 5.0)
                base_score -= penalty
                rationale.append(f"Elevated packet loss ({loss:.2f}%, -{penalty:.1f} pts)")
        else:
            confidence -= 0.15
            rationale.append("Packet loss telemetry unavailable (-15% confidence)")

        # 3. Jitter penalty
        if availability_map["jitter"]:
            jit = float(metrics["jitter"])
            if jit > 5.0:
                penalty = min(15.0, (jit - 5.0) * 1.2)
                base_score -= penalty
                rationale.append(f"High jitter ({jit:.1f} ms, -{penalty:.1f} pts)")
        else:
            confidence -= 0.10
            rationale.append("Jitter telemetry unavailable (-10% confidence)")

        # 4. Bandwidth Utilization penalty
        if availability_map["utilization"]:
            util = float(metrics["utilization"])
            if util > 80.0:
                penalty = min(25.0, (util - 80.0) * 1.25)
                base_score -= penalty
                rationale.append(f"High link utilization ({util:.1f}%, -{penalty:.1f} pts)")
        else:
            confidence -= 0.10

        # 5. Interface Errors, Drops & Flaps penalty
        drops = float(metrics.get("drops", 0.0)) if availability_map["drops"] else 0.0
        flaps = float(metrics.get("routing_flaps", 0.0)) if availability_map["routing_flaps"] else 0.0
        errors = float(metrics.get("interface_errors", 0.0)) if availability_map["interface_errors"] else 0.0

        if drops > 0.0 or flaps > 0.0 or errors > 0.0:
            error_penalty = min(25.0, (drops * 2.0) + (flaps * 8.0) + (errors * 1.5))
            base_score -= error_penalty
            rationale.append(
                f"Interface instability (drops={drops:.1f}/s, flaps={int(flaps)}, errors={int(errors)}, -{error_penalty:.1f} pts)"
            )

        # 6. XGBoost ML Failure Risk Penalty
        if xgboost_risk > 0.1:
            risk_penalty = min(40.0, xgboost_risk * 40.0)
            base_score -= risk_penalty
            rationale.append(f"XGBoost predicted failure risk ({xgboost_risk*100:.0f}%, -{risk_penalty:.1f} pts)")

        # 7. Active Incidents Penalty
        if active_incidents > 0:
            inc_penalty = min(30.0, active_incidents * 15.0)
            base_score -= inc_penalty
            rationale.append(f"Active incident impact ({active_incidents} incident(s), -{inc_penalty:.1f} pts)")

        # 8. Freshness & Collector Health Adjustments
        if evidence_freshness_sec > 60.0:
            confidence -= 0.20
            rationale.append(f"Telemetry stale ({evidence_freshness_sec:.0f}s old, -20% confidence)")

        if collector_health_status.upper() != "HEALTHY":
            confidence -= 0.25
            rationale.append(f"Collector status: {collector_health_status} (-25% confidence)")

        final_health = max(0.0, min(100.0, base_score))
        final_confidence = max(0.1, min(1.0, confidence))

        if not rationale:
            rationale.append("Provider telemetry and performance within nominal thresholds.")

        logger.debug(
            f"ProviderHealthEngine evaluated '{provider_name}' ({interface_key}): "
            f"Health={final_health:.1f}/100, Confidence={final_confidence:.2f}"
        )

        return ProviderHealthScore(
            provider_name=provider_name,
            health_score=round(final_health, 1),
            metrics_available=availability_map,
            metric_values=metrics,
            xgboost_risk=round(xgboost_risk, 4),
            active_incidents=active_incidents,
            evidence_freshness_sec=round(evidence_freshness_sec, 2),
            collector_health_status=collector_health_status,
            confidence=round(final_confidence, 2),
            rationale=rationale,
        )
