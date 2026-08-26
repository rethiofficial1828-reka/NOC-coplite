"""
Phase 6E — Production Authorization Quorum Gate Rehearsal.

Executes the FULL authorization evaluation pipeline using a test plan:

    ApprovalManager-equivalent (two-person quorum)
    → 16 prechecks (structural validation)
    → quorum gate (propose → seat 1 → seat 2 → evaluate)
    → mTLS readiness
    → control-plane readiness
    → maintenance-window provider
    → blast-radius limit
    → cooldown

EXPECTED FINAL RESULT: QuorumDecision.PRODUCTION_EXECUTION_DISABLED

This phase is a rehearsal ONLY.
PRODUCTION_AUTHORIZED MUST remain False throughout.
No real production device mutation occurs.
"""

from datetime import datetime, timedelta, timezone

import pytest

from agents.failover import (
    BreakGlassRequest,
    ExecutionPlan,
    ExecutionStep,
    GNMIControlPlane,
    MaintenanceWindow,
    ProductionAuthorizationQuorumEngine,
    QuorumDecision,
    TestChangeWindowProvider,
)
from agents.failover.production_models import (
    DeviceEndpointProfile,
    NOSVendor,
    TransportProtocol,
)
from agents.security.security_models import AAAIdentity, AAARole


# ---------------------------------------------------------------------------
# Quorum Rehearsal Test
# ---------------------------------------------------------------------------


class TestQuorumGateRehearsal:
    """Phase 6E: Full multi-point authorization evaluation rehearsal."""

    # ── Operator Identities ──────────────────────────────────────────────

    @pytest.fixture
    def requester(self) -> AAAIdentity:
        return AAAIdentity(user_id="pilot-requester", username="noc.pilot.op", roles=[AAARole.NOC_OPERATOR])

    @pytest.fixture
    def seat1_approver(self) -> AAAIdentity:
        return AAAIdentity(user_id="pilot-eng", username="noc.pilot.eng", roles=[AAARole.NOC_ENGINEER])

    @pytest.fixture
    def seat2_approver(self) -> AAAIdentity:
        return AAAIdentity(user_id="pilot-adm", username="noc.pilot.admin", roles=[AAARole.NOC_ADMIN])

    @pytest.fixture
    def sec_officer(self) -> AAAIdentity:
        return AAAIdentity(user_id="pilot-sec", username="noc.sec.officer", roles=[AAARole.SECURITY_OFFICER])

    # ── Execution Plan ───────────────────────────────────────────────────

    @pytest.fixture
    def rehearsal_plan(self, device_profile) -> ExecutionPlan:
        return ExecutionPlan(
            plan_id="REHEARSAL-PLAN-PHASE6E",
            decision_id="DEC-PILOT-001",
            plan_hash="PENDING_HASH",
            source_path="ISP-PRIMARY",
            destination_path="ISP-SECONDARY",
            target_devices=[device_profile.device_id],
            steps=[
                ExecutionStep(
                    sequence=1,
                    target=device_profile.device_id,
                    action_type="SWITCH_INTERFACE",
                    parameters={"from": "ISP-A", "to": "ISP-B"},
                )
            ],
        )

    # ── Rehearsal Engine ─────────────────────────────────────────────────

    @pytest.fixture
    def rehearsal_engine(self, pilot_maintenance_window, device_profile) -> ProductionAuthorizationQuorumEngine:
        provider = TestChangeWindowProvider()
        # Register window covering the pilot device
        mw = MaintenanceWindow(
            change_ticket_id="CHG-PILOT-PHASE6E",
            start_time=datetime.now(timezone.utc) - timedelta(hours=2),
            end_time=datetime.now(timezone.utc) + timedelta(hours=6),
            target_devices=[device_profile.device_id],
            approved_by="CAB_PILOT",
        )
        provider.register_window(mw)
        return ProductionAuthorizationQuorumEngine(
            change_window_provider=provider,
            cooldown_seconds=300.0,
        )

    # ── Test Cases ───────────────────────────────────────────────────────

    def test_rehearsal_initial_proposal_is_pending_quorum(
        self, rehearsal_engine, rehearsal_plan, requester, pilot_mode
    ):
        """After propose_production_plan, decision must be PENDING_QUORUM."""
        dec = rehearsal_engine.propose_production_plan(
            "REHEARSAL-001", rehearsal_plan, requester
        )
        assert dec.final_decision == QuorumDecision.PENDING_QUORUM, (
            f"[{pilot_mode}] Expected PENDING_QUORUM, got {dec.final_decision}"
        )
        print(f"\n[{pilot_mode}] Proposal submitted — state: {dec.final_decision.value}")

    def test_rehearsal_seat1_approval_recorded(
        self, rehearsal_engine, rehearsal_plan, requester, seat1_approver, pilot_mode
    ):
        """Seat 1 (NOC_ENGINEER) approval must be accepted by the engine."""
        dec = rehearsal_engine.propose_production_plan(
            "REHEARSAL-002", rehearsal_plan, requester
        )
        ok, errors = rehearsal_engine.submit_approval_seat(
            "REHEARSAL-002", 1, seat1_approver, dec.plan_hash
        )
        assert ok, f"[{pilot_mode}] Seat 1 approval rejected: {errors}"
        print(f"\n[{pilot_mode}] Seat 1 (NOC_ENGINEER) recorded OK")

    def test_rehearsal_full_quorum_then_production_execution_disabled(
        self,
        rehearsal_engine,
        rehearsal_plan,
        requester,
        seat1_approver,
        seat2_approver,
        device_profile,
        pilot_mode,
    ):
        """
        Full quorum (seats 1+2) + mTLS ready + control-plane ready +
        maintenance window ACTIVE → final decision MUST be PRODUCTION_EXECUTION_DISABLED.

        This is the critical safety rehearsal assertion.
        """
        req_id = "REHEARSAL-003"

        # 1. Propose
        dec = rehearsal_engine.propose_production_plan(req_id, rehearsal_plan, requester)

        # 2. Seat 1
        ok1, e1 = rehearsal_engine.submit_approval_seat(req_id, 1, seat1_approver, dec.plan_hash)
        assert ok1, f"[{pilot_mode}] Seat 1 failed: {e1}"

        # 3. Seat 2
        ok2, e2 = rehearsal_engine.submit_approval_seat(req_id, 2, seat2_approver, dec.plan_hash)
        assert ok2, f"[{pilot_mode}] Seat 2 failed: {e2}"

        # 4. Build control plane (MOCKED / HARDWARE)
        gnmi = GNMIControlPlane(declared_allowlist={device_profile.device_id})
        gnmi.connect_mtls(device_profile)

        # 5. Evaluate (PRODUCTION_AUTHORIZED derived from config.settings)
        eval_dec = rehearsal_engine.evaluate_authorization(
            req_id,
            rehearsal_plan,
            target_profile=device_profile,
            control_plane=gnmi,
        )

        # 6. CRITICAL ASSERTION: must be PRODUCTION_EXECUTION_DISABLED
        assert eval_dec.final_decision == QuorumDecision.PRODUCTION_EXECUTION_DISABLED, (
            f"[{pilot_mode}] SAFETY VIOLATION: expected PRODUCTION_EXECUTION_DISABLED, "
            f"got {eval_dec.final_decision}. Rejection reasons: {eval_dec.rejection_reasons}"
        )

        # 7. Confirm maintenance window was ACTIVE
        assert eval_dec.maintenance_window_status == "ACTIVE", (
            f"[{pilot_mode}] Maintenance window should be ACTIVE during rehearsal"
        )

        # 8. Confirm mTLS status was OK
        assert eval_dec.mtls_status == "OK", (
            f"[{pilot_mode}] mTLS status should be OK after valid profile connect"
        )

        # 9. Confirm rejection reason references hard-disabled flag
        assert any("hard-disabled" in r.lower() or "PRODUCTION_AUTHORIZED" in r for r in eval_dec.rejection_reasons), (
            f"[{pilot_mode}] Expected PRODUCTION_AUTHORIZED rejection reason in: {eval_dec.rejection_reasons}"
        )

        print(
            f"\n[{pilot_mode}] Quorum rehearsal PASS — final decision: "
            f"{eval_dec.final_decision.value} ✓"
        )
        print(f"[{pilot_mode}] Maintenance window: {eval_dec.maintenance_window_status}")
        print(f"[{pilot_mode}] mTLS status: {eval_dec.mtls_status}")
        print(f"[{pilot_mode}] Control plane status: {eval_dec.capability_status}")
        print(f"[{pilot_mode}] Rejection reasons: {eval_dec.rejection_reasons}")

    def test_rehearsal_break_glass_is_emergency_approved(
        self,
        rehearsal_engine,
        rehearsal_plan,
        sec_officer,
        pilot_mode,
    ):
        """
        Emergency break-glass by SECURITY_OFFICER must produce EMERGENCY_APPROVED.
        This does NOT enable production execution — it is a rehearsal record.
        """
        bg = BreakGlassRequest(
            identity=sec_officer,
            reason="Phase 6E rehearsal break-glass verification — isolated lab only.",
            signature="REHEARSAL_SIG_PHASE6E_99887766554433221100",
        )
        dec = rehearsal_engine.emergency_break_glass("REHEARSAL-BG-001", bg, rehearsal_plan)
        assert dec.final_decision == QuorumDecision.EMERGENCY_APPROVED, (
            f"[{pilot_mode}] Break-glass rehearsal failed: {dec.rejection_reasons}"
        )
        assert dec.approval_status == "EMERGENCY_BREAK_GLASS"
        print(f"\n[{pilot_mode}] Break-glass rehearsal: {dec.final_decision.value} ✓")
        print(f"[{pilot_mode}] Break-glass status: {dec.approval_status}")
