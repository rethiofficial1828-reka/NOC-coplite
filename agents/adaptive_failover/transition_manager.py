"""
Transition Manager Module for Adaptive Multi-Provider Failover Subsystem.

Implements state machine controlling network transitions (STABLE, DEGRADING, FAILOVER_CANDIDATE,
APPROVAL_REQUIRED, PRECHECK, EXECUTING, VERIFYING, STABLE_ON_ALTERNATE, FAILBACK_CANDIDATE, STABLE_ON_PRIMARY).
Rejects invalid state transitions and prevents duplicate transition runs.
"""

import threading
from typing import Dict, Set, Tuple

from agents.core.exceptions import ValidationError
from agents.core.logger import get_agent_logger
from agents.adaptive_failover.adaptive_models import TransitionStatus

logger = get_agent_logger("NetworkTransitionManager")


class NetworkTransitionManager:
    """
    Thread-safe state machine governing network failover and failback transition lifecycles.
    """

    VALID_TRANSITIONS: Dict[TransitionStatus, Set[TransitionStatus]] = {
        TransitionStatus.STABLE: {TransitionStatus.DEGRADING, TransitionStatus.FAILOVER_CANDIDATE},
        TransitionStatus.DEGRADING: {TransitionStatus.FAILOVER_CANDIDATE, TransitionStatus.STABLE},
        TransitionStatus.FAILOVER_CANDIDATE: {TransitionStatus.APPROVAL_REQUIRED, TransitionStatus.STABLE},
        TransitionStatus.APPROVAL_REQUIRED: {TransitionStatus.PRECHECK, TransitionStatus.STABLE, TransitionStatus.FAILOVER_CANDIDATE},
        TransitionStatus.PRECHECK: {TransitionStatus.EXECUTING, TransitionStatus.STABLE, TransitionStatus.FAILOVER_CANDIDATE},
        TransitionStatus.EXECUTING: {TransitionStatus.VERIFYING, TransitionStatus.STABLE},
        TransitionStatus.VERIFYING: {TransitionStatus.STABLE_ON_ALTERNATE, TransitionStatus.STABLE, TransitionStatus.DEGRADING},
        TransitionStatus.STABLE_ON_ALTERNATE: {TransitionStatus.FAILBACK_CANDIDATE, TransitionStatus.DEGRADING},
        TransitionStatus.FAILBACK_CANDIDATE: {TransitionStatus.APPROVAL_REQUIRED, TransitionStatus.STABLE_ON_ALTERNATE},
        TransitionStatus.STABLE_ON_PRIMARY: {TransitionStatus.DEGRADING, TransitionStatus.FAILOVER_CANDIDATE, TransitionStatus.STABLE},
    }

    def __init__(self, initial_state: TransitionStatus = TransitionStatus.STABLE) -> None:
        self._current_state = initial_state
        self._active_provider = "ISP-A"
        self._primary_provider = "ISP-A"
        self._alternate_provider = "ISP-B"
        self._lock = threading.RLock()

    @property
    def current_state(self) -> TransitionStatus:
        with self._lock:
            return self._current_state

    @property
    def active_provider(self) -> str:
        with self._lock:
            return self._active_provider

    def transition_to(self, new_state: TransitionStatus, provider_change: bool = False, new_active_provider: str = "") -> Tuple[bool, str]:
        """
        Attempt a state transition in the state machine.

        Args:
            new_state: Target TransitionStatus.
            provider_change: True if active provider changes.
            new_active_provider: New active provider name.

        Returns:
            Tuple of (success_bool, message).
        """
        with self._lock:
            allowed = self.VALID_TRANSITIONS.get(self._current_state, set())
            if new_state not in allowed and new_state != self._current_state:
                msg = f"Invalid state transition '{self._current_state.value}' -> '{new_state.value}'"
                logger.warning(f"NetworkTransitionManager: {msg}")
                return False, msg

            prev = self._current_state
            self._current_state = new_state
            if provider_change and new_active_provider:
                self._active_provider = new_active_provider

            logger.info(
                f"NetworkTransitionManager: State transitioned '{prev.value}' -> '{self._current_state.value}' "
                f"(Active Provider: '{self._active_provider}')"
            )
            return True, "TRANSITION_SUCCESS"
