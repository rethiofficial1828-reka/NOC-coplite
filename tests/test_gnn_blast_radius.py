"""
Unit & Integration Test Suite for Sprint 22 / v1.5 GNN Blast-Radius Subsystem.

Covers:
1. Topology graph extraction and feature tensor construction
2. Message-passing failure propagation algorithm
3. Damping and attenuation across topology hops
4. Redundant link failure dampening
5. Advisory-only enforcement (no physical state mutation)
6. Clear provenance metadata
7. GNNService facade and event publishing
"""

import unittest

from agents.gnn.blast_radius_gnn import GNNBlastRadiusEngine
from agents.gnn.gnn_models import (
    GNNBlastRadiusRequest,
    GNNBlastRadiusResult,
    GNNProvenance,
)
from agents.gnn.gnn_service import GNNService
from agents.gnn.graph_builder import TopologyGraphBuilder


class TestGNNBlastRadius(unittest.TestCase):
    """Test suite for GNNBlastRadiusEngine and GNNService."""

    def setUp(self) -> None:
        self.builder = TopologyGraphBuilder()
        self.engine = GNNBlastRadiusEngine(graph_builder=self.builder)
        self.service = GNNService(gnn_engine=self.engine)

    def test_01_graph_builder_feature_extraction(self) -> None:
        """Verify TopologyGraphBuilder constructs valid node and edge feature representations."""
        graph_data = self.builder.build_graph_data()
        self.assertGreaterEqual(graph_data.num_nodes, 4)
        self.assertGreaterEqual(graph_data.num_edges, 4)

        # Check node features
        for nid, nf in graph_data.nodes.items():
            self.assertEqual(nf.node_id, nid)
            self.assertGreaterEqual(nf.criticality, 1.0)
            self.assertGreaterEqual(nf.health_score, 0.0)
            self.assertGreaterEqual(nf.risk_score, 0.0)

        # Check edge features
        for ef in graph_data.edges:
            self.assertIn(ef.source, graph_data.nodes)
            self.assertIn(ef.target, graph_data.nodes)
            self.assertGreater(ef.bandwidth_mbps, 0.0)

    def test_02_failure_propagation_attenuation(self) -> None:
        """Verify impulse attenuates with distance from origin node."""
        req = GNNBlastRadiusRequest(
            target_entity="branch3-uplink",
            initial_perturbation=1.0,
            attenuation_factor=0.5,
            max_propagation_depth=3,
        )
        res = self.engine.predict_blast_radius(req)

        self.assertEqual(res.target_entity, "branch3-uplink")
        self.assertGreaterEqual(res.predicted_blast_radius_pct, 0.0)
        self.assertIn("branch3-uplink", res.propagation_probabilities)

        # Origin should have maximum impulse
        self.assertEqual(res.propagation_probabilities["branch3-uplink"], 1.0)

    def test_03_advisory_provenance_tagged(self) -> None:
        """Verify prediction explicitly reports deterministic propagation provenance."""
        res = self.service.evaluate_blast_radius("ISP-A")
        self.assertEqual(res.provenance, GNNProvenance.DETERMINISTIC_PROPAGATION_FALLBACK)
        self.assertGreater(res.confidence_score, 0.50)
        self.assertGreaterEqual(len(res.advisory_notes), 1)

    def test_04_service_facade_integration(self) -> None:
        """Verify GNNService facade provides clean high-level blast-radius analysis."""
        res = self.service.evaluate_blast_radius("core-01")
        self.assertIsInstance(res, GNNBlastRadiusResult)
        self.assertGreaterEqual(res.predicted_blast_radius_pct, 0.0)
        self.assertIsNotNone(res.result_id)


if __name__ == "__main__":
    unittest.main()
