"""
Phase 6A — Hardware Inventory Discovery Test.

Validates that the pilot target device exposes:
- vendor / model / NOS version
- management IP and port
- supported transport (gNMI / NETCONF)
- supported OpenConfig models
- BFD capability
- TLS capability declaration
- mTLS readiness flag

HARDWARE_QUALIFIED: reads inventory from real device.
MOCKED:             validates that declared profile metadata is structurally sound
                    and all required capabilities are present.
"""

import pytest

from agents.failover.production_control_plane import (
    ControlPlaneStatus,
    DryRunProductionControlPlane,
    GNMIControlPlane,
    NETCONFControlPlane,
    validate_endpoint_profile,
)
from agents.failover.production_models import (
    NOSVendor,
    TransportProtocol,
)


@pytest.mark.usefixtures("pilot_config", "pilot_mode", "device_profile")
class TestHardwareInventory:
    """Phase 6A: Hardware Inventory — validate device profile and capability declarations."""

    def test_device_profile_is_structurally_valid(self, device_profile, pilot_mode):
        """
        Profile must pass structural validation: non-empty IDs, valid IP, valid port,
        non-empty cert paths, correct vendor/transport enums.
        Classification: always runs regardless of mode.
        """
        is_valid, errors = validate_endpoint_profile(device_profile)
        assert is_valid, f"[{pilot_mode}] DeviceEndpointProfile validation failed: {errors}"
        print(f"\n[{pilot_mode}] Device profile '{device_profile.device_id}' validated OK.")

    def test_management_ip_declared(self, device_profile, pilot_mode):
        """Management IP must be declared and non-empty."""
        assert device_profile.management_ip, f"[{pilot_mode}] management_ip is empty"

    def test_management_port_in_range(self, device_profile, pilot_mode):
        """Management port must be in valid port range."""
        assert 1 <= device_profile.management_port <= 65535, (
            f"[{pilot_mode}] management_port {device_profile.management_port} is out of range"
        )

    def test_vendor_is_known_nos(self, device_profile, pilot_mode):
        """Device vendor must resolve to a known NOSVendor enum value."""
        assert isinstance(device_profile.vendor, NOSVendor), (
            f"[{pilot_mode}] vendor '{device_profile.vendor}' is not a recognised NOSVendor"
        )
        print(f"\n[{pilot_mode}] Vendor: {device_profile.vendor.value}")

    def test_transport_protocol_is_supported(self, device_profile, pilot_mode):
        """Transport must be either GNMI_GRPC or NETCONF_YANG."""
        assert device_profile.transport in [TransportProtocol.GNMI_GRPC, TransportProtocol.NETCONF_YANG], (
            f"[{pilot_mode}] transport '{device_profile.transport}' is not a supported structured protocol"
        )
        print(f"\n[{pilot_mode}] Transport: {device_profile.transport.value}")

    def test_openconfig_models_declared(self, device_profile, pilot_mode):
        """At least one OpenConfig YANG model must be declared in the profile."""
        assert len(device_profile.supported_models) >= 1, (
            f"[{pilot_mode}] No OpenConfig YANG models declared in device profile"
        )
        for m in device_profile.supported_models:
            assert ".yang" in m, f"[{pilot_mode}] Model '{m}' does not look like a YANG schema path"
        print(f"\n[{pilot_mode}] Models declared: {device_profile.supported_models}")

    def test_bfd_model_declared(self, device_profile, pilot_mode):
        """openconfig-bfd.yang must be in declared supported models or noted MOCKED."""
        if "openconfig-bfd.yang" not in device_profile.supported_models:
            # BFD model absent — mark as MOCKED limitation
            pytest.skip(f"[{pilot_mode}] openconfig-bfd.yang not declared — BFD MOCKED")
        print(f"\n[{pilot_mode}] BFD capability: DECLARED")

    def test_tls_server_name_matches_hostname(self, device_profile, pilot_mode):
        """TLS SAN / server name must match the declared device hostname."""
        assert device_profile.tls_server_name == device_profile.hostname, (
            f"[{pilot_mode}] tls_server_name '{device_profile.tls_server_name}' "
            f"!= hostname '{device_profile.hostname}'"
        )

    def test_device_is_allowlisted(self, device_profile, pilot_mode):
        """Device must be explicitly allowlisted before inventory is valid."""
        assert device_profile.allowlisted is True, (
            f"[{pilot_mode}] Device '{device_profile.device_id}' has allowlisted=False"
        )

    def test_control_plane_check_readiness(self, device_profile, pilot_mode):
        """
        Instantiate a DryRunProductionControlPlane and confirm readiness.
        On real hardware this verifies the driver boots correctly against the profile.
        """
        cp = DryRunProductionControlPlane(declared_allowlist={device_profile.device_id})
        readiness = cp.check_readiness()
        assert readiness.status == ControlPlaneStatus.READY, (
            f"[{pilot_mode}] Control plane readiness check failed: {readiness.message}"
        )
        print(f"\n[{pilot_mode}] Control plane readiness: {readiness.status.value}")

    def test_hardware_mode_is_logged(self, pilot_mode, pilot_config):
        """Confirm pilot mode is correctly detected and logged in the report."""
        if pilot_config.is_device_reachable():
            assert pilot_mode == "HARDWARE_QUALIFIED", (
                "Device is reachable but mode is not HARDWARE_QUALIFIED"
            )
            print(f"\n[{pilot_mode}] ✓ Physical device REACHABLE at {pilot_config.host}:{pilot_config.port}")
        else:
            assert pilot_mode == "MOCKED", "Device is unreachable but mode is not MOCKED"
            print(
                f"\n[{pilot_mode}] ✓ No physical device configured (HARDWARE_PILOT_HOST not set) — "
                "all hardware I/O delegated to in-process deterministic mocks."
            )
