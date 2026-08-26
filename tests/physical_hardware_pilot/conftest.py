"""
Physical Hardware Pilot Test Harness — Shared Configuration & Fixtures.

REALISM RULE:
- Tests that communicate with a real physical device are classified as HARDWARE_QUALIFIED.
- Tests that run without a reachable device fallback to in-process mocks and are
  explicitly classified as MOCKED.

Environment variables (all optional; absent → MOCKED mode):
    HARDWARE_PILOT_HOST      Management IP of the staging device (e.g. 192.168.100.1)
    HARDWARE_PILOT_PORT      gNMI port (default 9339)
    HARDWARE_PILOT_VENDOR    NOSVendor string (default GENERIC_OPENCONFIG)
    HARDWARE_PILOT_HOSTNAME  TLS SAN / hostname (default staging-rtr-01.lab.internal)
    HARDWARE_PILOT_CA_CERT   Path to trusted CA cert PEM
    HARDWARE_PILOT_CLIENT_CERT Path to client cert PEM
    HARDWARE_PILOT_CLIENT_KEY  Path to client key PEM (NOT LOGGED)
    HARDWARE_PILOT_DEVICE_ID   Device ID string (default staging-rtr-01)
    HARDWARE_PILOT_TRANSPORT   GNMI_GRPC or NETCONF_YANG (default GNMI_GRPC)

Never log or print HARDWARE_PILOT_CLIENT_KEY or any private key material.
"""

import os
import socket
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest

from agents.failover.production_models import (
    DeviceEndpointProfile,
    NOSVendor,
    TransportProtocol,
)


# ---------------------------------------------------------------------------
# Hardware Pilot Mode Enum
# ---------------------------------------------------------------------------


class HardwarePilotMode:
    """Classification tag for each test result."""

    HARDWARE_QUALIFIED = "HARDWARE_QUALIFIED"
    MOCKED = "MOCKED"


# ---------------------------------------------------------------------------
# Helper: Probe TCP reachability (non-blocking, safe for test environment)
# ---------------------------------------------------------------------------

_PROBE_TIMEOUT_S = 2.0


def _tcp_probe(host: str, port: int, timeout: float = _PROBE_TIMEOUT_S) -> bool:
    """
    Attempt a raw TCP connection to verify device reachability.
    Returns True only when a connection is established; False on any failure.
    No data is sent or received — connection is closed immediately.
    """
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Shared Pilot Config Class
# ---------------------------------------------------------------------------


class HardwarePilotConfig:
    """
    Resolves physical hardware pilot configuration from environment variables.
    When no device is configured / reachable, mode → MOCKED.
    """

    SAFE_DEFAULTS = {
        "host": None,
        "port": 9339,
        "vendor": NOSVendor.GENERIC_OPENCONFIG,
        "hostname": "staging-rtr-01.lab.internal",
        "ca_cert": "/etc/ssl/ca-lab.pem",
        "client_cert": "/etc/ssl/client-lab.pem",
        "client_key": "/etc/ssl/client-lab.key",
        "device_id": "staging-rtr-01",
        "transport": TransportProtocol.GNMI_GRPC,
    }

    def __init__(self) -> None:
        self.host: Optional[str] = os.environ.get("HARDWARE_PILOT_HOST")
        self.port: int = int(os.environ.get("HARDWARE_PILOT_PORT", "9339"))
        self.device_id: str = os.environ.get("HARDWARE_PILOT_DEVICE_ID", "staging-rtr-01")
        self.hostname: str = os.environ.get("HARDWARE_PILOT_HOSTNAME", "staging-rtr-01.lab.internal")
        self.ca_cert: str = os.environ.get("HARDWARE_PILOT_CA_CERT", "/etc/ssl/ca-lab.pem")
        self.client_cert: str = os.environ.get("HARDWARE_PILOT_CLIENT_CERT", "/etc/ssl/client-lab.pem")
        self.client_key: str = os.environ.get("HARDWARE_PILOT_CLIENT_KEY", "/etc/ssl/client-lab.key")

        vendor_str = os.environ.get("HARDWARE_PILOT_VENDOR", "GENERIC_OPENCONFIG").upper()
        try:
            self.vendor: NOSVendor = NOSVendor(vendor_str)
        except ValueError:
            self.vendor = NOSVendor.GENERIC_OPENCONFIG

        transport_str = os.environ.get("HARDWARE_PILOT_TRANSPORT", "GNMI_GRPC").upper()
        self.transport: TransportProtocol = (
            TransportProtocol.NETCONF_YANG
            if transport_str == "NETCONF_YANG"
            else TransportProtocol.GNMI_GRPC
        )

        # Determine reachability
        self._reachable: Optional[bool] = None

    def is_device_configured(self) -> bool:
        """Returns True if a host IP has been explicitly configured."""
        return bool(self.host)

    def is_device_reachable(self) -> bool:
        """Returns True only if configured AND TCP probe succeeds (cached)."""
        if not self.is_device_configured():
            return False
        if self._reachable is None:
            self._reachable = _tcp_probe(self.host, self.port)
        return self._reachable

    @property
    def pilot_mode(self) -> str:
        """Return current pilot mode string."""
        return HardwarePilotMode.HARDWARE_QUALIFIED if self.is_device_reachable() else HardwarePilotMode.MOCKED

    def build_device_profile(self, allowlisted: bool = True) -> DeviceEndpointProfile:
        """Build a DeviceEndpointProfile from resolved configuration."""
        return DeviceEndpointProfile(
            device_id=self.device_id,
            hostname=self.hostname,
            management_ip=self.host if self.host else "127.0.0.1",
            management_port=self.port,
            vendor=self.vendor,
            transport=self.transport,
            tls_server_name=self.hostname,
            ca_cert_path=self.ca_cert,
            client_cert_path=self.client_cert,
            client_key_path=self.client_key,
            allowlisted=allowlisted,
        )


# ---------------------------------------------------------------------------
# Pytest Session-Scoped Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def pilot_config() -> HardwarePilotConfig:
    """Session-scoped hardware pilot configuration resolved from environment."""
    return HardwarePilotConfig()


@pytest.fixture(scope="session")
def pilot_mode(pilot_config: HardwarePilotConfig) -> str:
    """Session-scoped string identifying HARDWARE_QUALIFIED or MOCKED mode."""
    mode = pilot_config.pilot_mode
    print(f"\n[PILOT MODE] {mode}")
    return mode


@pytest.fixture(scope="session")
def device_profile(pilot_config: HardwarePilotConfig) -> DeviceEndpointProfile:
    """Session-scoped DeviceEndpointProfile for the pilot target device."""
    return pilot_config.build_device_profile()


@pytest.fixture(scope="session")
def pilot_maintenance_window():
    """Return an active maintenance window spanning ±4 hours around now."""
    from agents.failover.quorum_gate import MaintenanceWindow

    now = datetime.now(timezone.utc)
    return MaintenanceWindow(
        change_ticket_id="CHG-PILOT-PHASE6",
        start_time=now - timedelta(hours=4),
        end_time=now + timedelta(hours=4),
        target_devices=["staging-rtr-01"],
        approved_by="CAB_PILOT_LAB",
    )
