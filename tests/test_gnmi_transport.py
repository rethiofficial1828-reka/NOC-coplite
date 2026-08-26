"""
Unit Test Suite for NOC Copilot v1.4 Phase 3: Typed gNMI Transport & Read-Only OpenConfig.

Tests:
1. Successful gNMI connection via mTLS endpoint profile
2. Read-only OpenConfig Get for interface state, default route, BFD
3. Typed helper methods: get_interface_state, get_static_default_route, get_bfd_peer_state
4. Non-mutating route verification
5. Readiness and capability reporting (read ENABLED, mutation DISABLED)
6. gNMI Set dry-run simulation vs live mutation hard-blocking
7. Session state tracking and error resilience
"""

import pytest

from agents.failover import (
    ControlPlaneDriverType,
    ControlPlaneStatus,
    DeviceEndpointProfile,
    GNMIControlPlane,
    MockTransportServer,
    NOSVendor,
    OC_INTERFACE_STATE,
    OC_STATIC_DEFAULT_ROUTE,
    ProductionExecutionDisabledError,
    RouteVerificationRequest,
    TransportProtocol,
    TransportStatus,
)


@pytest.fixture
def gnmi_device_profile() -> DeviceEndpointProfile:
    return DeviceEndpointProfile(
        device_id="core-01",
        hostname="core-01.corp.internal",
        management_ip="10.10.10.1",
        management_port=9339,
        vendor=NOSVendor.ARISTA_EOS,
        transport=TransportProtocol.GNMI_GRPC,
        tls_server_name="core-01.corp.internal",
        ca_cert_path="/etc/ssl/certs/ca.pem",
        client_cert_path="/etc/ssl/certs/client.pem",
        client_key_path="/etc/ssl/private/client.key",
        allowlisted=True,
    )


# ---------------------------------------------------------------------------
# 1. Connection & Readiness Lifecycle
# ---------------------------------------------------------------------------


def test_gnmi_not_configured_readiness():
    """Verify GNMIControlPlane reports NOT_CONFIGURED when not connected."""
    driver = GNMIControlPlane()
    assert driver.is_configured is False
    assert driver.driver_type == ControlPlaneDriverType.GNMI

    readiness = driver.check_readiness()
    assert readiness.success is False
    assert readiness.status == ControlPlaneStatus.NOT_CONFIGURED
    assert readiness.details["read_capability"] == "DISABLED"
    assert readiness.details["mutation_capability"] == "DISABLED"


def test_gnmi_connection_success(gnmi_device_profile: DeviceEndpointProfile):
    """Verify successful gNMI session establishment."""
    driver = GNMIControlPlane(declared_allowlist={"core-01"})
    assert driver.connect_mtls(gnmi_device_profile) is True
    assert driver.is_configured is True

    readiness = driver.check_readiness()
    assert readiness.success is True
    assert readiness.status == ControlPlaneStatus.READY
    assert readiness.details["read_capability"] == "ENABLED"
    assert readiness.details["mutation_capability"] == "DISABLED"
    assert readiness.details["tls_state"] == "ACTIVE"


# ---------------------------------------------------------------------------
# 2. Read-Only OpenConfig Queries
# ---------------------------------------------------------------------------


def test_gnmi_read_interface_state(gnmi_device_profile: DeviceEndpointProfile):
    """Verify reading OpenConfig interface state."""
    driver = GNMIControlPlane(declared_allowlist={"core-01"})
    driver.connect_mtls(gnmi_device_profile)

    if_state = driver.get_interface_state("core-01", "eth1")
    assert if_state is not None
    assert if_state.admin_status == "UP"
    assert if_state.oper_status == "UP"
    assert if_state.in_octets == 10485760


def test_gnmi_read_static_default_route(gnmi_device_profile: DeviceEndpointProfile):
    """Verify reading OpenConfig static default route."""
    driver = GNMIControlPlane(declared_allowlist={"core-01"})
    driver.connect_mtls(gnmi_device_profile)

    route = driver.get_static_default_route("core-01")
    assert route is not None
    assert route.prefix == "0.0.0.0/0"
    assert route.next_hop == "10.10.1.1"
    assert route.metric == 10


def test_gnmi_read_bfd_state(gnmi_device_profile: DeviceEndpointProfile):
    """Verify reading OpenConfig BFD peer operational state."""
    driver = GNMIControlPlane(declared_allowlist={"core-01"})
    driver.connect_mtls(gnmi_device_profile)

    bfd = driver.get_bfd_peer_state("core-01", "eth1", "10.10.1.1")
    assert bfd is not None
    assert bfd.local_state.value == "UP"
    assert bfd.remote_state.value == "UP"
    assert bfd.detection_time_ms == 50.0


def test_gnmi_non_mutating_route_verification(gnmi_device_profile: DeviceEndpointProfile):
    """Verify non-mutating route verification succeeds."""
    driver = GNMIControlPlane(declared_allowlist={"core-01"})
    driver.connect_mtls(gnmi_device_profile)

    req = RouteVerificationRequest(
        target_device="core-01",
        expected_provider="ISP-A",
    )
    resp = driver.verify_route_path(req)
    assert resp.success is True
    assert resp.status == ControlPlaneStatus.READY
    assert resp.details["verified"] is True


# ---------------------------------------------------------------------------
# 3. Mutation Hard-Blocking & Safety Invariants
# ---------------------------------------------------------------------------


def test_gnmi_set_dry_run_simulation(gnmi_device_profile: DeviceEndpointProfile):
    """Verify gNMI Set works in DRY_RUN simulation mode."""
    driver = GNMIControlPlane(declared_allowlist={"core-01"})
    driver.connect_mtls(gnmi_device_profile)

    resp = driver.set_openconfig_config(
        "core-01",
        OC_STATIC_DEFAULT_ROUTE,
        {"metric": 20},
        dry_run=True,
    )
    assert resp.success is True
    assert resp.status == ControlPlaneStatus.READY
    assert resp.details["dry_run"] is True


def test_gnmi_set_live_mutation_hard_blocked(gnmi_device_profile: DeviceEndpointProfile):
    """Verify live non-dry-run gNMI Set is hard-blocked and raises ProductionExecutionDisabledError."""
    driver = GNMIControlPlane(declared_allowlist={"core-01"})
    driver.connect_mtls(gnmi_device_profile)

    with pytest.raises(ProductionExecutionDisabledError) as exc_info:
        driver.set_openconfig_config(
            "core-01",
            OC_STATIC_DEFAULT_ROUTE,
            {"metric": 20},
            dry_run=False,  # Attempt live production mutation
        )

    assert "PRODUCTION_AUTHORIZED gNMI live mutation is strictly disabled" in str(exc_info.value)
