"""
Prediction Validator Module.

Provides schema validation, range checks, and type verification for prediction engine outputs
and PredictionResult domain models. Raises ValidationError upon validation failure.
"""

from typing import Any, Dict

from agents.core.exceptions import ValidationError
from agents.schemas.schemas import PredictionResult


class PredictionValidator:
    """
    Validator for prediction results and raw prediction dictionary outputs.
    """

    REQUIRED_RAW_FIELDS = {"interface", "risk_score", "time_to_impact", "contributing_signals"}

    @classmethod
    def validate_raw_prediction(cls, raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate raw dictionary prediction output from repository/engine.

        Args:
            raw: Dictionary containing raw prediction attributes.

        Returns:
            Validated raw prediction dictionary.

        Raises:
            ValidationError: If required fields are missing, invalid, or out of range.
        """
        if not isinstance(raw, dict):
            raise ValidationError(f"Prediction result must be a dict, got {type(raw).__name__}.")

        missing = cls.REQUIRED_RAW_FIELDS - set(raw.keys())
        if missing:
            raise ValidationError(f"Prediction output missing required keys: {sorted(list(missing))}")

        # Interface validation
        iface = raw.get("interface")
        if not isinstance(iface, str) or not iface.strip():
            raise ValidationError("Prediction interface must be a non-empty string.")

        # Risk score validation
        risk = raw.get("risk_score")
        if not isinstance(risk, (int, float)):
            raise ValidationError(f"Risk score must be numeric, got {type(risk).__name__}.")
        if risk < 0.0 or risk > 1.0:
            raise ValidationError(f"Risk score must be within range [0.0, 1.0], got {risk}.")

        # Time to impact validation
        tti = raw.get("time_to_impact")
        if not isinstance(tti, (int, float)):
            raise ValidationError(f"Time to impact must be numeric, got {type(tti).__name__}.")
        if tti < -1.0:
            raise ValidationError(f"Time to impact cannot be less than -1.0, got {tti}.")

        # Contributing signals validation
        signals = raw.get("contributing_signals")
        if not isinstance(signals, list):
            raise ValidationError(f"Contributing signals must be a list, got {type(signals).__name__}.")
        for sig in signals:
            if not isinstance(sig, str):
                raise ValidationError(f"Contributing signal element must be a string, got {type(sig).__name__}.")

        # Optional confidence validation
        if "confidence" in raw and raw["confidence"] is not None:
            conf = raw["confidence"]
            if not isinstance(conf, (int, float)) or conf < 0.0 or conf > 1.0:
                raise ValidationError(f"Confidence score must be within range [0.0, 1.0], got {conf}.")

        return raw

    @classmethod
    def validate_prediction_result(cls, result: PredictionResult) -> PredictionResult:
        """
        Validate a PredictionResult model instance.

        Args:
            result: PredictionResult object.

        Returns:
            Validated PredictionResult object.

        Raises:
            ValidationError: If model attributes violate domain constraints.
        """
        if not isinstance(result, PredictionResult):
            raise ValidationError(f"Expected PredictionResult model, got {type(result).__name__}.")

        if not result.interface or not result.interface.strip():
            raise ValidationError("PredictionResult interface must be a non-empty string.")

        if result.risk_score < 0.0 or result.risk_score > 1.0:
            raise ValidationError(f"PredictionResult risk_score out of bounds [0.0, 1.0]: {result.risk_score}")

        if result.confidence < 0.0 or result.confidence > 1.0:
            raise ValidationError(f"PredictionResult confidence out of bounds [0.0, 1.0]: {result.confidence}")

        if result.time_to_impact < -1.0:
            raise ValidationError(f"PredictionResult time_to_impact invalid: {result.time_to_impact}")

        return result
