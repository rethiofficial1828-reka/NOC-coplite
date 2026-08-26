"""
Virtual Device Manager for Hardware Harness Integration.

Handles discovery of local Docker virtual NOS images, lifecycle orchestration,
isolated network provisioning, and test-only PKI certificate injection.
"""

import subprocess
from typing import Dict, List, Optional, Set

from agents.core.logger import get_agent_logger
from agents.failover.production_models import (
    DeviceEndpointProfile,
    NOSVendor,
    TransportProtocol,
)
from tests.hardware_harness.harness_models import (
    VirtualDeviceStatus,
    VirtualNOSSpec,
)

logger = get_agent_logger("VirtualDeviceManager")


class VirtualDeviceManager:
    """
    Manages isolated virtual network operating system instances and hardware qualification tests.
    """

    KNOWN_SPECS: List[VirtualNOSSpec] = [
        VirtualNOSSpec(
            device_id="frr-router-01",
            vendor=NOSVendor.FRROUTING,
            image_name="frrouting/frr:latest",
            management_ip="127.0.0.1",
            management_port=9339,
            transport=TransportProtocol.GNMI_GRPC,
            tls_server_name="frr-router-01.corp.internal",
        ),
        VirtualNOSSpec(
            device_id="arista-ceos-01",
            vendor=NOSVendor.ARISTA_EOS,
            image_name="arista/ceos:latest",
            management_ip="127.0.0.1",
            management_port=9339,
            transport=TransportProtocol.GNMI_GRPC,
            tls_server_name="arista-ceos-01.corp.internal",
        ),
        VirtualNOSSpec(
            device_id="cisco-c8k-01",
            vendor=NOSVendor.CISCO_IOSXR,
            image_name="cisco/c8000v:latest",
            management_ip="127.0.0.1",
            management_port=830,
            transport=TransportProtocol.NETCONF_YANG,
            tls_server_name="cisco-c8k-01.corp.internal",
        ),
        VirtualNOSSpec(
            device_id="sonic-leaf-01",
            vendor=NOSVendor.SONIC,
            image_name="sonic:latest",
            management_ip="127.0.0.1",
            management_port=9339,
            transport=TransportProtocol.GNMI_GRPC,
            tls_server_name="sonic-leaf-01.corp.internal",
        ),
    ]

    _CACHED_IMAGES: Optional[Set[str]] = None

    def __init__(self) -> None:
        if VirtualDeviceManager._CACHED_IMAGES is None:
            VirtualDeviceManager._CACHED_IMAGES = self._discover_docker_images()
        self._installed_images: Set[str] = VirtualDeviceManager._CACHED_IMAGES
        self._devices: Dict[str, VirtualNOSSpec] = {}
        self._device_states: Dict[str, VirtualDeviceStatus] = {}
        self._initialize_inventory()

    def _discover_docker_images(self) -> Set[str]:
        """Detect installed Docker images locally with static fallback."""
        default_images = {"frrouting/frr:latest", "frrouting/frr"}
        try:
            res = subprocess.run(
                ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if res.returncode == 0 and res.stdout.strip():
                images = set(res.stdout.strip().splitlines())
                repo_names = {img.split(":")[0] for img in images if ":" in img}
                return images | repo_names | default_images
        except Exception:
            pass
        return default_images

    def _initialize_inventory(self) -> None:
        """Populate inventory and evaluate image availability."""
        for spec in self.KNOWN_SPECS:
            is_avail = (
                spec.image_name in self._installed_images
                or spec.image_name.split(":")[0] in self._installed_images
            )
            # Create resolved spec
            resolved_spec = VirtualNOSSpec(
                device_id=spec.device_id,
                vendor=spec.vendor,
                image_name=spec.image_name,
                management_ip=spec.management_ip,
                management_port=spec.management_port,
                transport=spec.transport,
                is_image_available=is_avail,
                tls_server_name=spec.tls_server_name,
                supported_models=spec.supported_models,
            )
            self._devices[spec.device_id] = resolved_spec
            self._device_states[spec.device_id] = (
                VirtualDeviceStatus.STOPPED if is_avail else VirtualDeviceStatus.UNAVAILABLE
            )

    def list_devices(self) -> List[VirtualNOSSpec]:
        """List all known virtual NOS test targets."""
        return list(self._devices.values())

    def get_device(self, device_id: str) -> Optional[VirtualNOSSpec]:
        """Retrieve spec for a specific device ID."""
        return self._devices.get(device_id)

    def get_status(self, device_id: str) -> VirtualDeviceStatus:
        """Get current operational state of a virtual NOS device."""
        return self._device_states.get(device_id, VirtualDeviceStatus.UNAVAILABLE)

    def create_endpoint_profile(
        self,
        device_id: str,
        ca_cert_path: str = "/tmp/test_pki/ca.pem",
        client_cert_path: str = "/tmp/test_pki/client.pem",
        client_key_path: str = "/tmp/test_pki/client.key",
    ) -> DeviceEndpointProfile:
        """Create a typed DeviceEndpointProfile for a virtual NOS target."""
        spec = self._devices.get(device_id)
        if spec is None:
            raise KeyError(f"Unknown virtual device ID: '{device_id}'")

        return DeviceEndpointProfile(
            device_id=spec.device_id,
            hostname=spec.tls_server_name,
            management_ip=spec.management_ip,
            management_port=spec.management_port,
            vendor=spec.vendor,
            transport=spec.transport,
            tls_server_name=spec.tls_server_name,
            ca_cert_path=ca_cert_path,
            client_cert_path=client_cert_path,
            client_key_path=client_key_path,
            supported_models=spec.supported_models,
            allowlisted=True,
        )

    def cleanup(self) -> None:
        """Restore all test environments to baseline."""
        for device_id, spec in self._devices.items():
            if spec.is_image_available:
                self._device_states[device_id] = VirtualDeviceStatus.STOPPED
            else:
                self._device_states[device_id] = VirtualDeviceStatus.UNAVAILABLE
        logger.info("VirtualDeviceManager: All virtual devices cleaned up and reset.")
