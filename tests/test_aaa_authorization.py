"""
Unit Test Suite for NOC Copilot v1.4 Phase 2: AAA & Role-Based Access Control.

Tests:
1. Role hierarchy and permissions across all 5 standard roles
2. Least-privilege authorization decisions
3. Session expiration rejection
4. Unknown action rejection
5. Audit trail completeness and decision recording
6. Multi-role identity behavior
"""

from datetime import datetime, timedelta, timezone
import pytest

from agents.security import (
    AAAAuthorizationService,
    AAAIdentity,
    AAARole,
    ACTION_PERMISSIONS,
)


@pytest.fixture
def aaa_service() -> AAAAuthorizationService:
    return AAAAuthorizationService()


# ---------------------------------------------------------------------------
# 1. Least Privilege Matrix Tests
# ---------------------------------------------------------------------------


def test_viewer_role_least_privilege(aaa_service: AAAAuthorizationService):
    """Verify NOC_VIEWER can only view telemetry and command center."""
    viewer = AAAIdentity(
        user_id="u-viewer",
        username="auditor",
        roles=[AAARole.NOC_VIEWER],
    )

    # Allowed
    assert aaa_service.authorize_action(viewer, "VIEW_TELEMETRY").allowed is True
    assert aaa_service.authorize_action(viewer, "VIEW_COMMAND_CENTER").allowed is True

    # Denied
    assert aaa_service.authorize_action(viewer, "RUN_DIAGNOSTICS").allowed is False
    assert aaa_service.authorize_action(viewer, "PROPOSE_PLAN_DRY_RUN").allowed is False
    assert aaa_service.authorize_action(viewer, "APPROVE_PLAN_LAB").allowed is False
    assert aaa_service.authorize_action(viewer, "APPROVE_PLAN_PROD_1ST_SEAT").allowed is False
    assert aaa_service.authorize_action(viewer, "EMERGENCY_OVERRIDE").allowed is False


def test_operator_role_permissions(aaa_service: AAAAuthorizationService):
    """Verify NOC_OPERATOR can run diagnostics and propose plans in DRY_RUN."""
    op = AAAIdentity(
        user_id="u-op",
        username="operator_1",
        roles=[AAARole.NOC_OPERATOR],
    )

    # Allowed
    assert aaa_service.authorize_action(op, "VIEW_TELEMETRY").allowed is True
    assert aaa_service.authorize_action(op, "RUN_DIAGNOSTICS").allowed is True
    assert aaa_service.authorize_action(op, "PROPOSE_PLAN_DRY_RUN").allowed is True

    # Denied
    assert aaa_service.authorize_action(op, "APPROVE_PLAN_LAB").allowed is False
    assert aaa_service.authorize_action(op, "APPROVE_PLAN_PROD_1ST_SEAT").allowed is False
    assert aaa_service.authorize_action(op, "APPROVE_PLAN_PROD_2ND_SEAT").allowed is False


def test_engineer_role_permissions(aaa_service: AAAAuthorizationService):
    """Verify NOC_ENGINEER can approve lab plans and provide 1st-seat production sign-off."""
    eng = AAAIdentity(
        user_id="u-eng",
        username="senior_eng",
        roles=[AAARole.NOC_ENGINEER],
    )

    # Allowed
    assert aaa_service.authorize_action(eng, "APPROVE_PLAN_LAB").allowed is True
    assert aaa_service.authorize_action(eng, "APPROVE_PLAN_PROD_1ST_SEAT").allowed is True

    # Denied (requires NOC_ADMIN for 2nd seat)
    assert aaa_service.authorize_action(eng, "APPROVE_PLAN_PROD_2ND_SEAT").allowed is False
    assert aaa_service.authorize_action(eng, "EMERGENCY_OVERRIDE").allowed is False


def test_admin_role_permissions(aaa_service: AAAAuthorizationService):
    """Verify NOC_ADMIN can provide 2nd-seat quorum approval and fetch secret references."""
    admin = AAAIdentity(
        user_id="u-admin",
        username="principal_admin",
        roles=[AAARole.NOC_ADMIN],
    )

    # Allowed
    assert aaa_service.authorize_action(admin, "APPROVE_PLAN_LAB").allowed is True
    assert aaa_service.authorize_action(admin, "APPROVE_PLAN_PROD_1ST_SEAT").allowed is True
    assert aaa_service.authorize_action(admin, "APPROVE_PLAN_PROD_2ND_SEAT").allowed is True
    assert aaa_service.authorize_action(admin, "FETCH_SECRET_MATERIAL").allowed is True

    # Denied (Emergency override reserved for Security Officer)
    assert aaa_service.authorize_action(admin, "EMERGENCY_OVERRIDE").allowed is False


def test_security_officer_role_permissions(aaa_service: AAAAuthorizationService):
    """Verify SECURITY_OFFICER can execute emergency overrides."""
    sec_officer = AAAIdentity(
        user_id="u-sec",
        username="ciso",
        roles=[AAARole.SECURITY_OFFICER],
    )

    assert aaa_service.authorize_action(sec_officer, "EMERGENCY_OVERRIDE").allowed is True
    assert aaa_service.authorize_action(sec_officer, "FETCH_SECRET_MATERIAL").allowed is True
    assert aaa_service.authorize_action(sec_officer, "APPROVE_PLAN_LAB").allowed is True


# ---------------------------------------------------------------------------
# 2. Session Expiration & Audit Trail Tests
# ---------------------------------------------------------------------------


def test_expired_session_rejection(aaa_service: AAAAuthorizationService):
    """Verify expired session is rejected regardless of roles."""
    now = datetime.now(timezone.utc)
    expired_user = AAAIdentity(
        user_id="u-expired",
        username="timed_out_admin",
        roles=[AAARole.NOC_ADMIN],
        expires_at=now - timedelta(minutes=5),
    )

    decision = aaa_service.authorize_action(expired_user, "VIEW_TELEMETRY")
    assert decision.allowed is False
    assert "session expired" in decision.reason.lower()


def test_unknown_action_rejection(aaa_service: AAAAuthorizationService):
    """Verify arbitrary or unregistered actions are safely denied."""
    admin = AAAIdentity(
        user_id="u-admin",
        username="admin",
        roles=[AAARole.NOC_ADMIN],
    )

    decision = aaa_service.authorize_action(admin, "ARBITRARY_SHELL_COMMAND")
    assert decision.allowed is False
    assert "Unknown or unregistered action" in decision.reason


def test_audit_trail_recording(aaa_service: AAAAuthorizationService):
    """Verify all authorization queries are appended to the audit trail."""
    user = AAAIdentity(
        user_id="u-user",
        username="test_user",
        roles=[AAARole.NOC_OPERATOR],
    )

    aaa_service.authorize_action(user, "VIEW_TELEMETRY", target_resource="core-01")
    aaa_service.authorize_action(user, "APPROVE_PLAN_LAB", target_resource="plan-123")

    trail = aaa_service.get_audit_trail()
    assert len(trail) == 2
    assert trail[0].action == "VIEW_TELEMETRY"
    assert trail[0].allowed is True
    assert trail[0].target_resource == "core-01"
    assert trail[1].action == "APPROVE_PLAN_LAB"
    assert trail[1].allowed is False
    assert trail[1].target_resource == "plan-123"
