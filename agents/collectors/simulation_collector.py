"""
Simulation Telemetry Collector Implementation.

Wraps the NOC Copilot synthetic fault simulation engine and database repository
to provide backwards-compatible simulated telemetry packets.
"""

from datetime import datetime, timezone
import random
from typing import List, Optional

from agents.core.logger import get_agent_logger
from agents.schemas.schemas import TelemetryPacket
from agents.telemetry.telemetry_service import TelemetryService
from agents.collectors.collector_base import CollectorBase
from agents.collectors.collector_models import (
    CollectorCapabilities,
    CollectorMetadata,
    CollectorSchedule,
    CollectorState,
)

logger = get_agent_logger("SimulationCollector")


class SimulationCollector(CollectorBase):
    """
    Simulation Collector for NOC Copilot.

    Ingests telemetry from TelemetryService / synthetic generator.
    """

    def __init__(
        self,
        service: Optional[TelemetryService] = None,
        metadata: Optional[CollectorMetadata] = None,
        schedule: Optional[CollectorSchedule] = None,
    ) -> None:
        """
        Initialize SimulationCollector.

        Args:
            service: TelemetryService instance.
            metadata: Metadata override.
            schedule: Polling schedule override.
        """
        meta = metadata or CollectorMetadata(
            name="SimulationCollector",
            description="Synthetic fault telemetry collector for simulation mode",
            source_type="simulation",
            supported_metrics=["utilization", "latency", "jitter", "drops", "routing_flaps"],
            author="NOC Copilot Core Team",
        )
        sched = schedule or CollectorSchedule(interval_seconds=5.0, priority=10)
        caps = CollectorCapabilities(
            supports_streaming=False,
            supports_polling=True,
            supports_batch=True,
            supports_filtering=True,
            protocol="internal",
        )

        super().__init__(metadata=meta, schedule=sched, capabilities=caps)
        self._service = service or TelemetryService()
        self._devices = [
            ("rtr-01", "Branch3-Uplink"),
            ("rtr-02", "Core-Switch-01"),
            ("ap-10", "Campus-WiFi-AP"),
            ("fw-01", "SecLab-Gateway"),
        ]

    def initialize(self) -> bool:
        """Initialize simulation collector."""
        with self._lock:
            self._health.state = CollectorState.READY
            self._health.is_healthy = True
            logger.info("SimulationCollector initialized successfully.")
            return True

    def shutdown(self) -> bool:
        """Shutdown simulation collector."""
        with self._lock:
            self._health.state = CollectorState.TERMINATED
            logger.info("SimulationCollector shut down cleanly.")
            return True

    def collect(self) -> List[TelemetryPacket]:
        """
        Collect simulated telemetry packets.

        Fetches latest packets from TelemetryService database if available,
        otherwise generates structured synthetic telemetry packets.

        Returns:
            List of TelemetryPacket instances.
        """
        packets: List[TelemetryPacket] = []

        try:
            db_packets = self._service.fetch_all_latest_packets()
            if db_packets:
                return db_packets
        except Exception as db_err:
            logger.debug(f"TelemetryService fetch returned empty/error ({db_err}). Generating fallback packets.")

        # Synthetic fallback packets if database is empty
        now = datetime.now(timezone.utc)
        for dev_id, iface in self._devices:
            packet = TelemetryPacket(
                device_id=dev_id,
                interface=iface,
                metrics={
                    "utilization": round(random.uniform(20.0, 75.0), 2),
                    "latency": round(random.uniform(5.0, 30.0), 2),
                    "jitter": round(random.uniform(0.5, 3.5), 2),
                    "drops": round(random.uniform(0.0, 2.0), 2),
                    "routing_flaps": 0.0,
                },
                timestamp=now,
                metadata={"source": "SimulationCollector", "mode": "synthetic"},
            )
            packets.append(packet)

        return packets
