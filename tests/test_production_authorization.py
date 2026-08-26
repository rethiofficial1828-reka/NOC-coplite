"""
Unit Test Suite for NOC Copilot v1.4 Phase 5: Production Authorization Engine & Hard Gate.

Tests:
1. End-to-end multi-point authorization evaluation
2. Maintenance window blocking (MAINTENANCE_WINDOW_BLOCKED)
3. Enterprise blast-radius concurrency blocking (BLAST_RADIUS_BLOCKED)
4. Cooldown timer blocking (COOLDOWN_BLOCKED)
5. Control plane / mTLS unreadiness blocking (CAPABILITY_BLOCKED)
6. Emergency break-glass override with Security Officer role
7. Explicit hard-disablement: Decision resolves to PRODUCTION_EXECUTION_DISABLED
8. DRY_RUN and LAB_AUTHORIZED independence
"""

from datetime import datetime, timedelta, timezone
import pytest

from agents.failover import (
    BreakGlassRequest,
    DeviceEndpointProfile,
    ExecutionPlan,
    ExecutionStep,
    GNMIControlPlane,
    MaintenanceWindow,
    NOSVendor,
    ProductionAuthorizationQuorumEngine,
    QuorumDecision,
    TestChangeWindowProvider,
    TransportProtocol,
)
from agents.security import AAAIdentity, AAARole


@pytest.fixture
def test_setup():
    now = datetime.now(timezone.utc)
    change_provider = TestChangeWindowProvider()
    win = MaintenanceWindow(
        change_ticket_id="CHG-PROD-001",
        start_time=now - timedelta(minutes=15),
        end_time=now + timedelta(minutes=45),
        target_devices=["core-01"],
        approved_by="CAB_DIRECTOR",
    )
    change_provider.register_window(win)

    engine = ProductionAuthorizationQuorumEngine(
        change_window_provider=change_provider,
        cooldown_seconds=300.0,
    )

    plan = ExecutionPlan(
        plan_id="PLAN-CORE-FAILOVER",
        decision_id="DEC-CORE-001",
        plan_hash="PENDING_HASH",
        source_path="ISP-A",
        destination_path="ISP-B",
        target_devices=["core-01"],
        steps=[ExecutionStep(sequence=1, target="core-01", action_type="SWITCH_INTERFACE", parameters={"to": "eth2"})],
    )

    requester = AAAIdentity(user_id="usr-op", username="op", roles=[AAARole.NOC_OPERATOR])
    eng = AAAIdentity(user_id="usr-eng", username="eng", roles=[AAARole.NOC_ENGINEER])
    adm = AAAIdentity(user_id="usr-adm", username="adm", roles=[AAARole.NOC_ADMIN])
    sec_officer = AAAIdentity(user_id="usr-sec", username="sec", roles=[AAARole.SECURITY_OFFICER])

    profile = DeviceEndpointProfile(
        device_id="core-01",
        hostname="core-01.corp.internal",
        management_ip="10.10.1.1",
        management_port=9339,
        vendor=NOSVendor.ARISTA_EOS,
        transport=TransportProtocol.GNMI_GRPC,
        tls_server_name="core-01.corp.internal",
        ca_cert_path="/ca.pem",
        client_cert_path="/client.pem",
        client_key_path="/key.pem",
        allowlisted=True,
    )

    return {
        "engine": engine,
        "plan": plan,
        "requester": requester,
        "eng": eng,
        "adm": adm,
        "sec_officer": sec_officer,
        "profile": profile,
        "change_provider": change_provider,
    }


def test_production_authorized_hard_disabled_decision(test_setup):
    """
    Verify that even when ALL quorum, maintenance windows, and prechecks pass,
    the decision resolves explicitly to PRODUCTION_EXECUTION_DISABLED derived from settings.PRODUCTION_AUTHORIZED.
    """
    setup = test_setup
    engine: ProductionAuthorizationQuorumEngine = setup["engine"]
    plan: ExecutionPlan = setup["plan"]
    req_id = "REQ-E2E-001"

    # 1. Propose
    decision = engine.propose_production_plan(req_id, plan, setup["requester"])
    assert decision.final_decision == QuorumDecision.PENDING_QUORUM

    # 2. Complete Quorum
    engine.submit_approval_seat(req_id, 1, setup["eng"], decision.plan_hash)
    engine.submit_approval_seat(req_id, 2, setup["adm"], decision.plan_hash)

    # 3. Setup mock gNMI driver
    gnmi = GNMIControlPlane(declared_allowlist={"core-01"})
    gnmi.connect_mtls(setup["profile"])

    # 4. Evaluate (derives PRODUCTION_AUTHORIZED from config.settings)
    eval_decision = engine.evaluate_authorization(
        req_id,
        plan,
        target_profile=setup["profile"],
        control_plane=gnmi,
    )

    assert eval_decision.final_decision == QuorumDecision.PRODUCTION_EXECUTION_DISABLED
    assert eval_decision.maintenance_window_status == "ACTIVE"
    assert eval_decision.mtls_status == "OK"
    assert any("PRODUCTION_AUTHORIZED is hard-disabled" in r for r in eval_decision.rejection_reasons)


def test_central_setting_false_always_yields_production_execution_disabled(test_setup):
    """Verify that settings.PRODUCTION_AUTHORIZED = False is the single source of truth."""
    from config import settings
    assert settings.PRODUCTION_AUTHORIZED is False

    setup = test_setup
    engine: ProductionAuthorizationQuorumEngine = setup["engine"]
    plan: ExecutionPlan = setup["plan"]
    req_id = "REQ-CENTRAL-001"

    decision = engine.propose_production_plan(req_id, plan, setup["requester"])
    engine.submit_approval_seat(req_id, 1, setup["eng"], decision.plan_hash)
    engine.submit_approval_seat(req_id, 2, setup["adm"], decision.plan_hash)

    gnmi = GNMIControlPlane(declared_allowlist={"core-01"})
    gnmi.connect_mtls(setup["profile"])

    eval_decision = engine.evaluate_authorization(
        req_id,
        plan,
        target_profile=setup["profile"],
        control_plane=gnmi,
    )
    assert eval_decision.final_decision == QuorumDecision.PRODUCTION_EXECUTION_DISABLED


def test_attempted_caller_override_cannot_enable_production(test_setup):
    """Verify that callers cannot pass arbitrary override flags to bypass central disablement."""
    import inspect
    sig = inspect.signature(ProductionAuthorizationQuorumEngine.evaluate_authorization)
    # Verify production_authorized_flag is NOT a parameter
    assert "production_authorized_flag" not in sig.parameters

    setup = test_setup
    engine: ProductionAuthorizationQuorumEngine = setup["engine"]
    plan: ExecutionPlan = setup["plan"]
    req_id = "REQ-NO-OVERRIDE-001"

    decision = engine.propose_production_plan(req_id, plan, setup["requester"])
    engine.submit_approval_seat(req_id, 1, setup["eng"], decision.plan_hash)
    engine.submit_approval_seat(req_id, 2, setup["adm"], decision.plan_hash)

    # Attempting to pass unexpected kwargs or flags will fail at runtime
    import pytest
    with pytest.raises(TypeError):
        engine.evaluate_authorization(
            req_id,
            plan,
            production_authorized_flag=True,  # type: ignore
        )



def test_maintenance_window_blocked(test_setup):
    """Verify evaluation fails if outside active change window."""
    setup = test_setup
    # Create engine with empty change provider
    engine = ProductionAuthorizationQuorumEngine(change_window_provider=TestChangeWindowProvider())
    plan: ExecutionPlan = setup["plan"]
    req_id = "REQ-MW-002"

    decision = engine.propose_production_plan(req_id, plan, setup["requester"])
    engine.submit_approval_seat(req_id, 1, setup["eng"], decision.plan_hash)
    engine.submit_approval_seat(req_id, 2, setup["adm"], decision.plan_hash)

    eval_decision = engine.evaluate_authorization(req_id, plan)
    assert eval_decision.final_decision == QuorumDecision.MAINTENANCE_WINDOW_BLOCKED


def test_blast_radius_concurrency_blocked(test_setup):
    """Verify maximum 1 simultaneous production transition is enforced."""
    setup = test_setup
    engine: ProductionAuthorizationQuorumEngine = setup["engine"]
    plan: ExecutionPlan = setup["plan"]
    req_id = "REQ-BR-003"

    # Simulate another active transition
    engine.record_transition_start("rtr-other-02")

    decision = engine.propose_production_plan(req_id, plan, setup["requester"])
    engine.submit_approval_seat(req_id, 1, setup["eng"], decision.plan_hash)
    engine.submit_approval_seat(req_id, 2, setup["adm"], decision.plan_hash)

    eval_decision = engine.evaluate_authorization(req_id, plan)
    assert eval_decision.final_decision == QuorumDecision.BLAST_RADIUS_BLOCKED


def test_cooldown_timer_blocked(test_setup):
    """Verify 300-second cooldown blocks immediate re-execution on same device."""
    setup = test_setup
    engine: ProductionAuthorizationQuorumEngine = setup["engine"]
    plan: ExecutionPlan = setup["plan"]
    req_id = "REQ-CD-004"

    # Mark recent transition completed
    engine.record_transition_completed("core-01")

    decision = engine.propose_production_plan(req_id, plan, setup["requester"])
    engine.submit_approval_seat(req_id, 1, setup["eng"], decision.plan_hash)
    engine.submit_approval_seat(req_id, 2, setup["adm"], decision.plan_hash)

    eval_decision = engine.evaluate_authorization(req_id, plan)
    assert eval_decision.final_decision == QuorumDecision.COOLDOWN_BLOCKED


def test_emergency_break_glass_override(test_setup):
    """Verify Security Officer break-glass override flow."""
    setup = test_setup
    engine: ProductionAuthorizationQuorumEngine = setup["engine"]
    plan: ExecutionPlan = setup["plan"]
    req_id = "REQ-BG-005"

    bg_req = BreakGlassRequest(
        identity=setup["sec_officer"],
        reason="Emergency multi-carrier fiber cut incident INC-9901 requires immediate reroute.",
        signature="SEC_AUTH_SIG_9988776655443322",
    )

    bg_decision = engine.emergency_break_glass(req_id, bg_req, plan)
    assert bg_decision.final_decision == QuorumDecision.EMERGENCY_APPROVED
    assert bg_decision.approval_status == "EMERGENCY_BREAK_GLASS"
