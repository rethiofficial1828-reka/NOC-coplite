"""
Dry-Run Execution Adapter Module for Enterprise Controlled Failover Execution Engine.

Implements IExecutionAdapter for simulation and dry-run execution modes.
Validates execution steps, simulates state transitions, produces execution evidence,
and supports simulated rollback without modifying physical network equipment.
"""

from typing import Any, Dict
import uuid

from agents.core.exceptions import ExecutionError, ValidationError
from agents.core.logger import get_agent_logger
from agents.failover.execution_adapter import IExecutionAdapter
from agents.failover.failover_models import ExecutionStep

logger = get_agent_logger("DryRunExecutionAdapter")


class DryRunExecutionAdapter(IExecutionAdapter):
    """
    Default adapter providing safe dry-run simulation of network failover steps.
    """

    @property
    def adapter_name(self) -> str:
        return "DryRunExecutionAdapter"

    def validate_target(self, target: str) -> bool:
        if not target or target.strip() == "":
            return False
        # Reject arbitrary shell scripts or suspicious command characters
        suspicious = [";", "&&", "||", "`", "$", "|", ">", "<", "sudo", "rm ", "bash", "sh"]
        for s in suspicious:
            if s in target:
                logger.warning(f"DryRunExecutionAdapter rejected target with command injection attempt: '{target}'")
                return False
        return True

    def validate_action(self, action_type: str, parameters: Dict[str, Any]) -> bool:
        if action_type not in self.SUPPORTED_ACTIONS:
            logger.warning(f"DryRunExecutionAdapter rejected unsupported action: '{action_type}'")
            return False
        # Reject executable keys or command strings in parameters
        forbidden_keys = ["cmd", "command", "shell", "exec", "script"]
        for k, v in parameters.items():
            if k.lower() in forbidden_keys:
                logger.warning(f"DryRunExecutionAdapter rejected parameter key '{k}' containing command keyword.")
                return False
            if isinstance(v, str):
                for s in [";", "&&", "||", "`", "$(", "bash", "sh"]:
                    if s in v:
                        logger.warning(f"DryRunExecutionAdapter rejected parameter '{k}' containing executable syntax: '{v}'")
                        return False
        return True

    def verify_capability(self) -> bool:
        return True

    def execute(self, step: ExecutionStep) -> Dict[str, Any]:
        """
        Simulate step execution safely.
        """
        if not self.validate_target(step.target):
            raise ValidationError(f"Invalid target specified for step '{step.step_id}': '{step.target}'")

        if not self.validate_action(step.action_type, step.parameters):
            raise ValidationError(f"Invalid or unauthorized action '{step.action_type}' for step '{step.step_id}'")

        logger.info(
            f"DryRunExecutionAdapter SIMULATED step '{step.step_id}' "
            f"(Action: {step.action_type}, Target: {step.target}, Params: {step.parameters})"
        )

        simulated_state = {
            "status": "SIMULATED_SUCCESS",
            "step_id": step.step_id,
            "adapter": self.adapter_name,
            "target": step.target,
            "action_type": step.action_type,
            "executed_in_mode": "DRY_RUN",
            "simulated_active_provider": step.parameters.get("target_provider", "ISP-B"),
            "simulated_previous_provider": step.parameters.get("source_provider", "ISP-A"),
            "simulated_interface_state": "UP",
        }

        return simulated_state

    def prepare_rollback(self, step: ExecutionStep) -> ExecutionStep:
        """
        Create inverse ExecutionStep for dry-run rollback.
        """
        inverse_action = "FAILBACK_PROVIDER" if step.action_type == "FAILOVER_PROVIDER" else "ENABLE_BACKUP_PATH"
        inverse_params = dict(step.parameters)
        if "target_provider" in step.parameters and "source_provider" in step.parameters:
            inverse_params["target_provider"] = step.parameters["source_provider"]
            inverse_params["source_provider"] = step.parameters["target_provider"]

        return ExecutionStep(
            step_id=str(uuid.uuid4()),
            sequence=step.sequence + 10,
            adapter=self.adapter_name,
            target=step.target,
            action_type=inverse_action,
            parameters=inverse_params,
            timeout_sec=step.timeout_sec,
            reversible=True,
            rollback_step_id=step.step_id,
        )

    def rollback(self, step: ExecutionStep) -> Dict[str, Any]:
        """
        Simulate step rollback safely.
        """
        logger.info(f"DryRunExecutionAdapter SIMULATED ROLLBACK for step '{step.step_id}' (Target: {step.target})")
        return {
            "status": "SIMULATED_ROLLBACK_SUCCESS",
            "step_id": step.step_id,
            "adapter": self.adapter_name,
            "target": step.target,
            "action_type": step.action_type,
            "restored_provider": step.parameters.get("source_provider", "ISP-A"),
        }
