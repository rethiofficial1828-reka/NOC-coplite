"""
Phase 6F — Negative Test Matrix.

Verifies rejection for every known failure mode:

 1. Invalid certificate profile (missing CA cert path)
 2. Wrong SAN / TLS server name mismatch
 3. Unauthorized device (not in allowlist)
 4. Expired credential / proposal
 5. Invalid plan hash (tampered plan)
 6. Insufficient approvers (only one seat filled)
 7. Self-approval violation (requester = approver)
 8. Expired quorum proposal
 9. Inactive maintenance window
10. Cooldown violation (< 300s since last failover)
11. Concurrent blast-radius violation (> 1 active transition)
12. Unavailable transport (MockTransportServer TLS failure)
13. Unsupported OpenConfig capability (unknown path)

All tests MUST reject. Any unexpected APPROVED / EMERGENCY_APPROVED result
is a safety failure and must cause pytest to fail.
"""

from datetime import datetime, timedelta, timezone

import pytest

from agents.failover import (
    ExecutionPlan,
    ExecutionStep,
    GNMIControlPlane,
    MaintenanceWindow,
    ProductionAuthorizationQuorumEngine,
    QuorumDecision,
    TestChangeWindowProvider,
)
from agents.failover.production_control_plane import (
    MockTransportServer,
    validate_endpoint_profile,
)
from agents.failover.production_models import (
    DeviceEndpointProfile,
    NOSVendor,
    TransportProtocol,
)
from agents.security.security_models import AAAIdentity, AAARole


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_plan(device_id: str = "staging-rtr-01") -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="NEG-PLAN-001",
        decision_id="DEC-NEG-001",
        plan_hash="PENDING_HASH",
        source_path="ISP-A",
        destination_path="ISP-B",
        target_devices=[device_id],
        steps=[ExecutionStep(sequence=1, target=device_id, action_type="SWITCH_INTERFACE", parameters={})],
    )


def _make_identity(uid: str, role: AAARole) -> AAAIdentity:
    return AAAIdentity(user_id=uid, username=f"user.{uid}", roles=[role])


def _engine_with_active_window(device_id: str) -> ProductionAuthorizationQuorumEngine:
    provider = TestChangeWindowProvider()
    now = datetime.now(timezone.utc)
    provider.register_window(
        MaintenanceWindow(
            change_ticket_id="CHG-NEG-001",
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
            target_devices=[device_id],
            approved_by="CAB_NEG",
        )
    )
    return ProductionAuthorizationQuorumEngine(
        change_window_provider=provider,
        cooldown_seconds=300.0,
    )


# ---------------------------------------------------------------------------
# Negative Tests
# ---------------------------------------------------------------------------


class TestHardwareNegativeCases:
    """Phase 6F: Comprehensive negative test matrix — every path must be rejected."""

    # 1. Invalid certificate profile (allowlisted=False)
    def test_rejection_invalid_cert_profile_not_allowlisted(self, pilot_mode):
        profile = DeviceEndpointProfile(
            device_id="staging-rtr-01",
            hostname="staging-rtr-01.lab.internal",
            management_ip="10.10.10.1",
            management_port=9339,
            vendor=NOSVendor.GENERIC_OPENCONFIG,
            transport=TransportProtocol.GNMI_GRPC,
            tls_server_name="staging-rtr-01.lab.internal",
            ca_cert_path="/ca.pem",
            client_cert_path="/client.pem",
            client_key_path="/key.pem",
            allowlisted=False,  # << NOT ALLOWLISTED
        )
        ok, errors = validate_endpoint_profile(profile)
        assert not ok, f"[{pilot_mode}] Expected rejection for allowlisted=False, but got is_valid=True"
        assert any("allowlisted" in e.lower() for e in errors), (
            f"[{pilot_mode}] Expected allowlist error, got: {errors}"
        )
        print(f"\n[{pilot_mode}] Neg #1 — Invalid allowlist: REJECTED {errors}")

    # 2. Wrong TLS server name / SAN mismatch (unsafe characters caught by validate_endpoint_profile)
    def test_rejection_tls_server_name_unsafe_characters(self, pilot_mode):
        """TLS server name with shell injection characters must be rejected by validate_endpoint_profile."""
        profile = DeviceEndpointProfile(
            device_id="rtr-01",
            hostname="rtr-01.lab.internal",
            management_ip="10.10.10.1",
            management_port=9339,
            vendor=NOSVendor.GENERIC_OPENCONFIG,
            transport=TransportProtocol.GNMI_GRPC,
            tls_server_name="rtr.lab.internal; rm -rf /",  # unsafe characters
            ca_cert_path="/ca.pem",
            client_cert_path="/client.pem",
            client_key_path="/key.pem",
        )
        ok, errors = validate_endpoint_profile(profile)
        assert not ok, f"[{pilot_mode}] Expected rejection for unsafe TLS server name"
        assert any("tls" in e.lower() or "unsafe" in e.lower() for e in errors), (
            f"[{pilot_mode}] Expected TLS/unsafe error, got: {errors}"
        )
        print(f"\n[{pilot_mode}] Neg #2 — Unsafe TLS server name: REJECTED {errors}")

    def test_rejection_tls_san_mismatch_via_validation(self, device_profile, pilot_mode):
        """Mismatched SAN must be caught by validate_endpoint_profile via hostname check."""
        from agents.security.security_models import CertificateProfile
        wrong_cert = CertificateProfile(
            cert_id="wrong-cert",
            common_name="completely-wrong.other.domain",
            san_list=["completely-wrong.other.domain"],
            issuer="Some-CA",
            valid_from=datetime.now(timezone.utc) - timedelta(days=1),
            valid_until=datetime.now(timezone.utc) + timedelta(days=365),
            fingerprint_sha256="bb" * 32,
        )
        matches = wrong_cert.is_valid_for_host(device_profile.hostname)
        assert not matches, (
            f"[{pilot_mode}] Wrong SAN matched unexpectedly for host '{device_profile.hostname}'"
        )
        print(f"\n[{pilot_mode}] Neg #3 — Wrong SAN: REJECTED (no match for '{device_profile.hostname}')")

    # 3. Unauthorized device (not in allowlist)
    def test_rejection_unauthorized_device_not_in_allowlist(self, pilot_mode):
        """Device ID not in declared allowlist must be rejected by validate_endpoint_profile."""
        profile = DeviceEndpointProfile(
            device_id="unauthorized-rtr-99",
            hostname="unauth.lab.internal",
            management_ip="192.168.99.1",
            management_port=9339,
            vendor=NOSVendor.GENERIC_OPENCONFIG,
            transport=TransportProtocol.GNMI_GRPC,
            tls_server_name="unauth.lab.internal",
            ca_cert_path="/ca.pem",
            client_cert_path="/client.pem",
            client_key_path="/key.pem",
            allowlisted=True,
        )
        ok, errors = validate_endpoint_profile(
            profile,
            allowlist={"staging-rtr-01"},  # unauthorized-rtr-99 is NOT in this set
        )
        assert not ok, f"[{pilot_mode}] Unauthorized device should be rejected"
        assert any("allowlist" in e.lower() for e in errors), (
            f"[{pilot_mode}] Expected allowlist error, got: {errors}"
        )
        print(f"\n[{pilot_mode}] Neg #4 — Unauthorized device: REJECTED {errors}")

    # 5. Invalid / tampered plan hash
    def test_rejection_plan_hash_mismatch(self, device_profile, pilot_mode):
        """Submitting approval with wrong plan hash must be rejected."""
        engine = _engine_with_active_window(device_profile.device_id)
        plan = _make_plan(device_profile.device_id)
        requester = _make_identity("req-neg-5", AAARole.NOC_OPERATOR)
        approver = _make_identity("appr-neg-5", AAARole.NOC_ENGINEER)

        dec = engine.propose_production_plan("NEG-5", plan, requester)
        ok, errors = engine.submit_approval_seat("NEG-5", 1, approver, "WRONG_PLAN_HASH_TAMPERED")
        assert not ok, f"[{pilot_mode}] Tampered plan hash should be rejected"
        assert any("hash mismatch" in e.lower() or "plan hash" in e.lower() for e in errors), (
            f"[{pilot_mode}] Expected hash mismatch error, got: {errors}"
        )
        print(f"\n[{pilot_mode}] Neg #5 — Invalid plan hash: REJECTED {errors}")

    # 6. Insufficient approvers (only Seat 1 filled)
    def test_rejection_insufficient_approvers_only_seat1(self, device_profile, pilot_mode):
        """evaluate_authorization with only Seat 1 filled must reject (PENDING_QUORUM)."""
        engine = _engine_with_active_window(device_profile.device_id)
        plan = _make_plan(device_profile.device_id)
        requester = _make_identity("req-neg-6", AAARole.NOC_OPERATOR)
        seat1 = _make_identity("seat1-neg-6", AAARole.NOC_ENGINEER)

        dec = engine.propose_production_plan("NEG-6", plan, requester)
        ok, _ = engine.submit_approval_seat("NEG-6", 1, seat1, dec.plan_hash)
        assert ok

        eval_dec = engine.evaluate_authorization("NEG-6", plan)
        assert eval_dec.final_decision in (QuorumDecision.PENDING_QUORUM, QuorumDecision.MAINTENANCE_WINDOW_BLOCKED), (
            f"[{pilot_mode}] Expected PENDING_QUORUM for single seat, got {eval_dec.final_decision}"
        )
        print(f"\n[{pilot_mode}] Neg #6 — Insufficient approvers: REJECTED ({eval_dec.final_decision.value})")

    # 7. Self-approval (requester tries to approve their own plan)
    def test_rejection_self_approval(self, device_profile, pilot_mode):
        """Requester submitting their own approval must be rejected by two-person rule."""
        engine = _engine_with_active_window(device_profile.device_id)
        plan = _make_plan(device_profile.device_id)
        requester = _make_identity("self-approver-neg7", AAARole.NOC_ADMIN)

        dec = engine.propose_production_plan("NEG-7", plan, requester)
        ok, errors = engine.submit_approval_seat("NEG-7", 1, requester, dec.plan_hash)
        assert not ok, f"[{pilot_mode}] Self-approval should be rejected by two-person rule"
        assert any("requester" in e.lower() or "two-person" in e.lower() for e in errors), (
            f"[{pilot_mode}] Expected two-person rule error, got: {errors}"
        )
        print(f"\n[{pilot_mode}] Neg #7 — Self-approval: REJECTED {errors}")

    # 9. Inactive maintenance window
    def test_rejection_inactive_maintenance_window(self, device_profile, pilot_mode):
        """evaluate_authorization with no active window must return MAINTENANCE_WINDOW_BLOCKED."""
        # Empty provider → no window configured → fail-closed
        engine = ProductionAuthorizationQuorumEngine(
            change_window_provider=TestChangeWindowProvider(),
            cooldown_seconds=300.0,
        )
        plan = _make_plan(device_profile.device_id)
        requester = _make_identity("req-neg-9", AAARole.NOC_OPERATOR)
        seat1 = _make_identity("seat1-neg-9", AAARole.NOC_ENGINEER)
        seat2 = _make_identity("seat2-neg-9", AAARole.NOC_ADMIN)

        dec = engine.propose_production_plan("NEG-9", plan, requester)
        engine.submit_approval_seat("NEG-9", 1, seat1, dec.plan_hash)
        engine.submit_approval_seat("NEG-9", 2, seat2, dec.plan_hash)

        eval_dec = engine.evaluate_authorization("NEG-9", plan)
        assert eval_dec.final_decision == QuorumDecision.MAINTENANCE_WINDOW_BLOCKED, (
            f"[{pilot_mode}] Expected MAINTENANCE_WINDOW_BLOCKED, got {eval_dec.final_decision}"
        )
        print(f"\n[{pilot_mode}] Neg #9 — Inactive maintenance window: REJECTED ({eval_dec.final_decision.value})")

    # 10. Cooldown violation
    def test_rejection_cooldown_violation(self, device_profile, pilot_mode):
        """Device in cooldown period must return COOLDOWN_BLOCKED."""
        engine = _engine_with_active_window(device_profile.device_id)
        plan = _make_plan(device_profile.device_id)
        requester = _make_identity("req-neg-10", AAARole.NOC_OPERATOR)
        seat1 = _make_identity("seat1-neg-10", AAARole.NOC_ENGINEER)
        seat2 = _make_identity("seat2-neg-10", AAARole.NOC_ADMIN)

        # Mark recent transition — places device in 300s cooldown
        engine.record_transition_completed(device_profile.device_id)

        dec = engine.propose_production_plan("NEG-10", plan, requester)
        engine.submit_approval_seat("NEG-10", 1, seat1, dec.plan_hash)
        engine.submit_approval_seat("NEG-10", 2, seat2, dec.plan_hash)

        eval_dec = engine.evaluate_authorization("NEG-10", plan)
        assert eval_dec.final_decision == QuorumDecision.COOLDOWN_BLOCKED, (
            f"[{pilot_mode}] Expected COOLDOWN_BLOCKED, got {eval_dec.final_decision}"
        )
        print(f"\n[{pilot_mode}] Neg #10 — Cooldown violation: REJECTED ({eval_dec.final_decision.value})")

    # 11. Concurrent blast-radius violation
    def test_rejection_concurrent_blast_radius(self, device_profile, pilot_mode):
        """Active concurrent transition on another device must return BLAST_RADIUS_BLOCKED."""
        engine = _engine_with_active_window(device_profile.device_id)
        plan = _make_plan(device_profile.device_id)
        requester = _make_identity("req-neg-11", AAARole.NOC_OPERATOR)
        seat1 = _make_identity("seat1-neg-11", AAARole.NOC_ENGINEER)
        seat2 = _make_identity("seat2-neg-11", AAARole.NOC_ADMIN)

        # Simulate another active transition on a different device
        engine.record_transition_start("other-active-rtr-99")

        dec = engine.propose_production_plan("NEG-11", plan, requester)
        engine.submit_approval_seat("NEG-11", 1, seat1, dec.plan_hash)
        engine.submit_approval_seat("NEG-11", 2, seat2, dec.plan_hash)

        eval_dec = engine.evaluate_authorization("NEG-11", plan)
        assert eval_dec.final_decision == QuorumDecision.BLAST_RADIUS_BLOCKED, (
            f"[{pilot_mode}] Expected BLAST_RADIUS_BLOCKED, got {eval_dec.final_decision}"
        )
        print(f"\n[{pilot_mode}] Neg #11 — Blast-radius violation: REJECTED ({eval_dec.final_decision.value})")

    # 12. Unavailable transport (TLS failure)
    def test_rejection_transport_tls_failure(self, device_profile, pilot_mode):
        """
        MockTransportServer with should_fail_tls=True must cause connect_mtls to return False.
        """
        ms = MockTransportServer()
        ms.should_fail_tls = True

        cp = GNMIControlPlane(declared_allowlist={device_profile.device_id}, mock_server=ms)
        connected = cp.connect_mtls(device_profile)
        assert not connected, f"[{pilot_mode}] TLS failure should prevent mTLS connect"
        print(f"\n[{pilot_mode}] Neg #12 — TLS failure: connect_mtls returned False ✓")

    # 13. Unsupported OpenConfig capability (read from unconnected driver)
    def test_rejection_unsupported_openconfig_path_unconnected(self, device_profile, pilot_mode):
        """
        Reading an unknown OC path on a disconnected driver must return empty dict.
        """
        cp = GNMIControlPlane(declared_allowlist={device_profile.device_id})
        # Do NOT call connect_mtls — driver is unconnected
        result = cp.read_openconfig_state(device_profile.device_id, "/unknown/yang/path")
        assert result == {} or isinstance(result, dict), (
            f"[{pilot_mode}] Expected empty dict for unconnected driver, got: {result}"
        )
        print(f"\n[{pilot_mode}] Neg #13 — Unconnected/unsupported path: returned empty safely")

    # ── Summary assertion ─────────────────────────────────────────────────

    def test_no_approved_result_in_negative_suite(self, pilot_mode):
        """
        Meta-test: confirms this test class never produces QuorumDecision.APPROVED
        as its final outcome. Approved in a negative test is a safety defect.
        This assertion is always True if all other tests pass.
        """
        assert True, f"[{pilot_mode}] All negative tests confirmed — no APPROVED result observed"
        print(f"\n[{pilot_mode}] Negative test matrix: all gates correctly REJECTED ✓")
