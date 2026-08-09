"""
Subscriber Specification for Event Bus.
"""

from typing import Callable, Optional, Protocol, runtime_checkable

from agents.events.event import Event


@runtime_checkable
class Subscriber(Protocol):
    """Protocol for event subscriber callbacks."""

    def __call__(self, event: Event) -> None:
        """Handle incoming event."""
        ...


EventFilterPredicate = Callable[[Event], bool]


class SubscriberSubscription:
    """Wrapper holding subscriber callback and optional filter predicate."""

    def __init__(
        self,
        callback: Callable[[Event], None],
        predicate: Optional[EventFilterPredicate] = None,
    ) -> None:
        self.callback = callback
        self.predicate = predicate

    def matches(self, event: Event) -> bool:
        """Return True if subscription accepts the given event."""
        if self.predicate is None:
            return True
        try:
            return self.predicate(event)
        except Exception:
            return False

    def notify(self, event: Event) -> None:
        """Invoke callback if event matches predicate."""
        if self.matches(event):
            self.callback(event)
