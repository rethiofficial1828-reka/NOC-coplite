"""
Topology Repository Module.

Thread-safe repository responsible for loading, normalising, and caching
network topology from all supported sources:

    1. topology.clab.yml  — ContainerLab YAML topology definition
    2. DEVICE_REGISTRY    — config/settings.py device registry list
    3. JSON topology files — future-compatible extension point

The repository caches the parsed graph and automatically reloads when the
source file changes (inode mtime comparison).  All public methods are
thread-safe.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, List, Optional, Tuple

from agents.core.logger import get_agent_logger
from agents.topology.topology_graph import TopologyGraph
from agents.topology.topology_models import (
    LinkState,
    NodeRole,
    TopologyInterface,
    TopologyLink,
    TopologyNode,
    TopologyStatistics,
)

logger = get_agent_logger("TopologyRepository")

# ---------------------------------------------------------------------------
# YAML is optional; gracefully degrade if PyYAML is not installed.
# ---------------------------------------------------------------------------
try:
    import yaml as _yaml  # type: ignore[import]

    _YAML_AVAILABLE = True
except ImportError:  # pragma: no cover
    _YAML_AVAILABLE = False
    logger.warning("PyYAML not installed — topology.clab.yml loading disabled.")


class TopologyRepository:
    """
    Thread-safe repository for loading and caching network topology graphs.

    Responsibilities:
        - Parse topology.clab.yml (ContainerLab format) when present.
        - Supplement with DEVICE_REGISTRY entries from config/settings.
        - Merge both sources into a unified TopologyGraph.
        - Cache the graph and invalidate on file modification.
        - Expose raw node/link lists for the validator and service layers.

    Args:
        topology_file: Absolute path to topology.clab.yml.
                       Defaults to <project_root>/topology.clab.yml.
        device_registry: Optional device registry list.
                         Defaults to config.settings.DEVICE_REGISTRY.
    """

    def __init__(
        self,
        topology_file: Optional[str] = None,
        device_registry: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self._lock = threading.RLock()

        # Resolve topology file path
        if topology_file is not None:
            self._topology_file = topology_file
        else:
            project_root = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            self._topology_file = os.path.join(project_root, "topology.clab.yml")

        # Resolve device registry
        if device_registry is not None:
            self._device_registry = device_registry
        else:
            try:
                from config import settings  # type: ignore[import]

                self._device_registry = list(settings.DEVICE_REGISTRY)
            except Exception:
                self._device_registry = []
                logger.warning("Could not import DEVICE_REGISTRY from config.settings.")

        # Cache state
        self._graph: Optional[TopologyGraph] = None
        self._nodes: List[TopologyNode] = []
        self._links: List[TopologyLink] = []
        self._last_mtime: float = 0.0
        self._statistics: Optional[TopologyStatistics] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_graph(self) -> TopologyGraph:
        """
        Return the cached TopologyGraph, reloading if the source file changed.

        Returns:
            TopologyGraph instance populated with current topology.
        """
        with self._lock:
            current_mtime = self._get_file_mtime()
            if self._graph is None or current_mtime != self._last_mtime:
                self._load_topology()
            return self._graph  # type: ignore[return-value]

    def get_all_nodes(self) -> List[TopologyNode]:
        """Return all normalised topology nodes."""
        self.get_graph()  # ensure cache is warm
        with self._lock:
            return list(self._nodes)

    def get_all_links(self) -> List[TopologyLink]:
        """Return all normalised topology links."""
        self.get_graph()
        with self._lock:
            return list(self._links)

    def get_node(self, node_id: str) -> Optional[TopologyNode]:
        """
        Find a single topology node by its ID.

        Args:
            node_id: Node identifier to look up.

        Returns:
            TopologyNode or None if not found.
        """
        graph = self.get_graph()
        return graph.get_node(node_id)

    def find_node_by_name(self, name: str) -> Optional[TopologyNode]:
        """
        Find a topology node by its human-readable name (case-insensitive).

        Args:
            name: Device name to search for.

        Returns:
            TopologyNode or None.
        """
        name_lower = name.lower()
        for node in self.get_all_nodes():
            if node.name.lower() == name_lower or node.node_id.lower() == name_lower:
                return node
        return None

    def get_statistics(self) -> TopologyStatistics:
        """
        Return aggregated topology statistics.

        Returns:
            TopologyStatistics model populated from the current graph.
        """
        graph = self.get_graph()
        with self._lock:
            if self._statistics is not None:
                return self._statistics

            all_nodes = graph.get_all_nodes()
            all_links = graph.get_all_links()

            active_count = sum(1 for n in all_nodes if n.is_active)
            all_services: set[str] = set()
            for node in all_nodes:
                all_services.update(node.services)

            degrees: Dict[str, int] = {}
            for link in all_links:
                degrees[link.source_node_id] = (
                    degrees.get(link.source_node_id, 0) + 1
                )
                degrees[link.target_node_id] = (
                    degrees.get(link.target_node_id, 0) + 1
                )
            isolated = sum(
                1 for n in all_nodes if degrees.get(n.node_id, 0) == 0
            )
            avg_degree = (
                sum(degrees.values()) / len(all_nodes) if all_nodes else 0.0
            )

            spof_ids = graph.find_single_points_of_failure()

            import datetime

            self._statistics = TopologyStatistics(
                total_nodes=len(all_nodes),
                total_links=len(all_links),
                total_services=len(all_services),
                active_nodes=active_count,
                isolated_nodes=isolated,
                single_points_of_failure=len(spof_ids),
                average_node_degree=round(avg_degree, 2),
                topology_source=self._topology_file,
                last_loaded_at=datetime.datetime.now(datetime.timezone.utc),
            )
            return self._statistics

    def reload(self) -> None:
        """Force an immediate topology reload, bypassing the mtime cache."""
        with self._lock:
            self._last_mtime = 0.0
            self._graph = None
            self._statistics = None
        self.get_graph()

    # ------------------------------------------------------------------
    # Internal loading pipeline
    # ------------------------------------------------------------------

    def _load_topology(self) -> None:
        """
        Full topology load pipeline: parse YAML, merge device registry,
        build TopologyGraph, and update cache.
        """
        logger.info(
            "Loading topology from '%s' and device registry (%d entries).",
            self._topology_file,
            len(self._device_registry),
        )

        nodes: Dict[str, TopologyNode] = {}
        links: List[TopologyLink] = []

        # Step 1: Load from ContainerLab YAML
        if _YAML_AVAILABLE and os.path.isfile(self._topology_file):
            clab_nodes, clab_links = self._parse_clab_yaml(self._topology_file)
            for n in clab_nodes:
                nodes[n.node_id] = n
            links.extend(clab_links)
        else:
            if not os.path.isfile(self._topology_file):
                logger.warning(
                    "topology.clab.yml not found at '%s'; using device registry only.",
                    self._topology_file,
                )

        # Step 2: Supplement with DEVICE_REGISTRY (add missing nodes)
        registry_nodes = self._parse_device_registry()
        for n in registry_nodes:
            if n.node_id not in nodes:
                nodes[n.node_id] = n
            else:
                # Enrich existing node with registry metadata
                existing = nodes[n.node_id]
                if not existing.location and n.location:
                    existing.location = n.location
                if not existing.device_type and n.device_type:
                    existing.device_type = n.device_type

        all_nodes = list(nodes.values())
        self._nodes = all_nodes
        self._links = links
        self._graph = TopologyGraph(nodes=all_nodes, links=links)
        self._last_mtime = self._get_file_mtime()
        self._statistics = None  # invalidate cached statistics

        logger.info(
            "Topology loaded: %d nodes, %d links.",
            len(all_nodes),
            len(links),
        )

    def _parse_clab_yaml(
        self, filepath: str
    ) -> Tuple[List[TopologyNode], List[TopologyLink]]:
        """
        Parse a ContainerLab YAML file into TopologyNode and TopologyLink lists.

        ContainerLab topology format (relevant subset):
            topology:
              nodes:
                <name>:
                  kind: ...
                  mgmt-ipv4: ...
              links:
                - endpoints:
                    - "<node>:<interface>"
                    - "<node>:<interface>"

        Args:
            filepath: Absolute path to the YAML file.

        Returns:
            Tuple of (nodes, links).
        """
        nodes: List[TopologyNode] = []
        links: List[TopologyLink] = []

        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                raw = _yaml.safe_load(fh)
        except Exception as exc:
            logger.error("Failed to parse '%s': %s", filepath, exc, exc_info=True)
            return nodes, links

        if not isinstance(raw, dict):
            logger.warning("Unexpected YAML structure in '%s'.", filepath)
            return nodes, links

        topology_section = raw.get("topology", {}) or {}

        # --- Nodes ---
        raw_nodes: Dict[str, Any] = topology_section.get("nodes", {}) or {}
        for node_name, attrs in raw_nodes.items():
            attrs = attrs or {}
            node_id = self._normalise_id(node_name)
            role = self._infer_role(node_name, attrs)
            mgmt_ip: Optional[str] = attrs.get("mgmt-ipv4")
            kind: str = attrs.get("kind", "")

            nodes.append(
                TopologyNode(
                    node_id=node_id,
                    name=node_name,
                    role=role,
                    device_type=kind,
                    management_ip=mgmt_ip,
                    interfaces=[],
                    metadata={
                        "image": attrs.get("image", ""),
                        "kind": kind,
                        "source": "clab",
                    },
                )
            )

        # --- Links ---
        raw_links: List[Any] = topology_section.get("links", []) or []
        for link_entry in raw_links:
            if not isinstance(link_entry, dict):
                continue
            endpoints: List[str] = link_entry.get("endpoints", [])
            if len(endpoints) < 2:
                continue

            src_parts = endpoints[0].split(":", 1)
            dst_parts = endpoints[1].split(":", 1)
            if len(src_parts) < 2 or len(dst_parts) < 2:
                continue

            src_node = self._normalise_id(src_parts[0])
            src_iface = src_parts[1]
            dst_node = self._normalise_id(dst_parts[0])
            dst_iface = dst_parts[1]

            # Add interface definitions to nodes if known
            self._ensure_interface(nodes, src_node, src_iface)
            self._ensure_interface(nodes, dst_node, dst_iface)

            links.append(
                TopologyLink(
                    source_node_id=src_node,
                    source_interface=src_iface,
                    target_node_id=dst_node,
                    target_interface=dst_iface,
                    weight=1.0,
                    state=LinkState.UP,
                    metadata={"source": "clab"},
                )
            )
            # ContainerLab links are bidirectional — add reverse direction
            links.append(
                TopologyLink(
                    source_node_id=dst_node,
                    source_interface=dst_iface,
                    target_node_id=src_node,
                    target_interface=src_iface,
                    weight=1.0,
                    state=LinkState.UP,
                    metadata={"source": "clab", "reverse": True},
                )
            )

        return nodes, links

    def _parse_device_registry(self) -> List[TopologyNode]:
        """
        Convert DEVICE_REGISTRY entries into TopologyNode objects.

        Returns:
            List of TopologyNode objects derived from config.settings.DEVICE_REGISTRY.
        """
        nodes: List[TopologyNode] = []
        for entry in self._device_registry:
            if not isinstance(entry, dict):
                continue
            raw_id: str = str(entry.get("id", ""))
            if not raw_id:
                continue
            node_id = self._normalise_id(raw_id)
            name: str = str(entry.get("name", raw_id))
            device_type: str = str(entry.get("type", ""))
            location: str = str(entry.get("location", ""))
            role = self._infer_role(name, {"kind": device_type})

            nodes.append(
                TopologyNode(
                    node_id=node_id,
                    name=name,
                    role=role,
                    device_type=device_type,
                    location=location,
                    interfaces=[],
                    services=[name],  # register each device as its own service
                    criticality=self._infer_criticality(role),
                    metadata={
                        "source": "device_registry",
                        "registry_id": raw_id,
                    },
                )
            )
        return nodes

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_id(raw: str) -> str:
        """Convert a raw node name into a lowercase, hyphenated identifier."""
        return raw.strip().lower().replace(" ", "-").replace("_", "-")

    @staticmethod
    def _infer_role(name: str, attrs: Dict[str, Any]) -> NodeRole:
        """Infer the NodeRole from name and attribute keywords."""
        name_lower = name.lower()
        kind_lower = str(attrs.get("kind", "")).lower()
        type_lower = str(attrs.get("type", "")).lower()
        combined = f"{name_lower} {kind_lower} {type_lower}"

        if "core" in combined:
            return NodeRole.CORE
        if "firewall" in combined or "fw" in name_lower:
            return NodeRole.FIREWALL
        if "router" in combined or "rtr" in name_lower:
            return NodeRole.ROUTER
        if "switch" in combined or "sw" in name_lower:
            return NodeRole.SWITCH
        if "wan" in combined or "uplink" in combined:
            return NodeRole.WAN_INTERFACE
        if "hub" in name_lower or "distribution" in combined:
            return NodeRole.DISTRIBUTION
        if "branch" in name_lower or "access" in combined:
            return NodeRole.ACCESS
        return NodeRole.UNKNOWN

    @staticmethod
    def _infer_criticality(role: NodeRole) -> int:
        """Assign a default criticality score based on NodeRole."""
        mapping: Dict[NodeRole, int] = {
            NodeRole.CORE: 10,
            NodeRole.FIREWALL: 9,
            NodeRole.ROUTER: 8,
            NodeRole.DISTRIBUTION: 7,
            NodeRole.WAN_INTERFACE: 7,
            NodeRole.SWITCH: 6,
            NodeRole.ACCESS: 5,
            NodeRole.EDGE: 5,
            NodeRole.ENDPOINT: 3,
            NodeRole.UNKNOWN: 5,
        }
        return mapping.get(role, 5)

    @staticmethod
    def _ensure_interface(
        nodes: List[TopologyNode], node_id: str, iface_name: str
    ) -> None:
        """Add an interface to the matching node if it does not already exist."""
        for node in nodes:
            if node.node_id == node_id:
                existing_names = {iface.name for iface in node.interfaces}
                if iface_name not in existing_names:
                    node.interfaces.append(
                        TopologyInterface(name=iface_name, state=LinkState.UP)
                    )
                return

    def _get_file_mtime(self) -> float:
        """Return the mtime of the topology file, or 0.0 if it does not exist."""
        try:
            return os.path.getmtime(self._topology_file)
        except OSError:
            return 0.0
