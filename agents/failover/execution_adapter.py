"""
Execution Adapter Interface Module for Enterprise Controlled Failover Execution Engine.

Defines strict abstract interface IExecutionAdapter and the structural Protocol
INetworkProviderDelegate for authorized enterprise network provider delegates.
Guarantees NO arbitrary shell commands, SSH command strings, or raw script execution can enter
the execution boundary. Accepts only strongly-typed, validated network actions.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from agents.failover.failover_models import ExecutionStep



@runtime_checkable
class INetworkProviderDelegate(Protocol):
    """
    Structural protocol defining the production contract for authorized enterprise
    network provider delegates supplied to AuthorizedNetworkAdapter.

    Production implementations must satisfy all three methods:
      - is_ready()              — non-mutating readiness probe used during precheck.
      - execute_typed_action()  — mutating execution of a pre-authorized network action.
      - rollback_typed_action() — rollback of a previously executed action.

    Using typing.Protocol (structural subtyping) means concrete delegates do NOT need
    to inherit from this class; they satisfy the contract by simply implementing the
    required methods.  isinstance(obj, INetworkProviderDelegate) is supported at
    registration time via @runtime_checkable.
    """

    def is_ready(self) -> bool:
        """
        Non-mutating readiness probe.

        Must return True only when the provider's control-plane API or hardware
        integration is operational and able to accept execution commands.
        Called during pre-execution validation (precheck) without mutating
        any network state.
        """
        ...

    def execute_typed_action(
        self,
        action_type: str,
        target: str,
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute a strongly-typed, pre-authorized network action.

        Args:
            action_type: One of the adapter's SUPPORTED_ACTIONS.
            target:      Device name, node ID, or WAN interface key.
            parameters:  Validated parameter map (no shell/credential keys).

        Returns:
            Result metadata dict (must not contain unmasked credentials).
        """
        ...

    def rollback_typed_action(
        self,
        action_type: str,
        target: str,
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Roll back a previously executed typed network action.

        Args:
            action_type: Original action type being reversed.
            target:      Device name, node ID, or WAN interface key.
            parameters:  Parameter map from the original step.

        Returns:
            Rollback result metadata dict.
        """
        ...


class IExecutionAdapter(ABC):
    """
    Abstract Interface for strongly-typed, pre-authorized network execution adapters.
    """

    SUPPORTED_ACTIONS = [
        "FAILOVER_PROVIDER",
        "FAILBACK_PROVIDER",
        "ENABLE_BACKUP_PATH",
        "DISABLE_DEGRADED_PATH",
        "SWITCH_INTERFACE",
    ]

    def get_supported_actions(self) -> list[str]:
        """Return list of pre-authorized, supported action types."""
        return list(self.SUPPORTED_ACTIONS)

    def execute_action(
        self,
        target: str,
        action_type: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Convenience wrapper to execute a typed action given target, action_type, and parameters.
        Delegates to validate_target, validate_action, and execute without duplicating logic.
        """
        params = parameters or {}
        if not self.verify_capability():
            return {
                "success": False,
                "error": f"UNAUTHORIZED: {self.adapter_name} is not authorized or capability check failed.",
            }
        if not self.validate_target(target):
            return {
                "success": False,
                "error": f"INVALID_TARGET: Target '{target}' failed security validation.",
            }
        if not self.validate_action(action_type, params):
            return {
                "success": False,
                "error": f"INVALID_ACTION: Action '{action_type}' failed validation or is unsupported.",
            }
        try:
            step = ExecutionStep(
                sequence=1,
                adapter=self.adapter_name,
                target=target,
                action_type=action_type,
                parameters=params,
            )
            exec_res = self.execute(step)
            return {
                "success": True,
                "dry_run": self.adapter_name == "DryRunExecutionAdapter",
                "result": exec_res,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"EXECUTION_FAILED: {e}",
            }

    @property
    @abstractmethod
    def adapter_name(self) -> str:
        """Name identifier of the execution adapter."""
        pass

    @abstractmethod
    def validate_target(self, target: str) -> bool:
        """
        Verify target device or WAN interface identifier.

        Args:
            target: Device name, node ID, or interface key.
        """
        pass

    @abstractmethod
    def validate_action(self, action_type: str, parameters: Dict[str, Any]) -> bool:
        """
        Validate that action_type is a supported typed action and parameters match schema.

        Args:
            action_type: FAILOVER_PROVIDER, FAILBACK_PROVIDER, etc.
            parameters: Parameter map.
        """
        pass

    @abstractmethod
    def verify_capability(self) -> bool:
        """Verify whether adapter is authorized and operational."""
        pass

    @abstractmethod
    def execute(self, step: ExecutionStep) -> Dict[str, Any]:
        """
        Execute a single typed execution step.

        Args:
            step: ExecutionStep object.

        Returns:
            Dict containing adapter result metadata.
        """
        pass

    @abstractmethod
    def prepare_rollback(self, step: ExecutionStep) -> ExecutionStep:
        """
        Generate complementary inverse ExecutionStep for automatic rollback.

        Args:
            step: Primary ExecutionStep.

        Returns:
            Inverse ExecutionStep object.
        """
        pass

    @abstractmethod
    def rollback(self, step: ExecutionStep) -> Dict[str, Any]:
        """
        Execute rollback of a previously executed step.

        Args:
            step: ExecutionStep to roll back.

        Returns:
            Dict containing rollback result metadata.
        """
        pass
