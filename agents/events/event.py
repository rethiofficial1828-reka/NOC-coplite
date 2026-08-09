"""
Event Model Definition.
"""

from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

from pydantic import BaseModel, Field


class Event(BaseModel):
    """
    Strongly-typed representation of an event in the NOC Copilot Event Bus.
    """

    event_id: str = Field(
        default_factory=lambda: str(uuid4()), description="Unique event identifier"
    )
    event_type: str = Field(
        ..., description="Categorical type/topic of event (e.g. telemetry.received)"
    )
    source: str = Field(
        ..., description="Name of agent or component emitting the event"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Event creation timestamp UTC",
    )
    payload: Dict[str, Any] = Field(
        default_factory=dict, description="Structured event data"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Contextual headers and trace attributes"
    )
