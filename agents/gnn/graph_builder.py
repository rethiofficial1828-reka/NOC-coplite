"""
Topology Graph Builder Module for NOC-Copilot GNN Blast-Radius Subsystem.

Extracts nodes, interfaces, and links from TopologyRepository and constructs
structured GNNGraphData with normalized node and edge feature vectors.
"""

from typing import Dict, List, Optional

from agents.core.logger import get_agent_logger
from agents.gnn.gnn_models import GNNEdgeFeatures, GNNGraphData, GNNNodeFeatures
from agents.topology.topology_repository import TopologyRepository
from config.settings import DEVICE_REGISTRY

logger = get_agent_logger("TopologyGraphBuilder")

ROLE_MAP = {
    "router": 0,
    "wan_interface": 0,
    "core": 1,
    "firewall": 2,
    "hub": 3,
    "switch": 0,
}


class TopologyGraphBuilder:
    """
    Constructs GNN-compatible graph feature representations from live network topology.
    """

    def __init__(self, repository: Optional[TopologyRepository] = None) -> None:
        self._repo = repository or TopologyRepository()

    def build_graph_data(self, risk_overrides: Optional[Dict[str, float]] = None) -> GNNGraphData:
        """
        Extract topology nodes and links and format into GNNGraphData.
        """
        risks = risk_overrides or {}
        nodes: Dict[str, GNNNodeFeatures] = {}
        edges: List[GNNEdgeFeatures] = []

        # 1. Ingest Nodes
        raw_nodes = self._repo.get_all_nodes()
        if not raw_nodes:
            for dev in DEVICE_REGISTRY:
                did = dev["id"]
                nodes[did] = GNNNodeFeatures(
                    node_id=did,
                    role_idx=ROLE_MAP.get(dev.get("type", "router").lower(), 0),
                    criticality=7.0 if "core" in did or "fw" in did else 5.0,
                    health_score=100.0,
                    degree=2,
                    risk_score=risks.get(did, 0.05),
                )
        else:
            for n in raw_nodes:
                role_str = n.role.value if hasattr(n.role, "value") else str(n.role)
                nodes[n.node_id] = GNNNodeFeatures(
                    node_id=n.node_id,
                    role_idx=ROLE_MAP.get(role_str.lower(), 0),
                    criticality=float(n.criticality),
                    health_score=100.0,
                    degree=len(n.interfaces) if n.interfaces else 2,
                    risk_score=risks.get(n.node_id, 0.05),
                )

        # 2. Ingest Links
        raw_links = self._repo.get_all_links()
        for l in raw_links:
            edges.append(
                GNNEdgeFeatures(
                    source=l.source_node_id,
                    target=l.target_node_id,
                    bandwidth_mbps=l.bandwidth_mbps or 1000.0,
                    utilization_percent=35.0,
                    is_redundant=l.is_redundant,
                    weight=l.weight,
                )
            )
            # Add reverse edge for undirected topology evaluation
            edges.append(
                GNNEdgeFeatures(
                    source=l.target_node_id,
                    target=l.source_node_id,
                    bandwidth_mbps=l.bandwidth_mbps or 1000.0,
                    utilization_percent=35.0,
                    is_redundant=l.is_redundant,
                    weight=l.weight,
                )
            )

        logger.debug(f"TopologyGraphBuilder created graph: {len(nodes)} nodes, {len(edges)} edges.")
        return GNNGraphData(
            nodes=nodes,
            edges=edges,
            num_nodes=len(nodes),
            num_edges=len(edges),
        )
