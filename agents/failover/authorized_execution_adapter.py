"""
Authorized Network Adapter Boundary Module for Enterprise Controlled Failover Engine.

Provides formal boundary interface for authorized production network integration.
Defaults to NOT_CONFIGURED state unless explicitly configured by an enterprise administrator.
Enforces strict secret masking, credential isolation, and anti-arbitrary-command validation.
"""

from typing import Any, Dict, Optional

from agents.core.exceptions import ExecutionError, ValidationError
from agents.core.logger import get_agent_logger
from agents.failover.execution_adapter import IExecutionAdapter, INetworkProviderDelegate
from agents.failover.failover_models import ExecutionStep

logger = get_agent_logger("AuthorizedNetworkAdapter")


class AuthorizedNetworkAdapter(IExecutionAdapter):
    """
    Authorized execution adapter for production network integrations.

    Defaults to NOT_CONFIGURED unless an authorized integration provider is configured.
    Guarantees no raw SSH strings or unmasked credentials are exposed.
    """

    def __init__(self, is_enabled: bool = False, provider_delegate: Optional[INetworkProviderDelegate] = None) -> None:
        self._is_enabled = is_enabled
        self._provider_delegate = provider_delegate

    @property
    def adapter_name(self) -> str:
        return "AuthorizedNetworkAdapter"

    def validate_target(self, target: str) -> bool:
        if not target or not isinstance(target, str):
            return False
        # Reject executable injection syntax
        for s in [";", "&&", "||", "`", "$", "|", ">", "<", "sudo", "rm ", "bash", "sh"]:
            if s in target:
                return False
        return True

    def validate_action(self, action_type: str, parameters: Dict[str, Any]) -> bool:
        if action_type not in self.SUPPORTED_ACTIONS:
            return False
        forbidden_keys = ["cmd", "command", "shell", "exec", "script"]
        # Ensure no credential keys, command keys, or secret strings in parameters
        for k in parameters:
            if k.lower() in forbidden_keys:
                logger.warning(f"AuthorizedNetworkAdapter rejected parameter key '{k}' containing command keyword.")
                return False
            if any(secret_word in k.lower() for secret_word in ["password", "secret", "token", "private_key", "auth"]):
                logger.warning(f"AuthorizedNetworkAdapter rejected parameter key '{k}' containing credential keyword.")
                return False
        return True

    def verify_capability(self) -> bool:
        if not self._is_enabled or self._provider_delegate is None:
            return False
        if hasattr(self._provider_delegate, "verify_capability") and callable(getattr(self._provider_delegate, "verify_capability")):
            try:
                res = self._provider_delegate.verify_capability()
                if isinstance(res, bool):
                    return res
            except Exception:
                return False
        if hasattr(self._provider_delegate, "health_check") and callable(getattr(self._provider_delegate, "health_check")):
            try:
                res = self._provider_delegate.health_check()
                if isinstance(res, bool):
                    return res
            except Exception:
                return False
        if hasattr(self._provider_delegate, "is_ready") and callable(getattr(self._provider_delegate, "is_ready")):
            try:
                res = self._provider_delegate.is_ready()
                if isinstance(res, bool):
                    return res
            except Exception:
                return False
        return True

    def execute(self, step: ExecutionStep) -> Dict[str, Any]:
        """
        Execute typed action through authorized network provider delegate.
        """
        if not self.verify_capability():
            logger.warning("AuthorizedNetworkAdapter called while NOT_CONFIGURED.")
            raise ExecutionError(
                "AuthorizedNetworkAdapter is NOT_CONFIGURED. Real network configuration edits "
                "require explicit enterprise adapter registration."
            )

        if not self.validate_target(step.target) or not self.validate_action(step.action_type, step.parameters):
            raise ValidationError(f"Invalid target or action parameters for step '{step.step_id}'")

        try:
            logger.info(f"AuthorizedNetworkAdapter executing typed step '{step.step_id}' via registered delegate.")
            res = self._provider_delegate.execute_typed_action(
                action_type=step.action_type,
                target=step.target,
                parameters=step.parameters,
            )
            # Mask any potential sensitive keys in return payload
            return self._mask_secrets(res)
        except Exception as e:
            logger.error(f"AuthorizedNetworkAdapter execution failed for step '{step.step_id}': {e}")
            raise ExecutionError(f"AuthorizedNetworkAdapter failed: {e}") from e

    def prepare_rollback(self, step: ExecutionStep) -> ExecutionStep:
        inverse_action = "FAILBACK_PROVIDER" if step.action_type == "FAILOVER_PROVIDER" else "ENABLE_BACKUP_PATH"
        return ExecutionStep(
            sequence=step.sequence + 10,
            adapter=self.adapter_name,
            target=step.target,
            action_type=inverse_action,
            parameters=dict(step.parameters),
            reversible=True,
            rollback_step_id=step.step_id,
        )

    def rollback(self, step: ExecutionStep) -> Dict[str, Any]:
        if not self.verify_capability():
            raise ExecutionError("AuthorizedNetworkAdapter rollback failed: NOT_CONFIGURED.")

        logger.info(f"AuthorizedNetworkAdapter rolling back step '{step.step_id}'")
        res = self._provider_delegate.rollback_typed_action(
            action_type=step.action_type,
            target=step.target,
            parameters=step.parameters,
        )
        return self._mask_secrets(res)

    def _mask_secrets(self, data: Any) -> Any:
        """Sanitize dictionaries to ensure no credentials escape into logs or events."""
        if isinstance(data, dict):
            masked = {}
            for k, v in data.items():
                if isinstance(v, dict):
                    masked[k] = self._mask_secrets(v)
                elif isinstance(v, list):
                    masked[k] = [self._mask_secrets(item) for item in v]
                elif any(sec in k.lower() for sec in ["password", "secret", "token", "key", "auth"]):
                    masked[k] = "******"
                else:
                    masked[k] = v
            return masked
        return data
