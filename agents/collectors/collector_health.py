"""
Collector Health Monitoring & Metrics Aggregator.

Tracks operational availability, collection latency, success/failure counts,
consecutive failure streaks, and exposes formatted health metrics for the Streamlit dashboard.
"""

from typing import Any, Dict, List
from agents.collectors.collector_base import CollectorBase
from agents.collectors.collector_models import CollectorHealth, CollectorState


class CollectorHealthMonitor:
    """
    Health Monitoring and Metrics Aggregator for Telemetry Collectors.
    """

    def __init__(self, registry_provider: Any = None) -> None:
        """
        Initialize CollectorHealthMonitor.

        Args:
            registry_provider: Object or callable returning registered collectors.
        """
        self._registry_provider = registry_provider

    def get_collector_health_snapshots(self, collectors: List[CollectorBase]) -> List[CollectorHealth]:
        """
        Extract CollectorHealth snapshots from a list of collectors.

        Args:
            collectors: List of CollectorBase instances.

        Returns:
            List of CollectorHealth snapshots.
        """
        return [c.health() for c in collectors]

    def calculate_aggregate_metrics(self, health_snapshots: List[CollectorHealth]) -> Dict[str, Any]:
        """
        Calculate overall system-wide telemetry ingestion health metrics.

        Args:
            health_snapshots: List of CollectorHealth objects.

        Returns:
            Summary dictionary.
        """
        if not health_snapshots:
            return {
                "total_collectors": 0,
                "active_collectors": 0,
                "degraded_collectors": 0,
                "failed_collectors": 0,
                "overall_availability_percent": 100.0,
                "total_packets_collected": 0,
                "avg_system_latency_ms": 0.0,
                "healthy_ratio": 1.0,
            }

        total = len(health_snapshots)
        active = sum(1 for h in health_snapshots if h.state in (CollectorState.READY, CollectorState.RUNNING))
        degraded = sum(1 for h in health_snapshots if h.state == CollectorState.DEGRADED)
        failed = sum(1 for h in health_snapshots if h.state == CollectorState.FAILED or not h.is_healthy)

        total_packets = sum(h.packets_collected for h in health_snapshots)
        total_attempts = sum(h.total_collections for h in health_snapshots)
        total_successes = sum(h.successful_collections for h in health_snapshots)

        overall_availability = (total_successes / total_attempts * 100.0) if total_attempts > 0 else 100.0

        latencies = [h.avg_latency_ms for h in health_snapshots if h.total_collections > 0]
        avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0

        healthy_ratio = (total - failed) / total if total > 0 else 1.0

        return {
            "total_collectors": total,
            "active_collectors": active,
            "degraded_collectors": degraded,
            "failed_collectors": failed,
            "overall_availability_percent": round(overall_availability, 2),
            "total_packets_collected": total_packets,
            "avg_system_latency_ms": round(avg_latency, 2),
            "healthy_ratio": round(healthy_ratio, 2),
        }

    def to_dashboard_metrics(self, collectors: List[CollectorBase]) -> Dict[str, Any]:
        """
        Format metrics specifically for display on the Streamlit NOC Dashboard.

        Args:
            collectors: List of CollectorBase instances.

        Returns:
            Structured dictionary for dashboard components.
        """
        snapshots = self.get_collector_health_snapshots(collectors)
        summary = self.calculate_aggregate_metrics(snapshots)

        collector_details = []
        for h in snapshots:
            collector_details.append(
                {
                    "collector_id": h.collector_id,
                    "name": h.collector_name,
                    "state": h.state.value,
                    "is_healthy": h.is_healthy,
                    "total_collections": h.total_collections,
                    "successful": h.successful_collections,
                    "failed": h.failed_collections,
                    "consecutive_failures": h.consecutive_failures,
                    "last_latency_ms": round(h.last_latency_ms, 2),
                    "avg_latency_ms": round(h.avg_latency_ms, 2),
                    "availability_percent": round(h.availability_percent, 2),
                    "packets_collected": h.packets_collected,
                    "last_error": h.last_error or "None",
                    "last_success": (
                        h.last_success_timestamp.isoformat() if h.last_success_timestamp else "N/A"
                    ),
                }
            )

        return {
            "summary": summary,
            "collectors": collector_details,
        }
