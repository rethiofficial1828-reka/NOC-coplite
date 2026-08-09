"""
Recommendation Validator Module.

Provides data integrity, range, and schema validation for RecommendationRecord models,
execution plans, CLI commands, and rollback plans. Raises ValidationError upon failure.
"""

from typing import Any, Dict

from agents.core.exceptions import ValidationError
from agents.recommendation.recommendation_models import (
    RecommendationCommand,
    RecommendationPriority,
    RecommendationRecord,
)


class RecommendationValidator:
    """
    Validator for recommendation records and execution plan structures.
    """

    @classmethod
    def validate_recommendation_record(cls, rec: RecommendationRecord) -> RecommendationRecord:
        """
        Validate RecommendationRecord attributes.

        Args:
            rec: RecommendationRecord model instance.

        Returns:
            Validated RecommendationRecord.

        Raises:
            ValidationError: If record or attributes are invalid.
        """
        if not isinstance(rec, RecommendationRecord):
            raise ValidationError(f"Expected RecommendationRecord model, got {type(rec).__name__}.")

        if not rec.recommendation_id or not rec.recommendation_id.strip():
            raise ValidationError("Recommendation recommendation_id cannot be empty.")

        if not rec.incident_id or not rec.incident_id.strip():
            raise ValidationError("Recommendation incident_id cannot be empty.")

        if not rec.device_id or not rec.device_id.strip():
            raise ValidationError("Recommendation device_id cannot be empty.")

        if not rec.summary or not rec.summary.strip():
            raise ValidationError("Recommendation summary cannot be empty.")

        if not isinstance(rec.priority, RecommendationPriority):
            raise ValidationError(f"Invalid recommendation priority: {rec.priority}")

        if not rec.execution_plan or not rec.execution_plan.actions:
            raise ValidationError("Recommendation execution_plan must contain at least one action step.")

        return rec

    @classmethod
    def validate_command(cls, cmd: RecommendationCommand) -> RecommendationCommand:
        """
        Validate RecommendationCommand object.

        Args:
            cmd: RecommendationCommand model instance.

        Returns:
            Validated RecommendationCommand.

        Raises:
            ValidationError: If command attributes are invalid.
        """
        if not isinstance(cmd, RecommendationCommand):
            raise ValidationError(f"Expected RecommendationCommand model, got {type(cmd).__name__}.")

        if not cmd.command_text or not cmd.command_text.strip():
            raise ValidationError("RecommendationCommand command_text cannot be empty.")

        if not cmd.target_device or not cmd.target_device.strip():
            raise ValidationError("RecommendationCommand target_device cannot be empty.")

        return cmd

    @classmethod
    def validate_incident_payload(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate incoming incident payload before recommendation generation.

        Args:
            payload: Incident record or dictionary payload.

        Returns:
            Validated payload dictionary.

        Raises:
            ValidationError: If payload is missing incident_id or device_id.
        """
        if not isinstance(payload, dict):
            raise ValidationError(f"Incident payload must be a dictionary, got {type(payload).__name__}.")

        inc_id = payload.get("incident_id")
        if not inc_id or not str(inc_id).strip():
            raise ValidationError("Incident payload missing required 'incident_id'.")

        dev_id = payload.get("device_id") or payload.get("interface")
        if not dev_id or not str(dev_id).strip():
            raise ValidationError("Incident payload missing required 'device_id' or 'interface'.")

        return payload
