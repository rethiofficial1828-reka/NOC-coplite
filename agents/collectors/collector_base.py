"""
Abstract Collector Base Class Definition.

Defines the pluggable interface contract for all live enterprise and simulation
telemetry collectors in NOC Copilot.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import threading
import time
from typing import List, Optional

from agents.core.logger import get_agent_logger
from agents.schemas.schemas import TelemetryPacket
from agents.collectors.collector_models import (
    CollectorCapabilities,
    CollectorHealth,
    CollectorMetadata,
    CollectorSchedule,
    CollectorState,
)

logger = get_agent_logger("CollectorBase")


class CollectorBase(ABC):
    """
    Abstract Base Class for Enterprise Telemetry Collectors.

    All telemetry collectors (SNMP, Syslog, REST, Windows, Linux, Prometheus, Simulation)
    must subclass this class and implement initialize(), shutdown(), and collect().
    """

    def __init__(
        self,
        metadata: Optional[CollectorMetadata] = None,
        schedule: Optional[CollectorSchedule] = None,
        capabilities: Optional[CollectorCapabilities] = None,
    ) -> None:
        """
        Initialize CollectorBase instance.

        Args:
            metadata: Metadata describing collector identity.
            schedule: Polling schedule and configuration.
            capabilities: Supported capability flags.
        """
        self._lock = threading.RLock()
        default_name = self.__class__.__name__

        self._metadata = metadata or CollectorMetadata(
            name=default_name,
            description=f"Telemetry collector instance of {default_name}",
        )
        self._schedule = schedule or CollectorSchedule()
        self._capabilities = capabilities or CollectorCapabilities()

        self._health = CollectorHealth(
            collector_id=self._metadata.collector_id,
            collector_name=self._metadata.name,
            state=CollectorState.UNINITIALIZED,
            is_healthy=True,
        )

    @property
    def name(self) -> str:
        """Name of collector."""
        return self._metadata.name

    @property
    def collector_id(self) -> str:
        """Instance identifier."""
        return self._metadata.collector_id

    @property
    def source_type(self) -> str:
        """Telemetry source classification."""
        return self._metadata.source_type

    @property
    def is_enabled(self) -> bool:
        """Check if collector schedule is enabled."""
        with self._lock:
            return self._schedule.enabled

    @abstractmethod
    def initialize(self) -> bool:
        """
        Initialize collector resources (connections, sockets, sessions).

        Returns:
            True if initialization succeeded, False otherwise.
        """
        pass

    @abstractmethod
    def shutdown(self) -> bool:
        """
        Gracefully release and close collector resources.

        Returns:
            True if shutdown completed cleanly, False otherwise.
        """
        pass

    @abstractmethod
    def collect(self) -> List[TelemetryPacket]:
        """
        Execute a single telemetry collection run.

        Returns:
            List of validated TelemetryPacket objects.
        """
        pass

    def health(self) -> CollectorHealth:
        """
        Retrieve a thread-safe snapshot of operational health.

        Returns:
            CollectorHealth model copy.
        """
        with self._lock:
            return self._health.model_copy(deep=True)

    def metadata(self) -> CollectorMetadata:
        """
        Retrieve collector metadata.

        Returns:
            CollectorMetadata model copy.
        """
        with self._lock:
            return self._metadata.model_copy(deep=True)

    def capabilities(self) -> CollectorCapabilities:
        """
        Retrieve supported capability flags.

        Returns:
            CollectorCapabilities model copy.
        """
        with self._lock:
            return self._capabilities.model_copy(deep=True)

    def schedule(self) -> CollectorSchedule:
        """
        Retrieve current collection schedule configuration.

        Returns:
            CollectorSchedule model copy.
        """
        with self._lock:
            return self._schedule.model_copy(deep=True)

    def set_enabled(self, enabled: bool) -> None:
        """
        Enable or disable collector execution.

        Args:
            enabled: Boolean flag.
        """
        with self._lock:
            self._schedule.enabled = enabled
            if not enabled and self._health.state == CollectorState.RUNNING:
                self._health.state = CollectorState.PAUSED
            elif enabled and self._health.state == CollectorState.PAUSED:
                self._health.state = CollectorState.READY

    def update_schedule(self, new_schedule: CollectorSchedule) -> None:
        """
        Update polling schedule configuration.

        Args:
            new_schedule: New CollectorSchedule object.
        """
        with self._lock:
            self._schedule = new_schedule.model_copy(deep=True)

    def record_success(self, packets_count: int, latency_ms: float) -> CollectorHealth:
        """
        Record a successful collection execution in metrics.

        Args:
            packets_count: Number of TelemetryPackets collected.
            latency_ms: Execution duration in milliseconds.

        Returns:
            Updated CollectorHealth object.
        """
        now = datetime.now(timezone.utc)
        with self._lock:
            h = self._health
            h.total_collections += 1
            h.successful_collections += 1
            h.consecutive_failures = 0
            h.last_collection_timestamp = now
            h.last_success_timestamp = now
            h.last_latency_ms = latency_ms
            h.total_latency_ms += latency_ms
            h.packets_collected += packets_count
            h.last_error = None

            if h.total_collections > 0:
                h.avg_latency_ms = h.total_latency_ms / h.total_collections
                h.availability_percent = (h.successful_collections / h.total_collections) * 100.0

            h.is_healthy = True
            h.state = CollectorState.READY
            return h.model_copy(deep=True)

    def record_failure(self, error_message: str, latency_ms: float = 0.0) -> CollectorHealth:
        """
        Record a failed collection execution in metrics.

        Args:
            error_message: Detailed error string.
            latency_ms: Duration before failure in milliseconds.

        Returns:
            Updated CollectorHealth object.
        """
        now = datetime.now(timezone.utc)
        with self._lock:
            h = self._health
            h.total_collections += 1
            h.failed_collections += 1
            h.consecutive_failures += 1
            h.last_collection_timestamp = now
            h.last_failure_timestamp = now
            h.last_latency_ms = latency_ms
            h.total_latency_ms += latency_ms
            h.last_error = error_message

            if h.total_collections > 0:
                h.avg_latency_ms = h.total_latency_ms / h.total_collections
                h.availability_percent = (h.successful_collections / h.total_collections) * 100.0

            # State degrades or fails based on consecutive failure threshold
            if h.consecutive_failures >= 3:
                h.is_healthy = False
                h.state = CollectorState.FAILED
            else:
                h.state = CollectorState.DEGRADED

            logger.warning(
                f"Collector '{self.name}' recorded failure ({h.consecutive_failures} consecutive): {error_message}"
            )
            return h.model_copy(deep=True)

    def execute_collection(self) -> List[TelemetryPacket]:
        """
        Thread-safe execution wrapper with metrics recording and latency measurement.

        Returns:
            List of collected TelemetryPacket instances.
        """
        with self._lock:
            if not self._schedule.enabled:
                logger.debug(f"Collector '{self.name}' is disabled. Skipping execution.")
                return []
            self._health.state = CollectorState.RUNNING

        start_time = time.perf_counter()
        try:
            packets = self.collect()
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            self.record_success(packets_count=len(packets), latency_ms=elapsed_ms)
            return packets
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            err_msg = str(e) or e.__class__.__name__
            self.record_failure(error_message=err_msg, latency_ms=elapsed_ms)
            raise
