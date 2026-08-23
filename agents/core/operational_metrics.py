"""
Operational Metrics Collector for NOC Copilot.

Provides thread-safe, structured operational metrics collection for diagnostics,
observability, latency tracking, incident counters, and audit reporting.
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import threading
import time
from typing import Any, Dict, List, Optional


@dataclass
class LatencySample:
    operation: str
    duration_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "SUCCESS"
    details: Dict[str, Any] = field(default_factory=dict)


class OperationalMetrics:
    """
    Centralized operational metrics registry.
    Thread-safe singleton providing counters, latencies, and summary telemetry.
    """

    _instance: Optional["OperationalMetrics"] = None
    _lock = threading.Lock()

    def __init__(self, max_samples: int = 500) -> None:
        self._max_samples = max_samples
        self._mutex = threading.Lock()
        
        # Counters
        self.investigation_request_count: int = 0
        self.incident_count: int = 0
        self.rollback_count: int = 0
        self.rollback_success_count: int = 0
        self.rollback_failure_count: int = 0
        self.ollama_request_count: int = 0
        self.ollama_failure_count: int = 0
        
        # Latency samples (bounded deques)
        self.prediction_latencies: deque[float] = deque(maxlen=max_samples)
        self.reasoning_latencies: deque[float] = deque(maxlen=max_samples)
        self.trust_latencies: deque[float] = deque(maxlen=max_samples)
        self.path_decision_latencies: deque[float] = deque(maxlen=max_samples)
        self.failover_latencies: deque[float] = deque(maxlen=max_samples)
        self.verification_latencies: deque[float] = deque(maxlen=max_samples)
        
        # General history log
        self._history: deque[LatencySample] = deque(maxlen=max_samples)
        self.started_at: datetime = datetime.now(timezone.utc)

    @classmethod
    def get_instance(cls) -> "OperationalMetrics":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def record_investigation(self) -> None:
        with self._mutex:
            self.investigation_request_count += 1

    def record_incident(self) -> None:
        with self._mutex:
            self.incident_count += 1

    def record_rollback(self, success: bool = True) -> None:
        with self._mutex:
            self.rollback_count += 1
            if success:
                self.rollback_success_count += 1
            else:
                self.rollback_failure_count += 1

    def record_ollama_call(self, success: bool = True) -> None:
        with self._mutex:
            self.ollama_request_count += 1
            if not success:
                self.ollama_failure_count += 1

    def record_latency(self, operation: str, duration_ms: float, status: str = "SUCCESS", details: Optional[Dict[str, Any]] = None) -> None:
        with self._mutex:
            sample = LatencySample(
                operation=operation,
                duration_ms=duration_ms,
                status=status,
                details=details or {},
            )
            self._history.append(sample)

            op_lower = operation.lower()
            if "predict" in op_lower:
                self.prediction_latencies.append(duration_ms)
            elif "reason" in op_lower:
                self.reasoning_latencies.append(duration_ms)
            elif "trust" in op_lower:
                self.trust_latencies.append(duration_ms)
            elif "path" in op_lower:
                self.path_decision_latencies.append(duration_ms)
            elif "failover" in op_lower:
                self.failover_latencies.append(duration_ms)
            elif "verif" in op_lower:
                self.verification_latencies.append(duration_ms)

    def _avg(self, dq: deque[float]) -> float:
        return sum(dq) / len(dq) if dq else 0.0

    def get_summary(self) -> Dict[str, Any]:
        with self._mutex:
            uptime_sec = (datetime.now(timezone.utc) - self.started_at).total_seconds()
            return {
                "uptime_seconds": round(uptime_sec, 2),
                "investigation_request_count": self.investigation_request_count,
                "incident_count": self.incident_count,
                "rollback_count": self.rollback_count,
                "rollback_success_count": self.rollback_success_count,
                "rollback_failure_count": self.rollback_failure_count,
                "ollama_request_count": self.ollama_request_count,
                "ollama_failure_count": self.ollama_failure_count,
                "avg_latencies_ms": {
                    "prediction": round(self._avg(self.prediction_latencies), 2),
                    "reasoning": round(self._avg(self.reasoning_latencies), 2),
                    "trust_evaluation": round(self._avg(self.trust_latencies), 2),
                    "path_decision": round(self._avg(self.path_decision_latencies), 2),
                    "failover_simulation": round(self._avg(self.failover_latencies), 2),
                    "verification": round(self._avg(self.verification_latencies), 2),
                },
                "total_recorded_operations": len(self._history),
            }
