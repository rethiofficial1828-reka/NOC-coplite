"""
Thread-Safe Event Bus Implementation.

Provides topic-based and predicate-filtered event publishing, subscribing,
and subscriber exception isolation for decoupling framework agents.
"""

import threading
from typing import Callable, Dict, List, Optional
import uuid

from agents.core.exceptions import EventError
from agents.core.logger import get_agent_logger
from agents.events.event import Event
from agents.events.subscriber import SubscriberSubscription

logger = get_agent_logger("EventBus")


class SubscriptionRecord:
    """Internal record holding subscription metadata."""

    def __init__(
        self,
        subscription_id: str,
        topic: str,
        subscription: SubscriberSubscription,
    ) -> None:
        self.subscription_id = subscription_id
        self.topic = topic
        self.subscription = subscription


class EventBus:
    """
    Thread-safe Event Bus supporting publish-subscribe event-driven architecture.
    """

    _global_instance: Optional["EventBus"] = None
    _global_lock = threading.Lock()

    def __init__(self) -> None:
        self._subscriptions: Dict[str, List[SubscriptionRecord]] = {}
        self._sub_index: Dict[str, SubscriptionRecord] = {}
        self._lock = threading.RLock()

    @classmethod
    def get_global(cls) -> "EventBus":
        """Get or create the global singleton EventBus instance."""
        if cls._global_instance is None:
            with cls._global_lock:
                if cls._global_instance is None:
                    cls._global_instance = cls()
        return cls._global_instance

    def subscribe(
        self,
        topic: str,
        callback: Callable[[Event], None],
        predicate: Optional[Callable[[Event], bool]] = None,
    ) -> str:
        """
        Subscribe to events on a specific topic or '*' for all topics.

        Args:
            topic: Topic identifier or '*' wildcard.
            callback: Function to invoke when event is published.
            predicate: Optional filter predicate accepting Event and returning bool.

        Returns:
            Unique subscription ID.
        """
        if not topic:
            raise EventError("Topic string cannot be empty.")
        if not callable(callback):
            raise EventError("Callback must be a callable object.")

        subscription_id = str(uuid.uuid4())
        sub = SubscriberSubscription(callback=callback, predicate=predicate)
        record = SubscriptionRecord(
            subscription_id=subscription_id, topic=topic, subscription=sub
        )

        with self._lock:
            if topic not in self._subscriptions:
                self._subscriptions[topic] = []
            self._subscriptions[topic].append(record)
            self._sub_index[subscription_id] = record

        logger.debug(f"Subscribed callback to topic '{topic}' [sub_id={subscription_id}]")
        return subscription_id

    def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe a callback using its subscription ID.

        Args:
            subscription_id: Unique subscription ID returned by subscribe().

        Returns:
            True if subscription was found and removed, False otherwise.
        """
        with self._lock:
            record = self._sub_index.pop(subscription_id, None)
            if record is None:
                return False

            topic_list = self._subscriptions.get(record.topic, [])
            self._subscriptions[record.topic] = [
                r for r in topic_list if r.subscription_id != subscription_id
            ]
            if not self._subscriptions[record.topic]:
                del self._subscriptions[record.topic]

            logger.debug(f"Unsubscribed subscription '{subscription_id}' from topic '{record.topic}'")
            return True

    def publish(self, event: Event) -> int:
        """
        Publish an event to all matching subscribers.

        Args:
            event: Event object to publish.

        Returns:
            Number of subscribers notified.
        """
        if not isinstance(event, Event):
            raise EventError("Published object must be an instance of Event.")

        matching_records: List[SubscriptionRecord] = []
        with self._lock:
            # Topic-specific subscribers
            if event.event_type in self._subscriptions:
                matching_records.extend(self._subscriptions[event.event_type])
            # Wildcard subscribers
            if "*" in self._subscriptions:
                matching_records.extend(self._subscriptions["*"])

        notified_count = 0
        for record in matching_records:
            try:
                if record.subscription.matches(event):
                    record.subscription.notify(event)
                    notified_count += 1
            except Exception as e:
                logger.error(
                    f"Error in subscriber callback [sub_id={record.subscription_id}] for event '{event.event_type}': {e}",
                    exc_info=True,
                )

        logger.debug(f"Published event '{event.event_type}' (ID={event.event_id}) to {notified_count} subscribers.")
        return notified_count

    def clear(self) -> None:
        """Clear all subscriptions."""
        with self._lock:
            self._subscriptions.clear()
            self._sub_index.clear()
