"""
Transition Memory Module for Adaptive Multi-Provider Failover Subsystem.

Stores immutable transition history records and integrates with EvidenceRegistry and InvestigationContext
to supply historical evidence for future path scoring decisions.
"""

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional

from agents.core.logger import get_agent_logger
from agents.adaptive_failover.adaptive_models import TransitionRecord

logger = get_agent_logger("TransitionMemory")


class TransitionMemory:
    """
    Historical transition memory preserving immutable transition evidence.
    """

    def __init__(self) -> None:
        self._records: List[TransitionRecord] = []
        self._provider_penalties: Dict[str, float] = {}
        self._lock = threading.RLock()

    def record_transition_event(self, record: TransitionRecord, verification_passed: bool = True) -> None:
        """
        Record a provider transition into memory and update historical penalty weights.
        """
        with self._lock:
            self._records.append(record)
            if not verification_passed:
                p = record.to_provider
                self._provider_penalties[p] = self._provider_penalties.get(p, 0.0) + 15.0
                logger.warning(
                    f"TransitionMemory: Recorded verification failure for '{p}'. "
                    f"Historical penalty increased to {self._provider_penalties[p]:.1f} points."
                )

    def get_historical_penalty(self, provider_name: str) -> float:
        """Retrieve historical penalty weight accumulated from prior failed failover transitions."""
        with self._lock:
            return self._provider_penalties.get(provider_name, 0.0)

    def get_all_records(self) -> List[TransitionRecord]:
        """Retrieve copy of all recorded transition records."""
        with self._lock:
            return list(self._records)

    def get_recent_history(self, limit: int = 50) -> List[TransitionRecord]:
        """Retrieve recent transition history records."""
        with self._lock:
            return list(self._records[-limit:])
