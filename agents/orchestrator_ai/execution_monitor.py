"""
Execution Monitor for Enterprise AI Investigation Platform.

Tracks real-time execution status of investigation DAG nodes, execution durations,
parallelism factors, retries, resource consumption metrics, and confidence progression.
Exposes metrics for UI dashboard integration.
"""

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional, Set

from agents.core.logger import get_agent_logger
from agents.orchestrator_ai.investigation_models import ExecutionSummary

logger = get_agent_logger("ExecutionMonitor")


class ExecutionMonitor:
    """
    Thread-safe real-time performance and status monitor for investigation execution.
    """

    def __init__(self, request_id: str = "") -> None:
        self.request_id = request_id
        self._lock = threading.RLock()
        self._start_time: Optional[datetime] = None
        self._end_time: Optional[datetime] = None
        self._running_nodes: Set[str] = set()
        self._completed_nodes: Set[str] = set()
        self._failed_nodes: Set[str] = set()
        self._skipped_nodes: Set[str] = set()
        self._node_durations: Dict[str, float] = {}
        self._node_retries: Dict[str, int] = {}
        self._confidence_samples: List[Dict[str, Any]] = []

    def start_monitoring(self) -> None:
        """Mark start time of investigation execution."""
        with self._lock:
            self._start_time = datetime.now(timezone.utc)
            logger.debug(f"ExecutionMonitor started for request '{self.request_id}'")

    def stop_monitoring(self) -> None:
        """Mark end time of investigation execution."""
        with self._lock:
            self._end_time = datetime.now(timezone.utc)
            logger.debug(f"ExecutionMonitor stopped for request '{self.request_id}'")

    def on_node_started(self, node_id: str) -> None:
        """Record node start."""
        with self._lock:
            self._running_nodes.add(node_id)
            logger.debug(f"Monitor: node '{node_id}' started.")

    def on_node_completed(self, node_id: str, duration_ms: float) -> None:
        """Record successful node completion."""
        with self._lock:
            self._running_nodes.discard(node_id)
            self._completed_nodes.add(node_id)
            self._node_durations[node_id] = duration_ms
            logger.debug(f"Monitor: node '{node_id}' completed in {duration_ms:.2f}ms")

    def on_node_failed(self, node_id: str, duration_ms: float, is_retry: bool = False) -> None:
        """Record node failure or retry attempt."""
        with self._lock:
            if is_retry:
                self._node_retries[node_id] = self._node_retries.get(node_id, 0) + 1
            else:
                self._running_nodes.discard(node_id)
                self._failed_nodes.add(node_id)
                self._node_durations[node_id] = duration_ms
            logger.debug(f"Monitor: node '{node_id}' failed (duration={duration_ms:.2f}ms, retry={is_retry})")

    def on_node_skipped(self, node_id: str, reason: str = "") -> None:
        """Record node skipped."""
        with self._lock:
            self._running_nodes.discard(node_id)
            self._skipped_nodes.add(node_id)
            logger.debug(f"Monitor: node '{node_id}' skipped. Rationale: {reason}")

    def record_confidence(self, confidence: float, agent_name: str) -> None:
        """Record confidence checkpoint sample."""
        with self._lock:
            self._confidence_samples.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "agent": agent_name,
                "confidence": confidence,
            })

    def get_elapsed_ms(self) -> float:
        """Calculate total wall-clock elapsed time in milliseconds."""
        with self._lock:
            if not self._start_time:
                return 0.0
            end = self._end_time or datetime.now(timezone.utc)
            return (end - self._start_time).total_seconds() * 1000.0

    def get_parallelism_factor(self) -> float:
        """
        Calculate parallelism factor = sum(individual node durations) / wall_clock_duration.
        """
        with self._lock:
            total_node_time = sum(self._node_durations.values())
            wall_clock = self.get_elapsed_ms()
            if wall_clock <= 0.0 or total_node_time <= 0.0:
                return 1.0
            return max(1.0, total_node_time / wall_clock)

    def to_summary(self) -> ExecutionSummary:
        """Generate ExecutionSummary object."""
        with self._lock:
            total = len(self._completed_nodes) + len(self._failed_nodes) + len(self._skipped_nodes) + len(self._running_nodes)
            return ExecutionSummary(
                total_agents=total,
                executed_agents=len(self._completed_nodes),
                skipped_agents=len(self._skipped_nodes),
                failed_agents=len(self._failed_nodes),
                total_duration_ms=self.get_elapsed_ms(),
                parallelism_factor=self.get_parallelism_factor(),
            )

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Expose structured dictionary for dashboard integration."""
        with self._lock:
            return {
                "request_id": self.request_id,
                "running_count": len(self._running_nodes),
                "completed_count": len(self._completed_nodes),
                "failed_count": len(self._failed_nodes),
                "skipped_count": len(self._skipped_nodes),
                "durations_ms": dict(self._node_durations),
                "retries": dict(self._node_retries),
                "total_wall_time_ms": self.get_elapsed_ms(),
                "parallelism_factor": self.get_parallelism_factor(),
                "confidence_samples": list(self._confidence_samples),
            }
