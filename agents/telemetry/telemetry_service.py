"""
Telemetry Service Module.

Business service layer that transforms raw telemetry database records into strongly-typed
TelemetryPacket objects, maps devices from DEVICE_REGISTRY, and prepares metrics for downstream agents.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from agents.core.exceptions import ValidationError
from agents.core.logger import get_agent_logger
from agents.schemas.schemas import TelemetryPacket
from agents.telemetry.telemetry_repository import TelemetryRepository
from agents.telemetry.telemetry_validator import TelemetryValidator
from config.config_manager import ConfigManager
from config.settings import DEVICE_REGISTRY

logger = get_agent_logger("TelemetryService")


class TelemetryService:
    """
    Business logic layer for telemetry processing, device resolution, and TelemetryPacket construction.
    """

    def __init__(
        self,
        repository: Optional[TelemetryRepository] = None,
        validator: Optional[TelemetryValidator] = None,
        config_manager: Optional[ConfigManager] = None,
    ) -> None:
        """
        Initialize TelemetryService.

        Args:
            repository: TelemetryRepository instance for data access.
            validator: TelemetryValidator instance for record validation.
            config_manager: ConfigManager instance for configuration settings.
        """
        self._config_manager = config_manager or ConfigManager.get_instance()
        self._repository = repository or TelemetryRepository()
        self._validator = validator or TelemetryValidator()

    @property
    def repository(self) -> TelemetryRepository:
        """Repository instance."""
        return self._repository

    @property
    def validator(self) -> TelemetryValidator:
        """Validator instance."""
        return self._validator

    def get_supported_devices(self) -> List[Dict[str, Any]]:
        """Retrieve list of configured devices from DEVICE_REGISTRY."""
        registry = self._config_manager.get("DEVICE_REGISTRY", DEVICE_REGISTRY)
        return list(registry)

    def resolve_device(self, device_id_or_name: str) -> Tuple[str, str]:
        """
        Map a device identifier or interface name to a tuple of (device_id, interface_name).

        Args:
            device_id_or_name: Device ID or Interface name string.

        Returns:
            Tuple of (device_id, interface_name).
        """
        devices = self.get_supported_devices()
        target = device_id_or_name.strip().lower()

        for dev in devices:
            did = str(dev.get("id", "")).strip().lower()
            dname = str(dev.get("name", "")).strip().lower()

            if target == did or target == dname:
                return dev["id"], dev["name"]

        # Default fallback if not found in static registry
        return device_id_or_name, device_id_or_name

    def raw_record_to_packet(self, record: Dict[str, Any]) -> TelemetryPacket:
        """
        Validate raw record dictionary and convert to a TelemetryPacket model.

        Args:
            record: Raw database record dict.

        Returns:
            Validated TelemetryPacket object.
        """
        validated_record = self._validator.validate_raw_record(record)
        interface_name = validated_record["interface"]
        device_id, interface_clean = self.resolve_device(interface_name)

        raw_ts = float(validated_record["timestamp"])
        packet_time = datetime.fromtimestamp(raw_ts, tz=timezone.utc)

        metrics = {
            "utilization": float(validated_record["utilization"]),
            "latency": float(validated_record["latency"]),
            "jitter": float(validated_record["jitter"]),
            "drops": float(validated_record["drops"]),
            "routing_flaps": float(validated_record["routing_flaps"]),
        }

        packet = TelemetryPacket(
            device_id=device_id,
            interface=interface_clean,
            metrics=metrics,
            timestamp=packet_time,
            metadata={"raw_timestamp": raw_ts},
        )

        return self._validator.validate_packet(packet)

    def fetch_latest_packet(self, device_id_or_name: str) -> Optional[TelemetryPacket]:
        """
        Fetch and parse the latest TelemetryPacket for a given device or interface.

        Args:
            device_id_or_name: Device ID or Interface name.

        Returns:
            TelemetryPacket or None if no record found.
        """
        _, interface_name = self.resolve_device(device_id_or_name)
        record = self._repository.get_latest_telemetry(interface_name)
        if not record:
            logger.debug(f"No latest telemetry record found for interface '{interface_name}'")
            return None

        return self.raw_record_to_packet(record)

    def fetch_all_latest_packets(self) -> List[TelemetryPacket]:
        """
        Fetch latest TelemetryPacket for every device currently present in the database.

        Returns:
            List of TelemetryPacket objects.
        """
        records = self._repository.get_all_latest_telemetry()
        packets: List[TelemetryPacket] = []
        for r in records:
            try:
                packets.append(self.raw_record_to_packet(r))
            except ValidationError as ve:
                logger.warning(f"Skipping invalid record for interface '{r.get('interface')}': {ve}")

        return packets

    def fetch_historical_packets(
        self, device_id_or_name: str, limit: int = 30
    ) -> List[TelemetryPacket]:
        """
        Fetch historical TelemetryPackets for a device.

        Args:
            device_id_or_name: Device ID or Interface name.
            limit: Number of records to return.

        Returns:
            List of TelemetryPacket objects ordered by timestamp ASC.
        """
        _, interface_name = self.resolve_device(device_id_or_name)
        records = self._repository.get_historical_telemetry(interface_name, limit=limit)
        packets: List[TelemetryPacket] = []
        for r in records:
            try:
                packets.append(self.raw_record_to_packet(r))
            except ValidationError as ve:
                logger.warning(f"Skipping invalid historical record: {ve}")

        return packets

    def fetch_timerange_packets(
        self,
        device_id_or_name: str,
        start_time: float,
        end_time: float,
        limit: int = 100,
        offset: int = 0,
    ) -> List[TelemetryPacket]:
        """
        Fetch TelemetryPackets within a timestamp epoch range.

        Args:
            device_id_or_name: Device ID or Interface name.
            start_time: Start epoch seconds.
            end_time: End epoch seconds.
            limit: Pagination limit.
            offset: Pagination offset.

        Returns:
            List of TelemetryPacket objects ordered by timestamp ASC.
        """
        _, interface_name = self.resolve_device(device_id_or_name)
        records = self._repository.get_telemetry_by_timerange(
            interface_name, start_time, end_time, limit=limit, offset=offset
        )
        packets: List[TelemetryPacket] = []
        for r in records:
            try:
                packets.append(self.raw_record_to_packet(r))
            except ValidationError as ve:
                logger.warning(f"Skipping invalid timerange record: {ve}")

        return packets
