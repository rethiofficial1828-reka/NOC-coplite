"""
Knowledge Validator Module.

Provides data integrity, bounds, and schema validation for KnowledgeResult models,
queries, and provider completions. Raises ValidationError upon validation failure.
"""

from typing import Any, Dict

from agents.core.exceptions import ValidationError
from agents.knowledge.knowledge_models import KnowledgeQuery, KnowledgeResult


class KnowledgeValidator:
    """
    Validator for Knowledge domain models and recommendation payloads.
    """

    @classmethod
    def validate_knowledge_result(cls, result: KnowledgeResult) -> KnowledgeResult:
        """
        Validate KnowledgeResult model instance.

        Args:
            result: KnowledgeResult instance.

        Returns:
            Validated KnowledgeResult.

        Raises:
            ValidationError: If model attributes are invalid.
        """
        if not isinstance(result, KnowledgeResult):
            raise ValidationError(f"Expected KnowledgeResult model, got {type(result).__name__}.")

        if not result.result_id or not result.result_id.strip():
            raise ValidationError("KnowledgeResult result_id cannot be empty.")

        if not result.recommendation_id or not result.recommendation_id.strip():
            raise ValidationError("KnowledgeResult recommendation_id cannot be empty.")

        if not result.incident_id or not result.incident_id.strip():
            raise ValidationError("KnowledgeResult incident_id cannot be empty.")

        if not result.generated_explanation or not result.generated_explanation.strip():
            raise ValidationError("KnowledgeResult generated_explanation cannot be empty.")

        if result.confidence_score < 0.0 or result.confidence_score > 1.0:
            raise ValidationError(f"KnowledgeResult confidence_score out of bounds [0.0, 1.0]: {result.confidence_score}")

        return result

    @classmethod
    def validate_recommendation_payload(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate incoming recommendation payload before generating knowledge.

        Args:
            payload: Recommendation payload dictionary.

        Returns:
            Validated payload dictionary.

        Raises:
            ValidationError: If required recommendation fields are missing.
        """
        if not isinstance(payload, dict):
            raise ValidationError(f"Recommendation payload must be a dict, got {type(payload).__name__}.")

        rec_id = payload.get("recommendation_id")
        if not rec_id or not str(rec_id).strip():
            raise ValidationError("Recommendation payload missing required 'recommendation_id'.")

        inc_id = payload.get("incident_id")
        if not inc_id or not str(inc_id).strip():
            raise ValidationError("Recommendation payload missing required 'incident_id'.")

        dev_id = payload.get("device_id") or payload.get("interface")
        if not dev_id or not str(dev_id).strip():
            raise ValidationError("Recommendation payload missing required 'device_id' or 'interface'.")

        return payload
