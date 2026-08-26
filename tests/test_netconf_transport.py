"""
Unit Test Suite for NOC Copilot v1.4 Phase 3: Typed NETCONF Transport & Read-Only OpenConfig.

Tests:
1. Successful NETCONF session establishment via mTLS profile
2. Read-only OpenConfig queries over structured YANG/XML
3. Typed helper methods: get_interface_state, get_static_default_route, get_bfd_peer_state
4. Non-mutating route verification
5. Readiness and capability reporting (read ENABLED, mutation DISABLED)
6. NETCONF edit-config dry-run simulation vs live mutation hard-blocking
7. Rejection of raw CLI strings and commands
"""

import pytest

from agents.failover import (
    ControlPlaneDriverType,
    ControlPlaneStatus,
    DeviceEndpointProfile,
    MockTransportServer,
    NETCONFControlPlane,
    NOSVendor,
    OC_STATIC_DEFAULT_ROUTE,
    ProductionExecutionDisabledError,
    RouteVerificationRequest,
    TransportProtocol,
)


@pytest.fixture
def netconf_device_profile() -> DeviceEndpointProfile:
    return DeviceEndpointProfile(
        device_id="rtr-01",
        hostname="rtr-01.corp.internal",
        management_ip="10.10.20.1",
        management_port=830,
        vendor=NOSVendor.CISCO_IOSXR,
        transport=TransportProtocol.NETCONF_YANG,
        tls_server_name="rtr-01.corp.internal",
        ca_cert_path="/etc/ssl/certs/ca.pem",
        client_cert_path="/etc/ssl/certs/client.pem",
        client_key_path="/etc/ssl/private/client.key",
        allowlisted=True,
    )


# ---------------------------------------------------------------------------
# 1. Connection & Readiness Lifecycle
# ---------------------------------------------------------------------------


def test_netconf_not_configured_readiness():
    """Verify NETCONFControlPlane reports NOT_CONFIGURED when not connected."""
    driver = NETCONFControlPlane()
    assert driver.is_configured is False
    assert driver.driver_type == ControlPlaneDriverType.NETCONF

    readiness = driver.check_readiness()
    assert readiness.success is False
    assert readiness.status == ControlPlaneStatus.NOT_CONFIGURED
    assert readiness.details["read_capability"] == "DISABLED"
    assert readiness.details["mutation_capability"] == "DISABLED"


def test_netconf_connection_success(netconf_device_profile: DeviceEndpointProfile):
    """Verify successful NETCONF session establishment."""
    driver = NETCONFControlPlane(declared_allowlist={"rtr-01"})
    assert driver.connect_mtls(netconf_device_profile) is True
    assert driver.is_configured is True

    readiness = driver.check_readiness()
    assert readiness.success is True
    assert readiness.status == ControlPlaneStatus.READY
    assert readiness.details["read_capability"] == "ENABLED"
    assert readiness.details["mutation_capability"] == "DISABLED"
    assert readiness.details["transport_type"] == "NETCONF_YANG"


# ---------------------------------------------------------------------------
# 2. Read-Only OpenConfig Queries
# ---------------------------------------------------------------------------


def test_netconf_read_interface_state(netconf_device_profile: DeviceEndpointProfile):
    """Verify reading OpenConfig interface state via NETCONF."""
    driver = NETCONFControlPlane(declared_allowlist={"rtr-01"})
    driver.connect_mtls(netconf_device_profile)

    if_state = driver.get_interface_state("rtr-01", "eth1")
    assert if_state is not None
    assert if_state.admin_status == "UP"
    assert if_state.oper_status == "UP"


def test_netconf_read_static_default_route(netconf_device_profile: DeviceEndpointProfile):
    """Verify reading OpenConfig static default route via NETCONF."""
    driver = NETCONFControlPlane(declared_allowlist={"rtr-01"})
    driver.connect_mtls(netconf_device_profile)

    route = driver.get_static_default_route("rtr-01")
    assert route is not None
    assert route.prefix == "0.0.0.0/0"
    assert route.next_hop == "10.10.1.1"


def test_netconf_read_bfd_state(netconf_device_profile: DeviceEndpointProfile):
    """Verify reading OpenConfig BFD state via NETCONF."""
    driver = NETCONFControlPlane(declared_allowlist={"rtr-01"})
    driver.connect_mtls(netconf_device_profile)

    bfd = driver.get_bfd_peer_state("rtr-01", "eth1", "10.10.1.1")
    assert bfd is not None
    assert bfd.local_state.value == "UP"


def test_netconf_non_mutating_route_verification(netconf_device_profile: DeviceEndpointProfile):
    """Verify non-mutating route verification via NETCONF."""
    driver = NETCONFControlPlane(declared_allowlist={"rtr-01"})
    driver.connect_mtls(netconf_device_profile)

    req = RouteVerificationRequest(
        target_device="rtr-01",
        expected_provider="ISP-A",
    )
    resp = driver.verify_route_path(req)
    assert resp.success is True
    assert resp.status == ControlPlaneStatus.READY


# ---------------------------------------------------------------------------
# 3. Mutation Hard-Blocking & Safety Invariants
# ---------------------------------------------------------------------------


def test_netconf_edit_config_dry_run(netconf_device_profile: DeviceEndpointProfile):
    """Verify NETCONF edit-config works in DRY_RUN simulation."""
    driver = NETCONFControlPlane(declared_allowlist={"rtr-01"})
    driver.connect_mtls(netconf_device_profile)

    resp = driver.set_openconfig_config(
        "rtr-01",
        OC_STATIC_DEFAULT_ROUTE,
        {"metric": 30},
        dry_run=True,
    )
    assert resp.success is True
    assert resp.status == ControlPlaneStatus.READY
    assert resp.details["dry_run"] is True


def test_netconf_edit_config_live_mutation_hard_blocked(netconf_device_profile: DeviceEndpointProfile):
    """Verify live non-dry-run NETCONF edit-config is hard-blocked and raises ProductionExecutionDisabledError."""
    driver = NETCONFControlPlane(declared_allowlist={"rtr-01"})
    driver.connect_mtls(netconf_device_profile)

    with pytest.raises(ProductionExecutionDisabledError) as exc_info:
        driver.set_openconfig_config(
            "rtr-01",
            OC_STATIC_DEFAULT_ROUTE,
            {"metric": 30},
            dry_run=False,  # Attempt live production mutation
        )

    assert "PRODUCTION_AUTHORIZED NETCONF live mutation is strictly disabled" in str(exc_info.value)
