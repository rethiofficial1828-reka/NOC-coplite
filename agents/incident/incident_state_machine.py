"""
Incident State Machine Module.

Enforces valid status transitions for incident lifecycle states (NEW, OPEN, ACKNOWLEDGED,
IN_PROGRESS, MITIGATED, RESOLVED, CLOSED) and records corresponding timeline audit entries.
"""

from datetime import datetime, timezone
from typing import Dict, Set

from agents.core.exceptions import ValidationError
from agents.core.logger import get_agent_logger
from agents.incident.incident_models import (
    IncidentRecord,
    IncidentStatus,
    IncidentTimeline,
)

logger = get_agent_logger("IncidentStateMachine")


class IncidentStateMachine:
    """
    State machine enforcing valid incident status state transitions.
    """

    VALID_TRANSITIONS: Dict[IncidentStatus, Set[IncidentStatus]] = {
        IncidentStatus.NEW: {
            IncidentStatus.OPEN,
            IncidentStatus.CLOSED,
        },
        IncidentStatus.OPEN: {
            IncidentStatus.ACKNOWLEDGED,
            IncidentStatus.IN_PROGRESS,
            IncidentStatus.MITIGATED,
            IncidentStatus.RESOLVED,
            IncidentStatus.CLOSED,
        },
        IncidentStatus.ACKNOWLEDGED: {
            IncidentStatus.IN_PROGRESS,
            IncidentStatus.MITIGATED,
            IncidentStatus.RESOLVED,
            IncidentStatus.CLOSED,
        },
        IncidentStatus.IN_PROGRESS: {
            IncidentStatus.MITIGATED,
            IncidentStatus.RESOLVED,
            IncidentStatus.CLOSED,
        },
        IncidentStatus.MITIGATED: {
            IncidentStatus.RESOLVED,
            IncidentStatus.OPEN,
            IncidentStatus.CLOSED,
        },
        IncidentStatus.RESOLVED: {
            IncidentStatus.CLOSED,
            IncidentStatus.OPEN,
        },
        IncidentStatus.CLOSED: {
            IncidentStatus.OPEN,
        },
    }

    @classmethod
    def can_transition(cls, current_status: IncidentStatus, target_status: IncidentStatus) -> bool:
        """
        Check if transition from current_status to target_status is permitted.

        Args:
            current_status: Current status enum.
            target_status: Target status enum.

        Returns:
            True if permitted, False otherwise.
        """
        if current_status == target_status:
            return True
        allowed = cls.VALID_TRANSITIONS.get(current_status, set())
        return target_status in allowed

    @classmethod
    def validate_transition(cls, current_status: IncidentStatus, target_status: IncidentStatus) -> None:
        """
        Validate transition or raise ValidationError.

        Args:
            current_status: Current status enum.
            target_status: Target status enum.

        Raises:
            ValidationError: If transition is forbidden.
        """
        if not cls.can_transition(current_status, target_status):
            raise ValidationError(
                f"Illegal incident status transition from '{current_status.value}' to '{target_status.value}'."
            )

    @classmethod
    def transition(
        cls,
        incident: IncidentRecord,
        target_status: IncidentStatus,
        reason: str = "",
        author: str = "System",
    ) -> IncidentRecord:
        """
        Execute status transition on an incident, adding a timeline entry and updating timestamps.

        Args:
            incident: Target IncidentRecord instance.
            target_status: Desired target status.
            reason: Optional human readable explanation for state change.
            author: Author/User initiating transition.

        Returns:
            Updated IncidentRecord instance.
        """
        if incident.status == target_status:
            return incident

        cls.validate_transition(incident.status, target_status)
        old_status = incident.status
        incident.status = target_status
        now = datetime.now(timezone.utc)
        incident.updated_at = now

        if target_status == IncidentStatus.RESOLVED and not incident.resolved_at:
            incident.resolved_at = now
        elif target_status == IncidentStatus.CLOSED and not incident.closed_at:
            incident.closed_at = now

        summary = f"Status changed from '{old_status.value}' to '{target_status.value}'"
        if reason:
            summary += f": {reason}"

        timeline_entry = IncidentTimeline(
            incident_id=incident.incident_id,
            event_type="STATUS_CHANGED",
            description=summary,
            timestamp=now,
            author=author,
            metadata={"old_status": old_status.value, "new_status": target_status.value, "reason": reason},
        )
        incident.timeline.append(timeline_entry)

        logger.info(f"Transitioned incident '{incident.incident_id}' to status '{target_status.value}'.")
        return incident
