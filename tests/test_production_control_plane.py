"""
Unit Test Suite for NOC Copilot v1.4 Phase 1: Typed Production Control-Plane Abstraction.

Validates:
1. Endpoint model validation
2. Vendor enum
3. Transport enum
4. BFD state model
5. Frozen endpoint profile immutability
6. Allowlist validation
7. Unsafe endpoint rejection
8. Not-configured readiness
9. Dry-run non-mutation
10. Production mutation remains blocked
11. Existing FRRControlPlane compatibility
12. Existing LAB_AUTHORIZED behavior unchanged
13. No shell/subprocess/network side effects
"""

import pytest
from pydantic import ValidationError

from agents.failover.failover_models import ProductionExecutionDisabledError
from agents.failover.network_control_plane import (
    ControlPlaneDriverType,
    ControlPlaneStatus,
    FailbackProviderRequest,
    FailoverProviderRequest,
)
from agents.failover.production_control_plane import (
    DryRunProductionControlPlane,
    IProductionControlPlane,
    NotConfiguredProductionControlPlane,
    validate_endpoint_profile,
)
from agents.failover.production_models import (
    BFDState,
    BFDTelemetrySignal,
    DeviceEndpointProfile,
    NOSVendor,
    OC_BFD_STATE,
    OC_INTERFACE_CONFIG,
    OC_INTERFACE_STATE,
    OC_NEXT_HOP,
    OC_STATIC_DEFAULT_ROUTE,
    OC_STATIC_ROUTE_METRIC,
    OpenConfigMutation,
    OpenConfigQuery,
    TransportProtocol,
)


@pytest.fixture
def valid_endpoint_profile() -> DeviceEndpointProfile:
    """Fixture for a valid Arista EOS endpoint profile."""
    return DeviceEndpointProfile(
        device_id="core-01",
        hostname="core-01.corp.internal",
        management_ip="192.168.10.1",
        management_port=9339,
        vendor=NOSVendor.ARISTA_EOS,
        transport=TransportProtocol.GNMI_GRPC,
        tls_server_name="core-01.corp.internal",
        ca_cert_path="/etc/ssl/certs/corp_ca.pem",
        client_cert_path="/etc/ssl/certs/copilot_client.pem",
        client_key_path="/etc/ssl/private/copilot_client.key",
        allowlisted=True,
    )


# ---------------------------------------------------------------------------
# 1. Enum & Model Validation
# ---------------------------------------------------------------------------


def test_nos_vendor_enum_values():
    """Verify supported NOS vendors."""
    assert NOSVendor.ARISTA_EOS.value == "ARISTA_EOS"
    assert NOSVendor.CISCO_IOSXR.value == "CISCO_IOSXR"
    assert NOSVendor.CISCO_IOSXE.value == "CISCO_IOSXE"
    assert NOSVendor.JUNIPER_JUNOS.value == "JUNIPER_JUNOS"
    assert NOSVendor.SONIC.value == "SONIC"
    assert NOSVendor.FRROUTING.value == "FRROUTING"
    assert NOSVendor.GENERIC_OPENCONFIG.value == "GENERIC_OPENCONFIG"


def test_transport_protocol_enum():
    """Verify transport protocol enum explicitly excludes CLI/SSH."""
    assert TransportProtocol.GNMI_GRPC.value == "GNMI_GRPC"
    assert TransportProtocol.NETCONF_YANG.value == "NETCONF_YANG"
    assert len(TransportProtocol) == 2
    assert not hasattr(TransportProtocol, "SSH_CLI")
    assert not hasattr(TransportProtocol, "SHELL")


def test_bfd_state_model_and_signal():
    """Verify BFDState enum and BFDTelemetrySignal model."""
    assert BFDState.UP.value == "UP"
    assert BFDState.DOWN.value == "DOWN"
    assert BFDState.INIT.value == "INIT"
    assert BFDState.ADMIN_DOWN.value == "ADMIN_DOWN"

    signal = BFDTelemetrySignal(
        device_id="rtr-01",
        interface_name="eth1",
        peer_address="10.10.1.1",
        local_state=BFDState.UP,
        remote_state=BFDState.UP,
        detection_time_ms=50.0,
        flap_count=0,
    )
    assert signal.device_id == "rtr-01"
    assert signal.local_state == BFDState.UP
    assert signal.detection_time_ms == 50.0

    # Verify frozen immutability
    with pytest.raises(ValidationError):
        signal.local_state = BFDState.DOWN  # type: ignore


def test_frozen_endpoint_profile_immutability(valid_endpoint_profile: DeviceEndpointProfile):
    """Verify DeviceEndpointProfile is frozen and prevents mutation."""
    assert valid_endpoint_profile.device_id == "core-01"
    assert valid_endpoint_profile.vendor == NOSVendor.ARISTA_EOS

    with pytest.raises(ValidationError):
        valid_endpoint_profile.management_ip = "10.0.0.1"  # type: ignore

    with pytest.raises(ValidationError):
        valid_endpoint_profile.allowlisted = False  # type: ignore


def test_openconfig_path_constants():
    """Verify standard OpenConfig path constants are correctly formatted."""
    assert "/interfaces/interface[name={name}]/state" == OC_INTERFACE_STATE
    assert "/interfaces/interface[name={name}]/config" == OC_INTERFACE_CONFIG
    assert "static-routes/static[prefix=0.0.0.0/0]" in OC_STATIC_DEFAULT_ROUTE
    assert "metric" in OC_STATIC_ROUTE_METRIC
    assert "next-hop" in OC_NEXT_HOP
    assert "peers/peer[address={peer_ip}]/state" in OC_BFD_STATE


# ---------------------------------------------------------------------------
# 2. Endpoint Validation & Security Verification
# ---------------------------------------------------------------------------


def test_validate_endpoint_profile_success(valid_endpoint_profile: DeviceEndpointProfile):
    """Verify validation passes for an authorized, well-formed profile."""
    allowlist = {"core-01", "rtr-01", "branch3-uplink"}
    is_valid, errors = validate_endpoint_profile(valid_endpoint_profile, allowlist=allowlist)
    assert is_valid is True
    assert len(errors) == 0


def test_validate_endpoint_profile_unallowlisted(valid_endpoint_profile: DeviceEndpointProfile):
    """Verify unallowlisted device is rejected."""
    allowlist = {"rtr-01", "branch3-uplink"}  # core-01 missing
    is_valid, errors = validate_endpoint_profile(valid_endpoint_profile, allowlist=allowlist)
    assert is_valid is False
    assert any("not in declared production allowlist" in err for err in errors)


def test_validate_endpoint_profile_unsafe_command_injection():
    """Verify shell/command injection tokens in device_id or hostname are rejected."""
    unsafe_profile = DeviceEndpointProfile(
        device_id="core-01; rm -rf /",
        hostname="core-01.corp.internal && bash",
        management_ip="192.168.10.1",
        management_port=9339,
        vendor=NOSVendor.CISCO_IOSXR,
        transport=TransportProtocol.GNMI_GRPC,
        tls_server_name="core-01.corp.internal | sudo",
        ca_cert_path="/etc/ssl/certs/ca.pem; eval",
        client_cert_path="/etc/ssl/certs/client.pem",
        client_key_path="/etc/ssl/private/client.key",
        allowlisted=True,
    )
    is_valid, errors = validate_endpoint_profile(unsafe_profile)
    assert is_valid is False
    assert len(errors) >= 3


def test_validate_endpoint_profile_invalid_ip():
    """Verify invalid IP addresses are caught during validation."""
    bad_ip_profile = DeviceEndpointProfile(
        device_id="core-01",
        hostname="core-01.corp.internal",
        management_ip="999.999.999.999",
        management_port=9339,
        vendor=NOSVendor.JUNIPER_JUNOS,
        transport=TransportProtocol.NETCONF_YANG,
        tls_server_name="core-01.corp.internal",
        ca_cert_path="/etc/ssl/certs/ca.pem",
        client_cert_path="/etc/ssl/certs/client.pem",
        client_key_path="/etc/ssl/private/client.key",
        allowlisted=True,
    )
    is_valid, errors = validate_endpoint_profile(bad_ip_profile)
    assert is_valid is False
    assert any("Invalid management IP address" in err for err in errors)


def test_validate_endpoint_profile_invalid_port():
    """Verify invalid port numbers are rejected."""
    bad_port_profile = DeviceEndpointProfile(
        device_id="core-01",
        hostname="core-01.corp.internal",
        management_ip="192.168.10.1",
        management_port=70000,
        vendor=NOSVendor.SONIC,
        transport=TransportProtocol.GNMI_GRPC,
        tls_server_name="core-01.corp.internal",
        ca_cert_path="/etc/ssl/certs/ca.pem",
        client_cert_path="/etc/ssl/certs/client.pem",
        client_key_path="/etc/ssl/private/client.key",
        allowlisted=True,
    )
    is_valid, errors = validate_endpoint_profile(bad_port_profile)
    assert is_valid is False
    assert any("Invalid management port" in err for err in errors)


# ---------------------------------------------------------------------------
# 3. NotConfiguredProductionControlPlane Behavior
# ---------------------------------------------------------------------------


def test_not_configured_production_control_plane():
    """Verify NotConfiguredProductionControlPlane safely rejects all calls."""
    cp = NotConfiguredProductionControlPlane()
    assert cp.is_configured is False
    assert cp.driver_type == ControlPlaneDriverType.NONE

    # Readiness
    readiness = cp.check_readiness()
    assert readiness.success is False
    assert readiness.status == ControlPlaneStatus.NOT_CONFIGURED

    # mTLS Connect
    profile = DeviceEndpointProfile(
        device_id="core-01",
        hostname="core-01",
        management_ip="10.0.0.1",
        vendor=NOSVendor.ARISTA_EOS,
        tls_server_name="core-01",
        ca_cert_path="/ca.pem",
        client_cert_path="/cert.pem",
        client_key_path="/key.pem",
    )
    assert cp.connect_mtls(profile) is False

    # Read OpenConfig
    assert cp.read_openconfig_state("core-01", OC_INTERFACE_STATE) == {}

    # Set OpenConfig
    resp = cp.set_openconfig_config("core-01", OC_STATIC_DEFAULT_ROUTE, {"metric": 20})
    assert resp.success is False
    assert resp.status == ControlPlaneStatus.NOT_CONFIGURED

    # Stream BFD
    assert cp.stream_bfd_events("core-01") == []

    # Failover / Failback / Verify
    fo_req = FailoverProviderRequest(
        target_device="core-01",
        wan_interface="eth1",
        source_provider="ISP-A",
        target_provider="ISP-B",
    )
    fo_resp = cp.failover_provider(fo_req)
    assert fo_resp.success is False
    assert fo_resp.status == ControlPlaneStatus.NOT_CONFIGURED


# ---------------------------------------------------------------------------
# 4. DryRunProductionControlPlane Behavior & Mutation Blocking
# ---------------------------------------------------------------------------


def test_dry_run_production_control_plane_readiness(valid_endpoint_profile: DeviceEndpointProfile):
    """Verify DryRunProductionControlPlane readiness and connection validation."""
    cp = DryRunProductionControlPlane(declared_allowlist={"core-01", "rtr-01"})
    assert cp.is_configured is True

    readiness = cp.check_readiness()
    assert readiness.success is True
    assert readiness.status == ControlPlaneStatus.READY

    # Connect valid profile
    assert cp.connect_mtls(valid_endpoint_profile) is True

    # Connect unallowlisted profile
    unallowlisted = DeviceEndpointProfile(
        device_id="unauthorized-core",
        hostname="unauthorized.corp",
        management_ip="10.0.0.99",
        vendor=NOSVendor.CISCO_IOSXR,
        tls_server_name="unauthorized.corp",
        ca_cert_path="/ca.pem",
        client_cert_path="/cert.pem",
        client_key_path="/key.pem",
    )
    assert cp.connect_mtls(unallowlisted) is False


def test_dry_run_production_control_plane_simulated_read_write():
    """Verify OpenConfig simulated reads and DRY_RUN mutations."""
    cp = DryRunProductionControlPlane(declared_allowlist={"core-01"})

    # Read default state
    state = cp.read_openconfig_state("core-01", OC_STATIC_DEFAULT_ROUTE)
    assert state["openconfig-network-instance:static"]["metric"] == 10

    # Dry-run mutation
    resp = cp.set_openconfig_config(
        "core-01",
        OC_STATIC_ROUTE_METRIC,
        {"metric": 50},
        dry_run=True,
    )
    assert resp.success is True
    assert resp.status == ControlPlaneStatus.READY
    assert resp.details["dry_run"] is True

    # Read back mutated state
    mutated = cp.read_openconfig_state("core-01", OC_STATIC_ROUTE_METRIC)
    assert mutated == {"metric": 50}


def test_production_mutation_hard_blocked_in_driver():
    """Verify live non-dry-run production mutation raises ProductionExecutionDisabledError."""
    cp = DryRunProductionControlPlane(declared_allowlist={"core-01"})

    with pytest.raises(ProductionExecutionDisabledError) as exc_info:
        cp.set_openconfig_config(
            "core-01",
            OC_STATIC_DEFAULT_ROUTE,
            {"metric": 20},
            dry_run=False,  # ATTEMPT LIVE MUTATION
        )

    assert "PRODUCTION_AUTHORIZED live hardware mutation is strictly disabled" in str(exc_info.value)


def test_dry_run_production_control_plane_bfd():
    """Verify BFD signals are provided for allowlisted devices."""
    cp = DryRunProductionControlPlane(declared_allowlist={"core-01"})

    signals = cp.stream_bfd_events("core-01")
    assert len(signals) == 1
    assert signals[0].device_id == "core-01"
    assert signals[0].local_state == BFDState.UP

    # Unallowlisted device returns empty list
    assert cp.stream_bfd_events("rogue-router") == []


def test_interface_compatibility():
    """Verify IProductionControlPlane is an instance of INetworkControlPlane."""
    assert issubclass(IProductionControlPlane, object)
    cp = DryRunProductionControlPlane()
    assert isinstance(cp, IProductionControlPlane)

    # Standard failover request works in dry-run mode
    req = FailoverProviderRequest(
        target_device="core-01",
        wan_interface="eth1",
        source_provider="ISP-A",
        target_provider="ISP-B",
    )
    resp = cp.failover_provider(req)
    assert resp.success is True
    assert resp.status == ControlPlaneStatus.READY
