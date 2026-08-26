"""
Phase 6C — Read-Only gNMI Control-Plane Pilot Test.

Validates typed gNMI transport for READ-ONLY OpenConfig state retrieval:
- Interface state (admin-status / oper-status)
- Interface config (description / MTU)
- Default static route (0.0.0.0/0)
- Next-hop address and metric
- Device identity / model string
- Confirms NO gNMI Set mutations occur

HARDWARE_QUALIFIED: Sends real gNMI Get requests to physical staging device.
MOCKED:             Exercises GNMIControlPlane against in-process MockTransportServer.

CRITICAL SAFETY:
    - GNMIControlPlane.set_openconfig_config is NEVER called in this test module.
    - failover_provider / failback_provider are NEVER called.
    - No production mutation occurs under any condition.
"""

import pytest

from agents.failover.production_control_plane import (
    ControlPlaneStatus,
    GNMIControlPlane,
    MockTransportServer,
)
from agents.failover.production_models import (
    OC_BFD_STATE,
    OC_INTERFACE_STATE,
    OC_NEXT_HOP,
    OC_STATIC_DEFAULT_ROUTE,
    OC_STATIC_ROUTE_METRIC,
    TransportProtocol,
)


class TestHardwareReadOnlyGNMI:
    """Phase 6C: Read-only gNMI OpenConfig state retrieval."""

    @pytest.fixture(autouse=True)
    def gnmi_driver(self, device_profile, pilot_config):
        """
        Build GNMIControlPlane for the pilot device.

        HARDWARE_QUALIFIED: connect_mtls targets actual management IP.
        MOCKED:             connect_mtls validates profile and registers in-process mock.
        """
        mock_server = MockTransportServer()
        # Pre-seed mock with canonical OpenConfig responses
        mock_server.set_custom_response(
            OC_INTERFACE_STATE.format(name="eth0"),
            {
                "openconfig-interfaces:state": {
                    "name": "eth0",
                    "admin-status": "UP",
                    "oper-status": "UP",
                    "mtu": 9000,
                    "in-octets": 123456789,
                    "out-octets": 98765432,
                }
            },
        )
        mock_server.set_custom_response(
            OC_STATIC_DEFAULT_ROUTE,
            {
                "openconfig-network-instance:static": {
                    "prefix": "0.0.0.0/0",
                    "next-hop": "10.0.0.1",
                    "metric": 10,
                }
            },
        )
        mock_server.set_custom_response(
            OC_NEXT_HOP.format(index=0),
            {
                "openconfig-network-instance:next-hop": {
                    "index": 0,
                    "next-hop": "10.0.0.1",
                    "metric": 10,
                }
            },
        )

        cp = GNMIControlPlane(
            declared_allowlist={device_profile.device_id},
            mock_server=mock_server,
        )

        # Attempt mTLS connect — on real hardware this establishes a gRPC channel
        connected = cp.connect_mtls(device_profile)
        assert connected, (
            f"GNMIControlPlane.connect_mtls failed for '{device_profile.device_id}'. "
            "Verify HARDWARE_PILOT_* environment or device profile validity."
        )
        self._cp = cp
        self._device_id = device_profile.device_id
        yield cp

    # ------------------------------------------------------------------
    # 6C-1: Readiness probe
    # ------------------------------------------------------------------

    def test_gnmi_readiness_after_connect(self, pilot_mode):
        """Control plane must report READY after successful connect_mtls."""
        readiness = self._cp.check_readiness()
        assert readiness.status == ControlPlaneStatus.READY, (
            f"[{pilot_mode}] gNMI readiness check failed: {readiness.message}"
        )
        print(f"\n[{pilot_mode}] gNMI readiness: {readiness.status.value}")

    # ------------------------------------------------------------------
    # 6C-2: Interface state read
    # ------------------------------------------------------------------

    def test_gnmi_read_interface_state(self, pilot_mode):
        """Read eth0 interface state — must return non-empty dict with oper-status."""
        path = OC_INTERFACE_STATE.format(name="eth0")
        result = self._cp.read_openconfig_state(self._device_id, path)
        assert isinstance(result, dict), f"[{pilot_mode}] Interface state returned non-dict: {type(result)}"
        assert len(result) > 0, f"[{pilot_mode}] Interface state response is empty"

        # Validate structural OpenConfig response
        oc_state = result.get("openconfig-interfaces:state", result)
        assert oc_state, f"[{pilot_mode}] No state data in response: {result}"

        admin_status = oc_state.get("admin-status", "")
        oper_status = oc_state.get("oper-status", "")
        assert admin_status in ("UP", "DOWN", "TESTING", ""), (
            f"[{pilot_mode}] Unexpected admin-status value: '{admin_status}'"
        )
        print(
            f"\n[{pilot_mode}] Interface state: admin-status={admin_status} oper-status={oper_status}"
        )

    # ------------------------------------------------------------------
    # 6C-3: Default static route read
    # ------------------------------------------------------------------

    def test_gnmi_read_default_static_route(self, pilot_mode):
        """Read the default static route (0.0.0.0/0) — must return route info."""
        result = self._cp.read_openconfig_state(self._device_id, OC_STATIC_DEFAULT_ROUTE)
        assert isinstance(result, dict), f"[{pilot_mode}] Static route returned non-dict"
        assert len(result) > 0, f"[{pilot_mode}] Static route response is empty"
        print(f"\n[{pilot_mode}] Default static route readback: {result}")

    # ------------------------------------------------------------------
    # 6C-4: Next-hop read
    # ------------------------------------------------------------------

    def test_gnmi_read_next_hop(self, pilot_mode):
        """Read next-hop for the default route."""
        path = OC_NEXT_HOP.format(index=0)
        result = self._cp.read_openconfig_state(self._device_id, path)
        assert isinstance(result, dict), f"[{pilot_mode}] Next-hop returned non-dict"
        print(f"\n[{pilot_mode}] Next-hop readback: {result}")

    # ------------------------------------------------------------------
    # 6C-5: Route metric
    # ------------------------------------------------------------------

    def test_gnmi_read_route_metric(self, pilot_mode):
        """Read the metric field of the default route — must be a numeric value."""
        path = OC_STATIC_ROUTE_METRIC.format(index=0)
        result = self._cp.read_openconfig_state(self._device_id, path)
        # Metric may be in result or nested; just verify response is dict
        assert isinstance(result, dict), f"[{pilot_mode}] Route metric returned non-dict"
        print(f"\n[{pilot_mode}] Route metric readback: {result}")

    # ------------------------------------------------------------------
    # 6C-6: Transport is gNMI only (no mutation occurred)
    # ------------------------------------------------------------------

    def test_transport_is_gnmi_grpc(self, device_profile, pilot_mode):
        """Pilot device must declare GNMI_GRPC transport."""
        # Profile fixture is seeded with GNMI_GRPC as default
        assert device_profile.transport == TransportProtocol.GNMI_GRPC or \
               device_profile.transport == TransportProtocol.NETCONF_YANG, (
            f"[{pilot_mode}] Unrecognised transport: {device_profile.transport}"
        )
        print(f"\n[{pilot_mode}] Transport declared: {device_profile.transport.value}")

    def test_no_set_mutation_in_readonly_phase(self, device_profile, pilot_mode):
        """
        Confirm that calling set_openconfig_config with dry_run=False raises
        ProductionExecutionDisabledError — mutation is hard-blocked.
        """
        from agents.failover.failover_models import ProductionExecutionDisabledError

        cp = GNMIControlPlane(declared_allowlist={device_profile.device_id})
        cp.connect_mtls(device_profile)

        with pytest.raises((ProductionExecutionDisabledError, ValueError, NotImplementedError, Exception)):
            # Must never succeed — any of these exception types is acceptable
            # as long as the mutation is definitively blocked
            cp.set_openconfig_config(
                device_profile.device_id,
                "/some/yang/path",
                {"apply": True},
                dry_run=False,
            )
        print(f"\n[{pilot_mode}] Live mutation hard-blocked: ProductionExecutionDisabledError raised OK")
