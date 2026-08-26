"""
Unit Test Suite for NOC Copilot v1.4 Phase 5: Production Quorum Gate.

Tests:
1. One-person approval is rejected (quorum incomplete)
2. Requester cannot approve their own plan (two-person rule)
3. Same person double approval on Seat 1 and Seat 2 is rejected
4. Valid two-person quorum (Seat 1: NOC_ENGINEER, Seat 2: NOC_ADMIN)
5. Plan-hash mismatch is rejected
6. Expired approval proposal is rejected
7. Role enforcement across signature seats
8. Audit log records safe metadata with zero secrets or private keys
"""

from datetime import datetime, timedelta, timezone
import pytest

from agents.failover import (
    ExecutionPlan,
    ExecutionStep,
    ProductionAuthorizationQuorumEngine,
    QuorumDecision,
)
from agents.security import AAAIdentity, AAARole


@pytest.fixture
def quorum_engine() -> ProductionAuthorizationQuorumEngine:
    return ProductionAuthorizationQuorumEngine()


@pytest.fixture
def sample_plan() -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="PLAN-TEST-001",
        decision_id="DEC-001",
        plan_hash="PENDING_HASH",
        source_path="ISP-A",
        destination_path="ISP-B",
        target_devices=["core-01"],
        steps=[
            ExecutionStep(sequence=1, target="core-01", action_type="SWITCH_INTERFACE", parameters={"to": "eth2"})
        ],
    )


@pytest.fixture
def operator_requester() -> AAAIdentity:
    return AAAIdentity(
        user_id="usr-requester",
        username="john.operator",
        roles=[AAARole.NOC_OPERATOR],
    )


@pytest.fixture
def engineer_approver() -> AAAIdentity:
    return AAAIdentity(
        user_id="usr-engineer",
        username="alice.engineer",
        roles=[AAARole.NOC_ENGINEER],
    )


@pytest.fixture
def admin_approver() -> AAAIdentity:
    return AAAIdentity(
        user_id="usr-admin",
        username="bob.admin",
        roles=[AAARole.NOC_ADMIN],
    )


# ---------------------------------------------------------------------------
# 1. Two-Person Rule & Seat Validations
# ---------------------------------------------------------------------------


def test_requester_cannot_be_approver(
    quorum_engine: ProductionAuthorizationQuorumEngine,
    sample_plan: ExecutionPlan,
    engineer_approver: AAAIdentity,
):
    """Verify requester cannot approve their own plan."""
    req_id = "REQ-001"
    decision = quorum_engine.propose_production_plan(req_id, sample_plan, engineer_approver)
    assert decision.final_decision == QuorumDecision.PENDING_QUORUM

    # Engineer attempts to approve own plan
    ok, errors = quorum_engine.submit_approval_seat(
        req_id,
        seat_number=1,
        approver=engineer_approver,
        plan_hash=decision.plan_hash,
    )
    assert ok is False
    assert any("Requester cannot be an approver" in e for e in errors)


def test_same_person_double_approval_rejected(
    quorum_engine: ProductionAuthorizationQuorumEngine,
    sample_plan: ExecutionPlan,
    operator_requester: AAAIdentity,
    admin_approver: AAAIdentity,
):
    """Verify same person cannot fill both Seat 1 and Seat 2."""
    req_id = "REQ-002"
    decision = quorum_engine.propose_production_plan(req_id, sample_plan, operator_requester)

    # Seat 1 by Admin
    ok1, _ = quorum_engine.submit_approval_seat(req_id, 1, admin_approver, decision.plan_hash)
    assert ok1 is True

    # Seat 2 by same Admin
    ok2, errors2 = quorum_engine.submit_approval_seat(req_id, 2, admin_approver, decision.plan_hash)
    assert ok2 is False
    assert any("distinct identities" in e for e in errors2)


def test_role_enforcement_on_seats(
    quorum_engine: ProductionAuthorizationQuorumEngine,
    sample_plan: ExecutionPlan,
    operator_requester: AAAIdentity,
    engineer_approver: AAAIdentity,
):
    """Verify Seat 2 strictly requires NOC_ADMIN role (NOC_ENGINEER rejected for Seat 2)."""
    req_id = "REQ-003"
    decision = quorum_engine.propose_production_plan(req_id, sample_plan, operator_requester)

    # Engineer attempts Seat 2
    ok, errors = quorum_engine.submit_approval_seat(req_id, 2, engineer_approver, decision.plan_hash)
    assert ok is False
    assert any("Seat 2 requires NOC_ADMIN role" in e for e in errors)


def test_valid_two_person_quorum(
    quorum_engine: ProductionAuthorizationQuorumEngine,
    sample_plan: ExecutionPlan,
    operator_requester: AAAIdentity,
    engineer_approver: AAAIdentity,
    admin_approver: AAAIdentity,
):
    """Verify valid distinct two-person quorum completes successfully."""
    req_id = "REQ-004"
    decision = quorum_engine.propose_production_plan(req_id, sample_plan, operator_requester)

    ok1, errs1 = quorum_engine.submit_approval_seat(req_id, 1, engineer_approver, decision.plan_hash)
    assert ok1 is True
    assert len(errs1) == 0

    ok2, errs2 = quorum_engine.submit_approval_seat(req_id, 2, admin_approver, decision.plan_hash)
    assert ok2 is True
    assert len(errs2) == 0


def test_plan_hash_mismatch_rejected(
    quorum_engine: ProductionAuthorizationQuorumEngine,
    sample_plan: ExecutionPlan,
    operator_requester: AAAIdentity,
    engineer_approver: AAAIdentity,
):
    """Verify corrupted or altered plan hash is rejected."""
    req_id = "REQ-005"
    quorum_engine.propose_production_plan(req_id, sample_plan, operator_requester)

    ok, errors = quorum_engine.submit_approval_seat(
        req_id,
        1,
        engineer_approver,
        plan_hash="badf00dbadf00dbadf00d" * 3,
    )
    assert ok is False
    assert any("Plan hash mismatch" in e for e in errors)


def test_expired_approval_rejected(
    quorum_engine: ProductionAuthorizationQuorumEngine,
    sample_plan: ExecutionPlan,
    operator_requester: AAAIdentity,
    engineer_approver: AAAIdentity,
):
    """Verify approval submitted after expiration is rejected."""
    req_id = "REQ-006"
    # Propose with negative validity to force expiration
    decision = quorum_engine.propose_production_plan(req_id, sample_plan, operator_requester, validity_minutes=-1.0)

    ok, errors = quorum_engine.submit_approval_seat(req_id, 1, engineer_approver, decision.plan_hash)
    assert ok is False
    assert any("EXPIRED" in e for e in errors)


def test_audit_trail_redaction(
    quorum_engine: ProductionAuthorizationQuorumEngine,
    sample_plan: ExecutionPlan,
    operator_requester: AAAIdentity,
    engineer_approver: AAAIdentity,
):
    """Verify structured audit logs record safe metadata without secret tokens."""
    req_id = "REQ-007"
    decision = quorum_engine.propose_production_plan(req_id, sample_plan, operator_requester)
    quorum_engine.submit_approval_seat(req_id, 1, engineer_approver, decision.plan_hash)

    logs = quorum_engine.get_audit_log()
    assert len(logs) >= 2
    for log in logs:
        assert "plan_hash" in log
        assert "request_id" in log
        assert "password" not in str(log).lower()
        assert "private_key" not in str(log).lower()
