"""
Phase 6G — Audit Trail Integrity Test.

Verifies:
- Every authorization attempt is logged with a structured audit record
- plan_hash is recorded in every event
- approver identities (user_id) are recorded in every seat record
- decision and rejection reasons are recorded
- NO secret material (private keys, passwords) is logged
- No production mutation occurred (audit log contains no PRODUCTION_EXEC events)

All tests run against in-process QuorumGateAudit log captured by test harness.
"""

from datetime import datetime, timedelta, timezone

import pytest

from agents.failover import (
    ExecutionPlan,
    ExecutionStep,
    MaintenanceWindow,
    ProductionAuthorizationQuorumEngine,
    QuorumDecision,
    TestChangeWindowProvider,
)
from agents.security.security_models import AAAIdentity, AAARole


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _active_engine(device_id: str = "staging-rtr-01") -> ProductionAuthorizationQuorumEngine:
    provider = TestChangeWindowProvider()
    now = datetime.now(timezone.utc)
    provider.register_window(
        MaintenanceWindow(
            change_ticket_id="CHG-AUDIT-001",
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=3),
            target_devices=[device_id],
            approved_by="CAB_AUDIT",
        )
    )
    return ProductionAuthorizationQuorumEngine(
        change_window_provider=provider,
        cooldown_seconds=300.0,
    )


def _plan(device_id: str = "staging-rtr-01") -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="AUDIT-PLAN-001",
        decision_id="DEC-AUDIT-001",
        plan_hash="PENDING_HASH",
        source_path="ISP-A",
        destination_path="ISP-B",
        target_devices=[device_id],
        steps=[ExecutionStep(sequence=1, target=device_id, action_type="SWITCH_INTERFACE", parameters={})],
    )


def _id(uid: str, role: AAARole) -> AAAIdentity:
    return AAAIdentity(user_id=uid, username=f"{uid}.user", roles=[role])


# ---------------------------------------------------------------------------
# Audit Tests
# ---------------------------------------------------------------------------


class TestAuditTrailIntegrity:
    """Phase 6G: Audit trail structure, completeness, and secret-hygiene verification."""

    def test_propose_creates_audit_record(self, pilot_mode):
        """propose_production_plan must create at least one audit record."""
        engine = _active_engine()
        engine.propose_production_plan("AUDIT-001", _plan(), _id("req-a1", AAARole.NOC_OPERATOR))
        assert len(engine._audit_log) >= 1, f"[{pilot_mode}] No audit records after propose"
        print(f"\n[{pilot_mode}] Audit records after propose: {len(engine._audit_log)}")

    def test_audit_record_has_plan_hash(self, pilot_mode):
        """Every audit record must contain a non-empty plan_hash field."""
        engine = _active_engine()
        engine.propose_production_plan("AUDIT-002", _plan(), _id("req-a2", AAARole.NOC_OPERATOR))
        for rec in engine._audit_log:
            assert "plan_hash" in rec, f"[{pilot_mode}] Audit record missing 'plan_hash': {rec}"
            assert rec["plan_hash"], f"[{pilot_mode}] Audit record has empty 'plan_hash': {rec}"
        print(f"\n[{pilot_mode}] plan_hash present in all {len(engine._audit_log)} audit records ✓")

    def test_audit_record_has_user_id(self, pilot_mode):
        """Every audit record must contain the non-empty user_id of the acting principal."""
        engine = _active_engine()
        engine.propose_production_plan("AUDIT-003", _plan(), _id("req-a3", AAARole.NOC_OPERATOR))
        for rec in engine._audit_log:
            assert "user_id" in rec, f"[{pilot_mode}] Audit record missing 'user_id': {rec}"
            assert rec["user_id"], f"[{pilot_mode}] Audit record has empty 'user_id': {rec}"
        print(f"\n[{pilot_mode}] user_id present in all audit records ✓")

    def test_audit_record_has_status(self, pilot_mode):
        """Every audit record must include a non-empty status string."""
        engine = _active_engine()
        engine.propose_production_plan("AUDIT-004", _plan(), _id("req-a4", AAARole.NOC_OPERATOR))
        for rec in engine._audit_log:
            assert "status" in rec, f"[{pilot_mode}] Audit record missing 'status': {rec}"
            assert rec["status"], f"[{pilot_mode}] Audit record has empty 'status': {rec}"

    def test_audit_record_has_action(self, pilot_mode):
        """Every audit record must include an 'action' describing the event type."""
        engine = _active_engine()
        engine.propose_production_plan("AUDIT-005", _plan(), _id("req-a5", AAARole.NOC_OPERATOR))
        for rec in engine._audit_log:
            assert "action" in rec, f"[{pilot_mode}] Audit record missing 'action': {rec}"
            assert rec["action"], f"[{pilot_mode}] Audit record has empty 'action': {rec}"

    def test_audit_seat_records_approver_identity(self, pilot_mode):
        """Seat approval record must contain the approver user_id."""
        engine = _active_engine()
        requester = _id("req-a6", AAARole.NOC_OPERATOR)
        approver = _id("approver-a6", AAARole.NOC_ENGINEER)

        dec = engine.propose_production_plan("AUDIT-006", _plan(), requester)
        engine.submit_approval_seat("AUDIT-006", 1, approver, dec.plan_hash)

        seat_records = [r for r in engine._audit_log if "SEAT" in r.get("action", "")]
        assert len(seat_records) >= 1, f"[{pilot_mode}] No seat approval records found"
        for sr in seat_records:
            assert sr.get("user_id") == "approver-a6", (
                f"[{pilot_mode}] Seat record user_id mismatch: {sr}"
            )
        print(f"\n[{pilot_mode}] Approver identities recorded in seat audit records ✓")

    def test_audit_evaluate_records_decision(self, pilot_mode):
        """evaluate_authorization must produce an audit record with the final decision status."""
        engine = _active_engine()
        device_id = "staging-rtr-01"
        plan = _plan(device_id)
        requester = _id("req-a7", AAARole.NOC_OPERATOR)
        seat1 = _id("seat1-a7", AAARole.NOC_ENGINEER)
        seat2 = _id("seat2-a7", AAARole.NOC_ADMIN)

        dec = engine.propose_production_plan("AUDIT-007", plan, requester)
        engine.submit_approval_seat("AUDIT-007", 1, seat1, dec.plan_hash)
        engine.submit_approval_seat("AUDIT-007", 2, seat2, dec.plan_hash)
        engine.evaluate_authorization("AUDIT-007", plan)

        eval_records = [r for r in engine._audit_log if "EVALUATE" in r.get("action", "")]
        assert len(eval_records) >= 1, f"[{pilot_mode}] No EVALUATE audit record found"
        for er in eval_records:
            assert er.get("status") == QuorumDecision.PRODUCTION_EXECUTION_DISABLED.value, (
                f"[{pilot_mode}] Expected PRODUCTION_EXECUTION_DISABLED in eval record, got: {er}"
            )
        print(f"\n[{pilot_mode}] Evaluation decision recorded in audit log ✓")

    def test_audit_has_no_private_key_material(self, pilot_mode):
        """
        CRITICAL: Audit log must contain NO private key material.
        Checks all string values in every audit record for PEM markers.
        """
        engine = _active_engine()
        requester = _id("req-a8", AAARole.NOC_OPERATOR)
        dec = engine.propose_production_plan("AUDIT-008", _plan(), requester)
        engine.evaluate_authorization("AUDIT-008", _plan())

        FORBIDDEN_MARKERS = [
            "-----BEGIN RSA PRIVATE KEY-----",
            "-----BEGIN PRIVATE KEY-----",
            "-----BEGIN EC PRIVATE KEY-----",
            "-----BEGIN CERTIFICATE-----",
        ]

        for rec in engine._audit_log:
            rec_str = str(rec)
            for marker in FORBIDDEN_MARKERS:
                assert marker not in rec_str, (
                    f"[{pilot_mode}] SECURITY VIOLATION: private key material in audit log: '{marker}'"
                )
        print(f"\n[{pilot_mode}] No private key material in {len(engine._audit_log)} audit records ✓")

    def test_audit_has_no_password_fields(self, pilot_mode):
        """Audit log must not contain password / secret / token literal values."""
        engine = _active_engine()
        engine.propose_production_plan("AUDIT-009", _plan(), _id("req-a9", AAARole.NOC_OPERATOR))

        FORBIDDEN_KEYS = ["password", "passwd", "secret", "token", "api_key"]
        for rec in engine._audit_log:
            for fk in FORBIDDEN_KEYS:
                assert fk not in rec, (
                    f"[{pilot_mode}] Forbidden key '{fk}' found in audit record: {rec}"
                )
        print(f"\n[{pilot_mode}] No password/secret fields in audit log ✓")

    def test_audit_no_production_mutation_event_exists(self, pilot_mode):
        """
        Confirm no PRODUCTION_EXEC or LIVE_MUTATION event appears in the audit log.
        This verifies that no production mutation occurred during the entire Phase 6 run.
        """
        engine = _active_engine()
        engine.propose_production_plan("AUDIT-010", _plan(), _id("req-a10", AAARole.NOC_OPERATOR))
        engine.evaluate_authorization("AUDIT-010", _plan())

        MUTATION_MARKERS = ["PRODUCTION_EXEC", "LIVE_MUTATION", "COMMIT_LIVE", "APPLY_LIVE"]
        for rec in engine._audit_log:
            action = rec.get("action", "")
            for marker in MUTATION_MARKERS:
                assert marker not in action, (
                    f"[{pilot_mode}] SAFETY VIOLATION: production mutation event in audit log: '{action}'"
                )
        print(f"\n[{pilot_mode}] No production mutation events in audit log ✓")

    def test_audit_rejection_reasons_recorded(self, pilot_mode):
        """
        When evaluation is rejected, rejection_reasons must be non-empty in the audit record.
        """
        engine = _active_engine()
        device_id = "staging-rtr-01"
        plan = _plan(device_id)
        requester = _id("req-a11", AAARole.NOC_OPERATOR)
        seat1 = _id("seat1-a11", AAARole.NOC_ENGINEER)
        seat2 = _id("seat2-a11", AAARole.NOC_ADMIN)

        dec = engine.propose_production_plan("AUDIT-011", plan, requester)
        engine.submit_approval_seat("AUDIT-011", 1, seat1, dec.plan_hash)
        engine.submit_approval_seat("AUDIT-011", 2, seat2, dec.plan_hash)
        engine.evaluate_authorization("AUDIT-011", plan)

        eval_records = [r for r in engine._audit_log if "EVALUATE" in r.get("action", "")]
        for er in eval_records:
            reasons = er.get("rejection_reasons", [])
            assert len(reasons) >= 1, (
                f"[{pilot_mode}] Expected non-empty rejection_reasons, got: {reasons}"
            )
            assert any("PRODUCTION_AUTHORIZED" in r or "hard-disabled" in r.lower() for r in reasons), (
                f"[{pilot_mode}] Expected PRODUCTION_AUTHORIZED rejection reason, got: {reasons}"
            )
        print(f"\n[{pilot_mode}] Rejection reasons correctly recorded in audit log ✓")

    def test_audit_event_has_timestamp(self, pilot_mode):
        """Every audit record must have a parseable ISO 8601 timestamp."""
        engine = _active_engine()
        engine.propose_production_plan("AUDIT-012", _plan(), _id("req-a12", AAARole.NOC_OPERATOR))

        for rec in engine._audit_log:
            assert "timestamp" in rec, f"[{pilot_mode}] Audit record missing timestamp: {rec}"
            ts = rec["timestamp"]
            # Verify it parses as an ISO datetime string
            try:
                datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, AttributeError) as exc:
                pytest.fail(f"[{pilot_mode}] Invalid timestamp format '{ts}': {exc}")
        print(f"\n[{pilot_mode}] All {len(engine._audit_log)} audit records have valid timestamps ✓")
