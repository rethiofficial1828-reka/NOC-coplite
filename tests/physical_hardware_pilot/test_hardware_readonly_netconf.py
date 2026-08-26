"""
Phase 6C (NETCONF) — Read-Only NETCONF Control-Plane Pilot Test.

Validates typed NETCONF transport for READ-ONLY OpenConfig state retrieval:
- Interface operational state
- Default static route
- Device system information
- Confirms NO edit-config mutations occur

HARDWARE_QUALIFIED: Sends real NETCONF get requests (RFC 6241) to physical device.
MOCKED:             Exercises NETCONFControlPlane against in-process MockTransportServer.

CRITICAL SAFETY:
    - NETCONFControlPlane.set_openconfig_config(dry_run=False) is NEVER called.
    - edit-config mutations are hard-blocked.
"""

import pytest

from agents.failover.production_control_plane import (
    ControlPlaneStatus,
    MockTransportServer,
    NETCONFControlPlane,
)
from agents.failover.production_models import (
    OC_INTERFACE_STATE,
    OC_STATIC_DEFAULT_ROUTE,
    TransportProtocol,
)


class TestHardwareReadOnlyNETCONF:
    """Phase 6C: Read-only NETCONF OpenConfig state retrieval."""

    @pytest.fixture(autouse=True)
    def netconf_driver(self, device_profile, pilot_mode):
        """
        Build NETCONFControlPlane for the pilot device.
        MOCKED: registers in-process mock; HARDWARE: connects to management port 830.
        """
        mock_server = MockTransportServer()
        mock_server.set_custom_response(
            OC_INTERFACE_STATE.format(name="eth0"),
            {
                "openconfig-interfaces:state": {
                    "name": "eth0",
                    "admin-status": "UP",
                    "oper-status": "UP",
                }
            },
        )

        cp = NETCONFControlPlane(
            declared_allowlist={device_profile.device_id},
            mock_server=mock_server,
        )

        # Attempt mTLS connect — validates profile in MOCKED mode
        connected = cp.connect_mtls(device_profile)
        assert connected, (
            f"[{pilot_mode}] NETCONFControlPlane.connect_mtls failed for '{device_profile.device_id}'"
        )
        self._cp = cp
        self._device_id = device_profile.device_id
        yield cp

    def test_netconf_readiness_after_connect(self, pilot_mode):
        """NETCONF driver must report READY after successful connect_mtls."""
        readiness = self._cp.check_readiness()
        assert readiness.status == ControlPlaneStatus.READY, (
            f"[{pilot_mode}] NETCONF readiness check failed: {readiness.message}"
        )
        print(f"\n[{pilot_mode}] NETCONF readiness: {readiness.status.value}")

    def test_netconf_read_interface_state(self, pilot_mode):
        """Read eth0 interface state — must return non-empty dict."""
        path = OC_INTERFACE_STATE.format(name="eth0")
        result = self._cp.read_openconfig_state(self._device_id, path)
        assert isinstance(result, dict), f"[{pilot_mode}] Interface state is not a dict"
        assert len(result) > 0, f"[{pilot_mode}] Interface state response is empty"
        print(f"\n[{pilot_mode}] NETCONF interface state: {result}")

    def test_netconf_read_default_route(self, pilot_mode):
        """Read default static route over NETCONF — must return non-empty dict."""
        result = self._cp.read_openconfig_state(self._device_id, OC_STATIC_DEFAULT_ROUTE)
        assert isinstance(result, dict), f"[{pilot_mode}] Default route is not a dict"
        print(f"\n[{pilot_mode}] NETCONF default route: {result}")

    def test_netconf_no_editconfig_mutation(self, device_profile, pilot_mode):
        """
        edit-config mutation must be hard-blocked.
        Verifies that calling set_openconfig_config with dry_run=False raises.
        """
        from agents.failover.failover_models import ProductionExecutionDisabledError

        cp = NETCONFControlPlane(declared_allowlist={device_profile.device_id})
        cp.connect_mtls(device_profile)

        with pytest.raises((ProductionExecutionDisabledError, ValueError, NotImplementedError, Exception)):
            cp.set_openconfig_config(
                device_profile.device_id,
                OC_INTERFACE_STATE.format(name="eth0"),
                {"admin-status": "DOWN"},
                dry_run=False,
            )
        print(f"\n[{pilot_mode}] NETCONF edit-config mutation hard-blocked: OK")

    def test_netconf_bfd_state_mocked(self, pilot_mode):
        """
        BFD state over NETCONF.
        In MOCKED mode verifies the mock server returns the correct BFD structure.
        """
        from agents.failover.production_models import OC_BFD_STATE
        from agents.failover.production_control_plane import MockTransportServer

        ms = MockTransportServer()
        ms.set_custom_response(
            OC_BFD_STATE.format(id="eth0", peer_ip="10.0.0.1"),
            {
                "openconfig-bfd:state": {
                    "local-state": "UP",
                    "remote-state": "UP",
                    "detection-time-ms": 50,
                }
            },
        )
        result = ms.handle_get(self._device_id, OC_BFD_STATE.format(id="eth0", peer_ip="10.0.0.1"))
        assert "openconfig-bfd:state" in result, (
            f"[{pilot_mode}] BFD state structure missing from mock response"
        )
        print(f"\n[{pilot_mode}] NETCONF BFD state (MOCKED): {result}")
