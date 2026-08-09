"""
Incident Validator Module.

Provides data integrity and range validation for IncidentRecord, IncidentTimeline,
and incident state transition payloads. Raises ValidationError upon validation failure.
"""

from typing import Any, Dict

from agents.core.exceptions import ValidationError
from agents.incident.incident_models import (
    IncidentRecord,
    IncidentSeverity,
    IncidentStatus,
    IncidentTimeline,
)


class IncidentValidator:
    """
    Validator for Incident domain models and prediction payloads.
    """

    @classmethod
    def validate_incident_record(cls, incident: IncidentRecord) -> IncidentRecord:
        """
        Validate IncidentRecord attributes and domain constraints.

        Args:
            incident: IncidentRecord model instance.

        Returns:
            Validated IncidentRecord.

        Raises:
            ValidationError: If any attribute is invalid.
        """
        if not isinstance(incident, IncidentRecord):
            raise ValidationError(f"Expected IncidentRecord model instance, got {type(incident).__name__}.")

        if not incident.incident_id or not incident.incident_id.strip():
            raise ValidationError("Incident incident_id cannot be empty.")

        if not incident.device_id or not incident.device_id.strip():
            raise ValidationError("Incident device_id cannot be empty.")

        if not incident.title or not incident.title.strip():
            raise ValidationError("Incident title cannot be empty.")

        if not isinstance(incident.severity, IncidentSeverity):
            raise ValidationError(f"Invalid incident severity level: {incident.severity}")

        if not isinstance(incident.status, IncidentStatus):
            raise ValidationError(f"Invalid incident status state: {incident.status}")

        if incident.risk_score < 0.0 or incident.risk_score > 1.0:
            raise ValidationError(f"Incident risk_score out of bounds [0.0, 1.0]: {incident.risk_score}")

        return incident

    @classmethod
    def validate_prediction_payload(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate incoming prediction payload before incident evaluation.

        Args:
            payload: Payload dictionary containing prediction attributes.

        Returns:
            Validated payload dictionary.

        Raises:
            ValidationError: If required prediction keys are missing or invalid.
        """
        if not isinstance(payload, dict):
            raise ValidationError(f"Prediction payload must be a dictionary, got {type(payload).__name__}.")

        iface = payload.get("interface") or payload.get("device_id")
        if not iface or not str(iface).strip():
            raise ValidationError("Prediction payload missing 'interface' or 'device_id'.")

        risk = payload.get("risk_score")
        if risk is None or not isinstance(risk, (int, float)):
            raise ValidationError(f"Prediction payload missing valid numeric 'risk_score': {risk}")

        if float(risk) < 0.0 or float(risk) > 1.0:
            raise ValidationError(f"Prediction payload risk_score out of bounds: {risk}")

        return payload
