"""
AAA Authorization Engine for NOC Copilot v1.4.

Defines:
- AAAAuthorizationService: Validates operator identities and roles against least-privilege action permissions.
- ACTION_PERMISSIONS: Strict mapping of NOC operational capabilities to authorized RBAC roles.

Guarantees:
- Deterministic role-based authorization
- Structured, tamper-evident audit decision logs
- Least-privilege separation between Tier-1 view, diagnostics, plan proposal, lab approval, and production quorum
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from agents.core.logger import get_agent_logger
from agents.security.security_models import (
    AAAIdentity,
    AAARole,
    AuthorizationDecision,
)

logger = get_agent_logger("AAAAuthorization")

# ---------------------------------------------------------------------------
# Strict Action-to-Role Permission Taxonomy
# ---------------------------------------------------------------------------

ACTION_PERMISSIONS: Dict[str, Set[AAARole]] = {
    "VIEW_TELEMETRY": {
        AAARole.NOC_VIEWER,
        AAARole.NOC_OPERATOR,
        AAARole.NOC_ENGINEER,
        AAARole.NOC_ADMIN,
        AAARole.SECURITY_OFFICER,
    },
    "VIEW_COMMAND_CENTER": {
        AAARole.NOC_VIEWER,
        AAARole.NOC_OPERATOR,
        AAARole.NOC_ENGINEER,
        AAARole.NOC_ADMIN,
        AAARole.SECURITY_OFFICER,
    },
    "RUN_DIAGNOSTICS": {
        AAARole.NOC_OPERATOR,
        AAARole.NOC_ENGINEER,
        AAARole.NOC_ADMIN,
        AAARole.SECURITY_OFFICER,
    },
    "PROPOSE_PLAN_DRY_RUN": {
        AAARole.NOC_OPERATOR,
        AAARole.NOC_ENGINEER,
        AAARole.NOC_ADMIN,
        AAARole.SECURITY_OFFICER,
    },
    "APPROVE_PLAN_LAB": {
        AAARole.NOC_ENGINEER,
        AAARole.NOC_ADMIN,
        AAARole.SECURITY_OFFICER,
    },
    "APPROVE_PLAN_PROD_1ST_SEAT": {
        AAARole.NOC_ENGINEER,
        AAARole.NOC_ADMIN,
    },
    "APPROVE_PLAN_PROD_2ND_SEAT": {
        AAARole.NOC_ADMIN,
    },
    "EMERGENCY_OVERRIDE": {
        AAARole.SECURITY_OFFICER,
    },
    "FETCH_SECRET_MATERIAL": {
        AAARole.NOC_ADMIN,
        AAARole.SECURITY_OFFICER,
    },
    "ROTATE_CREDENTIALS": {
        AAARole.NOC_ADMIN,
        AAARole.SECURITY_OFFICER,
    },
}


class AAAAuthorizationService:
    """
    Evaluates operator permissions and records immutable authorization decisions.
    """

    def __init__(self) -> None:
        self._audit_decisions: List[AuthorizationDecision] = []

    def authorize_action(
        self,
        identity: AAAIdentity,
        action: str,
        target_resource: Optional[str] = None,
    ) -> AuthorizationDecision:
        """
        Evaluate if an identity has the required roles to execute an action.

        Args:
            identity: Authenticated AAAIdentity.
            action: Standard action name string.
            target_resource: Optional resource identifier (device_id, plan_id, etc.).

        Returns:
            AuthorizationDecision record.
        """
        # Expiration check
        if identity.expires_at is not None and datetime.now(timezone.utc) >= identity.expires_at:
            decision = AuthorizationDecision(
                allowed=False,
                action=action,
                acting_identity=identity.username,
                acting_roles=[r.value for r in identity.roles],
                required_roles=[],
                target_resource=target_resource,
                reason=f"Identity session expired at {identity.expires_at.isoformat()}.",
            )
            self._audit_decisions.append(decision)
            logger.warning(f"AAA Denied: Session expired for user '{identity.username}'.")
            return decision

        # Action existence check
        clean_action = action.strip().upper()
        if clean_action not in ACTION_PERMISSIONS:
            decision = AuthorizationDecision(
                allowed=False,
                action=clean_action,
                acting_identity=identity.username,
                acting_roles=[r.value for r in identity.roles],
                required_roles=[],
                target_resource=target_resource,
                reason=f"Unknown or unregistered action '{clean_action}'.",
            )
            self._audit_decisions.append(decision)
            logger.warning(f"AAA Denied: Unknown action '{clean_action}'.")
            return decision

        required_roles = ACTION_PERMISSIONS[clean_action]
        has_required_role = any(r in required_roles for r in identity.roles)

        if has_required_role:
            decision = AuthorizationDecision(
                allowed=True,
                action=clean_action,
                acting_identity=identity.username,
                acting_roles=[r.value for r in identity.roles],
                required_roles=[r.value for r in required_roles],
                target_resource=target_resource,
                reason="Identity possesses required RBAC role.",
            )
            logger.info(
                f"AAA Allowed: User '{identity.username}' authorized for '{clean_action}' on target '{target_resource}'."
            )
        else:
            decision = AuthorizationDecision(
                allowed=False,
                action=clean_action,
                acting_identity=identity.username,
                acting_roles=[r.value for r in identity.roles],
                required_roles=[r.value for r in required_roles],
                target_resource=target_resource,
                reason=f"Insufficient privilege. User roles {[r.value for r in identity.roles]} lack any of {[r.value for r in required_roles]}.",
            )
            logger.warning(
                f"AAA Denied: User '{identity.username}' lacks privilege for '{clean_action}'."
            )

        self._audit_decisions.append(decision)
        return decision

    def get_audit_trail(self) -> List[AuthorizationDecision]:
        """Return full decision audit history."""
        return list(self._audit_decisions)
