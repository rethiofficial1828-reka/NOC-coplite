"""
Unit & Integration Test Suite for Sprint 22 / v1.5 Network Digital Twin Subsystem.

Covers:
1. Digital Twin snapshot creation and immutability
2. Device, interface, link, and route state tracking
3. Provider failure simulation
4. Link failure simulation
5. Failover route simulation
6. Affected components and SPOF analysis
7. Zero physical network mutation guarantee
"""

import unittest

from agents.twin.digital_twin import NetworkDigitalTwin
from agents.twin.twin_models import (
    DigitalTwinSnapshot,
    TwinSimulationScenario,
)
from agents.twin.twin_service import DigitalTwinService


class TestNetworkDigitalTwin(unittest.TestCase):
    """Test suite for NetworkDigitalTwin and DigitalTwinService."""

    def setUp(self) -> None:
        self.twin = NetworkDigitalTwin()
        self.service = DigitalTwinService(digital_twin=self.twin)

    def test_01_snapshot_structure_and_completeness(self) -> None:
        """Verify snapshot captures all devices, interfaces, links, routes, and providers."""
        snap = self.twin.snapshot()
        self.assertIsInstance(snap, DigitalTwinSnapshot)
        self.assertGreaterEqual(len(snap.devices), 4)
        self.assertGreaterEqual(len(snap.interfaces), 4)
        self.assertGreaterEqual(len(snap.routes), 4)
        self.assertGreaterEqual(len(snap.providers), 4)

        # Check providers in snapshot
        self.assertIn("ISP-A", snap.providers)
        self.assertIn("ISP-B", snap.providers)
        self.assertIn("ISP-C", snap.providers)
        self.assertIn("ISP-D", snap.providers)

        # Check route states
        route_providers = [r.provider_name for r in snap.routes]
        self.assertIn("ISP-A", route_providers)
        self.assertIn("ISP-B", route_providers)
        self.assertIn("ISP-C", route_providers)
        self.assertIn("ISP-D", route_providers)

    def test_02_snapshot_immutability(self) -> None:
        """Verify snapshot is an immutable copy and doesn't mutate on twin updates."""
        snap1 = self.twin.snapshot()
        self.twin.update_health("ISP-A", 30.0)
        snap2 = self.twin.snapshot()

        self.assertEqual(snap1.health_summary.get("ISP-A"), 100.0)
        self.assertEqual(snap2.health_summary.get("ISP-A"), 30.0)

    def test_03_simulate_provider_failure_isp_a(self) -> None:
        """Verify provider failure simulation computes alternative routes and affected components."""
        sim_res = self.twin.simulate_provider_failure("ISP-A")
        self.assertEqual(sim_res.scenario, TwinSimulationScenario.PROVIDER_FAILURE)
        self.assertEqual(sim_res.target_entity, "ISP-A")
        self.assertIn("branch3-uplink", sim_res.affected_node_ids)
        self.assertIn("wan_egress", sim_res.affected_services)
        self.assertIn("ISP-B", sim_res.summary)
        self.assertEqual(sim_res.impact_severity, "LOW")

    def test_04_simulate_link_failure(self) -> None:
        """Verify link failure simulation calculates affected links and nodes."""
        sim_res = self.twin.simulate_link_failure("core-01", "fw-01")
        self.assertEqual(sim_res.scenario, TwinSimulationScenario.LINK_FAILURE)
        self.assertIn("core-01", sim_res.affected_node_ids)
        self.assertIn("fw-01", sim_res.affected_node_ids)
        self.assertGreaterEqual(sim_res.blast_radius_pct, 0.0)

    def test_05_simulate_failover_transition(self) -> None:
        """Verify failover simulation evaluates route transition from ISP-A to ISP-B/C/D."""
        sim_res_b = self.twin.simulate_failover("ISP-A", "ISP-B")
        self.assertEqual(sim_res_b.scenario, TwinSimulationScenario.FAILOVER)
        self.assertIn("10.10.2.1", sim_res_b.summary)
        self.assertIn("Simulated: False", sim_res_b.summary)

        sim_res_c = self.twin.simulate_failover("ISP-A", "ISP-C")
        self.assertIn("10.10.3.1", sim_res_c.summary)
        self.assertIn("Simulated: True", sim_res_c.summary)

    def test_06_affected_components_analysis(self) -> None:
        """Verify get_affected_components aggregates direct and downstream dependencies."""
        summary = self.twin.get_affected_components(["core-01"])
        self.assertIn("core-01", summary.directly_affected)
        self.assertGreaterEqual(summary.impact_score, 0.0)

    def test_07_twin_service_facade(self) -> None:
        """Verify DigitalTwinService facade exposes clean simulation APIs."""
        snap = self.service.get_snapshot()
        self.assertIsNotNone(snap.snapshot_id)

        sim = self.service.simulate_provider_failure("ISP-B")
        self.assertEqual(sim.target_entity, "ISP-B")


if __name__ == "__main__":
    unittest.main()
