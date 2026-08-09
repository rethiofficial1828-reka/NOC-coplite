"""
Publisher Interface for Event Bus System.
"""

from typing import Protocol, runtime_checkable

from agents.events.event import Event


@runtime_checkable
class Publisher(Protocol):
    """Protocol for event publishers emitting events to the EventBus."""

    def publish(self, event: Event) -> None:
        """Publish an event to subscribers."""
        ...
