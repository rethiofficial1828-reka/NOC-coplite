"""
Prediction Service Module.

Business service layer that orchestrates predictive ML execution via PredictionRepository,
validates output via PredictionValidator, and constructs strongly-typed PredictionResult objects.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents.core.logger import get_agent_logger
from agents.prediction.prediction_repository import PredictionRepository
from agents.prediction.prediction_validator import PredictionValidator
from agents.schemas.schemas import PredictionResult, TelemetryPacket

logger = get_agent_logger("PredictionService")


class PredictionService:
    """
    Business service layer for ML risk prediction and PredictionResult schema construction.
    """

    def __init__(
        self,
        repository: Optional[PredictionRepository] = None,
        validator: Optional[PredictionValidator] = None,
    ) -> None:
        """
        Initialize PredictionService.

        Args:
            repository: PredictionRepository instance for ML engine access.
            validator: PredictionValidator instance for schema validation.
        """
        self._repository = repository or PredictionRepository()
        self._validator = validator or PredictionValidator()

    @property
    def repository(self) -> PredictionRepository:
        """Repository instance."""
        return self._repository

    @property
    def validator(self) -> PredictionValidator:
        """Validator instance."""
        return self._validator

    def raw_dict_to_prediction_result(self, raw: Dict[str, Any]) -> PredictionResult:
        """
        Validate raw engine prediction dict and convert into a PredictionResult domain model.

        Args:
            raw: Raw prediction dictionary.

        Returns:
            Validated PredictionResult object.
        """
        validated_raw = self._validator.validate_raw_prediction(raw)

        # Normalize risk score between 0.0 and 1.0
        risk_score = float(max(0.0, min(1.0, validated_raw["risk_score"])))
        time_to_impact = float(validated_raw["time_to_impact"])
        signals = list(validated_raw["contributing_signals"])
        interface_name = str(validated_raw["interface"])

        # Calculate confidence metric
        confidence = float(raw.get("confidence", 1.0))
        confidence = max(0.0, min(1.0, confidence))

        result = PredictionResult(
            interface=interface_name,
            risk_score=risk_score,
            time_to_impact=time_to_impact,
            contributing_signals=signals,
            timestamp=datetime.now(timezone.utc),
            confidence=confidence,
        )

        return self._validator.validate_prediction_result(result)

    def predict_for_interface(self, interface: str) -> PredictionResult:
        """
        Fetch recent telemetry for interface and execute prediction service.

        Args:
            interface: Name of interface.

        Returns:
            PredictionResult object.
        """
        raw = self._repository.predict_for_interface(interface)
        return self.raw_dict_to_prediction_result(raw)

    def predict_for_telemetry_packet(self, packet: TelemetryPacket) -> PredictionResult:
        """
        Execute prediction service for a single TelemetryPacket event.

        Args:
            packet: TelemetryPacket object.

        Returns:
            PredictionResult object.
        """
        # If TelemetryPacket contains interface, query recent window for that interface
        return self.predict_for_interface(packet.interface)

    def predict_fleet(self, interfaces: Optional[List[str]] = None) -> List[PredictionResult]:
        """
        Execute prediction service across all fleet devices.

        Args:
            interfaces: Optional list of interface names.

        Returns:
            List of PredictionResult objects.
        """
        raw_fleet = self._repository.predict_fleet(interfaces)
        results: List[PredictionResult] = []

        for iface, raw in raw_fleet.items():
            try:
                results.append(self.raw_dict_to_prediction_result(raw))
            except Exception as e:
                logger.error(f"Error building prediction result for interface '{iface}': {e}", exc_info=True)

        return results
