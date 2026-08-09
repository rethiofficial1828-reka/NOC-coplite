"""
Production Telemetry Agent Implementation.

Subclasses BaseAgent to ingest, validate, and standardize multi-device network telemetry,
publish 'telemetry.updated' events to the EventBus, and update workflow ExecutionContext.
"""

from typing import Any, Dict, List, Optional, Union
import uuid

from agents.base.base_agent import BaseAgent
from agents.core.container import ServiceContainer
from agents.core.logger import get_agent_logger, log_execution_event
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.registry.registry import AgentRegistry
from agents.schemas.schemas import (
    AgentMetadata,
    CapabilityFlags,
    ExecutionContext,
    TelemetryPacket,
)
from agents.telemetry.telemetry_service import TelemetryService
from config.config_manager import ConfigManager

logger = get_agent_logger("TelemetryAgent")


class TelemetryAgent(BaseAgent):
    """
    Production Telemetry Agent for NOC Copilot.

    Ingests telemetry from TelemetryService, validates packets, publishes 'telemetry.updated'
    events onto the EventBus, and populates workflow ExecutionContext.
    """

    def __init__(
        self,
        service: Optional[TelemetryService] = None,
        metadata: Optional[AgentMetadata] = None,
        container: Optional[ServiceContainer] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        """
        Initialize TelemetryAgent.

        Args:
            service: TelemetryService instance (defaults to DI container or new TelemetryService).
            metadata: AgentMetadata instance.
            container: ServiceContainer instance.
            event_bus: EventBus instance.
        """
        agent_metadata = metadata or AgentMetadata(
            name="TelemetryAgent",
            version="1.0.0",
            description="Ingests, validates, and standardizes multi-device network telemetry.",
            author="NOC Copilot Core Team",
            dependencies=[],
            tags=["telemetry", "ingest", "monitoring"],
            capabilities=CapabilityFlags(supports_cpu=True, supports_batch=True),
        )

        super().__init__(metadata=agent_metadata, container=container, event_bus=event_bus)
        self._service = service or TelemetryService(
            config_manager=self.container.resolve(ConfigManager) if self.container.has_service(ConfigManager) else None
        )

    @property
    def service(self) -> TelemetryService:
        """Telemetry service instance."""
        return self._service

    def validate_input(self, input_data: Any) -> Dict[str, Any]:
        """
        Validate execution input payload options.

        Expected format dict:
            {
                "device_id": "core-01",  # Optional: specific device ID or interface name or "all"
                "interface": "Branch3-Uplink",  # Optional alias
                "mode": "latest",  # "latest", "historical", or "timerange"
                "limit": 30,  # Optional limit for historical/timerange
                "start_time": 1700000000.0,  # Optional for timerange
                "end_time": 1700001000.0  # Optional for timerange
            }
        """
        if input_data is None:
            return {"mode": "latest", "device_id": "all"}

        if not isinstance(input_data, dict):
            # Treat simple string as device_id or interface name
            return {"mode": "latest", "device_id": str(input_data)}

        mode = input_data.get("mode", "latest")
        if mode not in ("latest", "historical", "timerange"):
            mode = "latest"

        device_target = input_data.get("device_id") or input_data.get("interface") or "all"
        limit = int(input_data.get("limit", 30))

        validated_opts: Dict[str, Any] = {
            "mode": mode,
            "device_id": device_target,
            "limit": max(1, limit),
        }

        if "start_time" in input_data:
            validated_opts["start_time"] = float(input_data["start_time"])
        if "end_time" in input_data:
            validated_opts["end_time"] = float(input_data["end_time"])

        return validated_opts

    def _execute_internal(
        self, input_data: Dict[str, Any], context: Optional[ExecutionContext] = None
    ) -> List[TelemetryPacket]:
        """
        Execute telemetry collection, payload validation, event publishing, and context update.

        Args:
            input_data: Validated execution options.
            context: Shared ExecutionContext.

        Returns:
            List of fetched and validated TelemetryPacket objects.
        """
        mode = input_data["mode"]
        target = input_data["device_id"]
        limit = input_data["limit"]

        packets: List[TelemetryPacket] = []

        if mode == "timerange" and "start_time" in input_data and "end_time" in input_data:
            start_ts = input_data["start_time"]
            end_ts = input_data["end_time"]
            packets = self._service.fetch_timerange_packets(
                target, start_ts, end_ts, limit=limit
            )
        elif mode == "historical" and target != "all":
            packets = self._service.fetch_historical_packets(target, limit=limit)
        else:
            # Mode "latest"
            if target == "all" or not target:
                packets = self._service.fetch_all_latest_packets()
            else:
                single_packet = self._service.fetch_latest_packet(target)
                if single_packet:
                    packets = [single_packet]

        exec_id = context.context_id if context else str(uuid.uuid4())

        # Publish telemetry.updated events
        published_count = 0
        if self.event_bus:
            for packet in packets:
                event = Event(
                    event_type="telemetry.updated",
                    source=self.name,
                    payload=packet.model_dump(mode="json"),
                    metadata={
                        "execution_id": exec_id,
                        "device_id": packet.device_id,
                        "interface": packet.interface,
                        "timestamp": str(packet.timestamp),
                    },
                )
                self.event_bus.publish(event)
                published_count += 1

        log_execution_event(
            logger,
            self.name,
            "TELEMETRY_PROCESSED",
            f"TelemetryAgent processed {len(packets)} packet(s) (published {published_count} events).",
        )

        # Update execution context if provided
        if context:
            context.results[self.name] = [p.model_dump(mode="json") for p in packets]
            context.shared_state["latest_telemetry"] = {
                p.interface: p.model_dump(mode="json") for p in packets
            }

        return packets


def register_telemetry_agent(registry: Optional[AgentRegistry] = None) -> TelemetryAgent:
    """
    Convenience function to instantiate and register TelemetryAgent with the AgentRegistry.

    Args:
        registry: Target AgentRegistry (defaults to global registry).

    Returns:
        Registered TelemetryAgent instance.
    """
    target_registry = registry or AgentRegistry.get_global()
    agent = TelemetryAgent()
    target_registry.register(agent, allow_override=True)
    return agent
