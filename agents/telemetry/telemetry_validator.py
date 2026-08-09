"""
Telemetry Validator Module.

Provides data type, range, null-check, and schema validation for network telemetry records
and TelemetryPacket objects. Raises ValidationError upon validation failure.
"""

from typing import Any, Dict

from agents.core.exceptions import ValidationError
from agents.schemas.schemas import TelemetryPacket


class TelemetryValidator:
    """
    Validator for raw telemetry records and TelemetryPacket objects.
    """

    REQUIRED_RAW_FIELDS = {
        "timestamp",
        "interface",
        "utilization",
        "latency",
        "jitter",
        "drops",
        "routing_flaps",
    }

    @classmethod
    def validate_raw_record(cls, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate a raw dictionary record from the telemetry database.

        Args:
            record: Raw record dictionary.

        Returns:
            Validated raw record dictionary.

        Raises:
            ValidationError: If record is missing keys, contains invalid types, or out-of-range values.
        """
        if not isinstance(record, dict):
            raise ValidationError(f"Telemetry record must be a dictionary, got {type(record).__name__}.")

        missing = cls.REQUIRED_RAW_FIELDS - set(record.keys())
        if missing:
            raise ValidationError(f"Telemetry record missing required fields: {sorted(list(missing))}")

        # Interface validation
        interface = record.get("interface")
        if not isinstance(interface, str) or not interface.strip():
            raise ValidationError("Telemetry interface must be a non-empty string.")

        # Timestamp validation
        timestamp = record.get("timestamp")
        if not isinstance(timestamp, (int, float)) or timestamp <= 0:
            raise ValidationError(f"Invalid timestamp value: {timestamp}. Must be a positive numeric epoch.")

        # Utilization validation
        util = record.get("utilization")
        if not isinstance(util, (int, float)):
            raise ValidationError(f"Utilization must be numeric, got {type(util).__name__}.")
        if util < 0.0 or util > 100.0:
            raise ValidationError(f"Utilization out of valid percentage range [0, 100]: {util}")

        # Latency validation
        lat = record.get("latency")
        if not isinstance(lat, (int, float)):
            raise ValidationError(f"Latency must be numeric, got {type(lat).__name__}.")
        if lat < 0.0:
            raise ValidationError(f"Latency cannot be negative: {lat}")

        # Jitter validation
        jit = record.get("jitter")
        if not isinstance(jit, (int, float)):
            raise ValidationError(f"Jitter must be numeric, got {type(jit).__name__}.")
        if jit < 0.0:
            raise ValidationError(f"Jitter cannot be negative: {jit}")

        # Drops validation
        drp = record.get("drops")
        if not isinstance(drp, (int, float)):
            raise ValidationError(f"Drops must be numeric, got {type(drp).__name__}.")
        if drp < 0.0:
            raise ValidationError(f"Drops cannot be negative: {drp}")

        # Routing flaps validation
        flaps = record.get("routing_flaps")
        if not isinstance(flaps, (int, float)):
            raise ValidationError(f"Routing flaps must be numeric, got {type(flaps).__name__}.")
        if flaps < 0:
            raise ValidationError(f"Routing flaps cannot be negative: {flaps}")

        return record

    @classmethod
    def validate_packet(cls, packet: TelemetryPacket) -> TelemetryPacket:
        """
        Validate a TelemetryPacket model object.

        Args:
            packet: TelemetryPacket instance.

        Returns:
            Validated TelemetryPacket instance.

        Raises:
            ValidationError: If packet attributes or metrics are invalid.
        """
        if not isinstance(packet, TelemetryPacket):
            raise ValidationError(f"Expected TelemetryPacket instance, got {type(packet).__name__}.")

        if not packet.device_id or not packet.device_id.strip():
            raise ValidationError("TelemetryPacket device_id must be a non-empty string.")

        if not packet.interface or not packet.interface.strip():
            raise ValidationError("TelemetryPacket interface must be a non-empty string.")

        if not isinstance(packet.metrics, dict):
            raise ValidationError("TelemetryPacket metrics must be a dictionary.")

        # Check required metrics keys
        required_metrics = {"utilization", "latency", "jitter", "drops"}
        for k in required_metrics:
            if k in packet.metrics:
                val = packet.metrics[k]
                if not isinstance(val, (int, float)):
                    raise ValidationError(f"Metric '{k}' must be numeric in TelemetryPacket.")

        return packet
