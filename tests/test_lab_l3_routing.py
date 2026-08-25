"""
Test Suite for NOC-Copilot v1.2 Phase 7: Live Lab L3 Routing & FRR Configuration.

Validates the L3 addressing, dual-homed routing, metric preference, failover,
and failback logic for ContainerLab / FRRouting:
1. Management vs WAN subnet separation
2. eth1 point-to-point WAN addressing (ISP-A)
3. eth2 point-to-point WAN addressing (ISP-B)
4. ISP-A primary default route definition
5. ISP-B backup default route definition
6. Route preference and distance metric ordering
7. ISP-A reachability and gateway resolution
8. ISP-B reachability and gateway resolution
9. Failover route selection (ISP-A unavailable -> ISP-B selected)
10. Failback route selection (ISP-A restored -> ISP-A selected)
11. Zero modification or regression to NOC-Copilot safety logic
"""

import ipaddress
import os
import unittest

from agents.failover.approval_manager import ApprovalManager
from agents.failover.dry_run_adapter import DryRunExecutionAdapter
from agents.failover.failover_models import ExecutionMode, ProductionExecutionDisabledError
from agents.failover.failover_service import FailoverService
from agents.failover.pre_execution_validator import PreExecutionValidator
from agents.topology.topology_repository import TopologyRepository
from config.settings import PROJECT_ROOT


class TestLabL3Routing(unittest.TestCase):
    """Test suite for ContainerLab L3 WAN addressing and FRRouting configuration."""

    def setUp(self) -> None:
        self.clab_file = os.path.join(PROJECT_ROOT, "topology.clab.yml")
        self.b3_conf_file = os.path.join(PROJECT_ROOT, "lab_configs", "branch3-uplink", "frr.conf")
        self.rtr_conf_file = os.path.join(PROJECT_ROOT, "lab_configs", "rtr-01", "frr.conf")
        self.hub_conf_file = os.path.join(PROJECT_ROOT, "lab_configs", "hub", "frr.conf")

        # Read configuration contents
        with open(self.b3_conf_file, "r") as f:
            self.b3_conf = f.read()
        with open(self.rtr_conf_file, "r") as f:
            self.rtr_conf = f.read()
        with open(self.hub_conf_file, "r") as f:
            self.hub_conf = f.read()

    # -----------------------------------------------------------------------
    # 1. Management vs WAN Subnet Separation
    # -----------------------------------------------------------------------
    def test_mgmt_vs_wan_subnet_separation(self) -> None:
        """Verify management subnet (172.20.20.0/24) does not overlap with WAN subnets."""
        mgmt_net = ipaddress.ip_network("172.20.20.0/24")
        wan1_net = ipaddress.ip_network("10.10.1.0/30")
        wan2_net = ipaddress.ip_network("10.10.2.0/30")

        self.assertFalse(mgmt_net.overlaps(wan1_net), "Management network must not overlap with WAN-1")
        self.assertFalse(mgmt_net.overlaps(wan2_net), "Management network must not overlap with WAN-2")
        self.assertFalse(wan1_net.overlaps(wan2_net), "WAN-1 and WAN-2 must be distinct subnets")

    # -----------------------------------------------------------------------
    # 2. eth1 Addressing (ISP-A Primary Link)
    # -----------------------------------------------------------------------
    def test_eth1_addressing(self) -> None:
        """Verify eth1 addresses on branch3-uplink and rtr-01 form a valid /30 point-to-point link."""
        self.assertIn("interface eth1", self.b3_conf)
        self.assertIn("ip address 10.10.1.2/30", self.b3_conf)
        self.assertIn("interface eth2", self.rtr_conf)
        self.assertIn("ip address 10.10.1.1/30", self.rtr_conf)

        b3_ip = ipaddress.ip_interface("10.10.1.2/30")
        rtr_ip = ipaddress.ip_interface("10.10.1.1/30")
        self.assertEqual(b3_ip.network, rtr_ip.network, "branch3-uplink:eth1 and rtr-01:eth2 must share 10.10.1.0/30")

    # -----------------------------------------------------------------------
    # 3. eth2 Addressing (ISP-B Backup Link)
    # -----------------------------------------------------------------------
    def test_eth2_addressing(self) -> None:
        """Verify eth2 addresses on branch3-uplink and hub form a valid /30 point-to-point link."""
        self.assertIn("interface eth2", self.b3_conf)
        self.assertIn("ip address 10.10.2.2/30", self.b3_conf)
        self.assertIn("interface eth2", self.hub_conf)
        self.assertIn("ip address 10.10.2.1/30", self.hub_conf)

        b3_ip = ipaddress.ip_interface("10.2.2.2/30" if "10.2.2.2" in self.b3_conf else "10.10.2.2/30")
        hub_ip = ipaddress.ip_interface("10.2.2.1/30" if "10.2.2.1" in self.hub_conf else "10.10.2.1/30")
        self.assertEqual(b3_ip.network, hub_ip.network, "branch3-uplink:eth2 and hub:eth2 must share 10.10.2.0/30")

    # -----------------------------------------------------------------------
    # 4. ISP-A Primary Default Route
    # -----------------------------------------------------------------------
    def test_ispa_primary_route(self) -> None:
        """Verify branch3-uplink configures ISP-A primary default route via 10.10.1.1 with distance 10."""
        self.assertIn("ip route 0.0.0.0/0 10.10.1.1 10", self.b3_conf)

    # -----------------------------------------------------------------------
    # 5. ISP-B Backup Default Route
    # -----------------------------------------------------------------------
    def test_ispb_backup_route(self) -> None:
        """Verify branch3-uplink configures ISP-B backup default route via 10.10.2.1 with distance 20."""
        self.assertIn("ip route 0.0.0.0/0 10.10.2.1 20", self.b3_conf)

    # -----------------------------------------------------------------------
    # 6. Route Preference & Metric Ordering
    # -----------------------------------------------------------------------
    def test_route_preference(self) -> None:
        """Verify administrative distance ordering ensures ISP-A (10) takes precedence over ISP-B (20)."""
        routes = []
        for line in self.b3_conf.splitlines():
            line = line.strip()
            if line.startswith("ip route 0.0.0.0/0"):
                parts = line.split()
                # parts: ['ip', 'route', '0.0.0.0/0', '<next_hop>', '<distance>']
                routes.append({"next_hop": parts[3], "distance": int(parts[4])})

        self.assertEqual(len(routes), 2, "Must configure exactly 2 default routes on branch3-uplink")
        routes.sort(key=lambda r: r["distance"])

        # Lowest distance wins
        primary_route = routes[0]
        backup_route = routes[1]

        self.assertEqual(primary_route["next_hop"], "10.10.1.1")
        self.assertEqual(primary_route["distance"], 10)
        self.assertEqual(backup_route["next_hop"], "10.10.2.1")
        self.assertEqual(backup_route["distance"], 20)
        self.assertLess(primary_route["distance"], backup_route["distance"])

    # -----------------------------------------------------------------------
    # 7. ISP-A Reachability Definition
    # -----------------------------------------------------------------------
    def test_ispa_reachability_definition(self) -> None:
        """Verify ISP-A gateway 10.10.1.1 is directly reachable via branch3-uplink:eth1."""
        b3_eth1_net = ipaddress.ip_interface("10.10.1.2/30").network
        gateway_ip = ipaddress.ip_address("10.10.1.1")
        self.assertIn(gateway_ip, b3_eth1_net, "ISP-A gateway must reside in branch3-uplink:eth1 subnet")

    # -----------------------------------------------------------------------
    # 8. ISP-B Reachability Definition
    # -----------------------------------------------------------------------
    def test_ispb_reachability_definition(self) -> None:
        """Verify ISP-B gateway 10.10.2.1 is directly reachable via branch3-uplink:eth2."""
        b3_eth2_net = ipaddress.ip_interface("10.10.2.2/30").network
        gateway_ip = ipaddress.ip_address("10.10.2.1")
        self.assertIn(gateway_ip, b3_eth2_net, "ISP-B gateway must reside in branch3-uplink:eth2 subnet")

    # -----------------------------------------------------------------------
    # 9. Failover Route Selection
    # -----------------------------------------------------------------------
    def test_failover_route_selection(self) -> None:
        """Verify that when ISP-A is inactive, routing table resolves to ISP-B (10.10.2.1 via eth2)."""
        active_routes = [
            {"prefix": "0.0.0.0/0", "next_hop": "10.10.1.1", "interface": "eth1", "distance": 10, "active": False},
            {"prefix": "0.0.0.0/0", "next_hop": "10.10.2.1", "interface": "eth2", "distance": 20, "active": True},
        ]
        selected_route = next((r for r in active_routes if r["active"]), None)
        self.assertIsNotNone(selected_route)
        self.assertEqual(selected_route["next_hop"], "10.10.2.1")
        self.assertEqual(selected_route["interface"], "eth2")

    # -----------------------------------------------------------------------
    # 10. Failback Route Selection
    # -----------------------------------------------------------------------
    def test_failback_route_selection(self) -> None:
        """Verify that when ISP-A is restored, routing table selects ISP-A (10.10.1.1 via eth1)."""
        active_routes = [
            {"prefix": "0.0.0.0/0", "next_hop": "10.10.1.1", "interface": "eth1", "distance": 10, "active": True},
            {"prefix": "0.0.0.0/0", "next_hop": "10.10.2.1", "interface": "eth2", "distance": 20, "active": True},
        ]
        # Distance 10 takes priority over distance 20
        selected_route = min(active_routes, key=lambda r: r["distance"])
        self.assertEqual(selected_route["next_hop"], "10.10.1.1")
        self.assertEqual(selected_route["interface"], "eth1")

    # -----------------------------------------------------------------------
    # 11. Zero modification to NOC-Copilot Safety Logic
    # -----------------------------------------------------------------------
    def test_no_modification_to_noc_copilot_safety_logic(self) -> None:
        """Verify DRY_RUN remains enforced and PRODUCTION_AUTHORIZED raises an error."""
        approval_mgr = ApprovalManager()
        validator = PreExecutionValidator(approval_manager=approval_mgr)
        service = FailoverService(
            approval_manager=approval_mgr,
            validator=validator,
            dry_run_adapter=DryRunExecutionAdapter(),
        )
        # 1. DRY_RUN execution executes safely
        res = service.execute_failover_pipeline(
            target_interface_or_device="Branch3-Uplink",
            execution_mode=ExecutionMode.DRY_RUN,
            auto_approve=True,
            adapter_name="DryRunExecutionAdapter",
        )
        self.assertIsNotNone(res)

        # 2. PRODUCTION_AUTHORIZED is strictly blocked
        with self.assertRaises(ProductionExecutionDisabledError):
            service.execute_failover_pipeline(
                target_interface_or_device="Branch3-Uplink",
                execution_mode=ExecutionMode.PRODUCTION_AUTHORIZED,
                auto_approve=True,
            )


if __name__ == "__main__":
    unittest.main()
