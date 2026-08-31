"""
Network Digital Twin Engine Module for NOC-Copilot v1.5.

Maintains an in-memory, graph-backed simulation model representing network devices,
interfaces, physical and simulated links, forwarding routes, next-hops, and WAN providers.
Supports state snapshotting, What-If provider failure simulation, link failure simulation,
failover route simulation, and blast-radius / affected component calculations without
mutating physical network state.
"""

from copy import deepcopy
from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from agents.core.logger import get_agent_logger
from agents.topology.topology_graph import TopologyGraph
from agents.topology.topology_models import LinkState, NodeRole, TopologyLink, TopologyNode
from agents.topology.topology_repository import TopologyRepository
from agents.twin.twin_models import (
    AffectedComponentsSummary,
    DeviceTwinState,
    DigitalTwinSnapshot,
    InterfaceTwinState,
    LinkTwinState,
    RouteTwinState,
    TwinSimulationResult,
    TwinSimulationScenario,
)
from config.settings import WAN_PROVIDER_REGISTRY, DEVICE_REGISTRY

logger = get_agent_logger("NetworkDigitalTwin")


class NetworkDigitalTwin:
    """
    In-memory graph-backed Digital Twin representing network topology, routes, and WAN state.
    """

    def __init__(
        self,
        repository: Optional[TopologyRepository] = None,
        wan_registry: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self._repo = repository or TopologyRepository()
        self._wan_registry = wan_registry if wan_registry is not None else list(WAN_PROVIDER_REGISTRY)
        self._lock = threading.RLock()

        self._devices: Dict[str, DeviceTwinState] = {}
        self._interfaces: Dict[str, InterfaceTwinState] = {}
        self._links: Dict[str, LinkTwinState] = {}
        self._routes: List[RouteTwinState] = []
        self._providers: Dict[str, Dict[str, Any]] = {}
        self._health_summary: Dict[str, float] = {}

        self._initialize_from_topology()

    def _initialize_from_topology(self) -> None:
        """Hydrate digital twin state from topology repository and WAN registry."""
        with self._lock:
            # 1. Load WAN Provider Registry
            for p in self._wan_registry:
                pid = p.get("provider_id", "UNKNOWN")
                self._providers[pid] = dict(p)

            # 2. Load Nodes from Topology Repository
            nodes = self._repo.get_all_nodes()
            if not nodes:
                # Build fallback standard nodes if repository is empty
                for dev in DEVICE_REGISTRY:
                    did = dev["id"]
                    self._devices[did] = DeviceTwinState(
                        device_id=did,
                        name=dev["name"],
                        role=dev.get("type", "router").lower(),
                        is_active=True,
                        health_score=100.0,
                        active_interfaces=["eth1", "eth2"],
                        services=["egress_routing", "corporate_wan"],
                        criticality=7 if "core" in did or "fw" in did else 5,
                    )
            else:
                for n in nodes:
                    ifaces = [iface.name for iface in n.interfaces]
                    self._devices[n.node_id] = DeviceTwinState(
                        device_id=n.node_id,
                        name=n.name,
                        role=n.role.value if hasattr(n.role, "value") else str(n.role),
                        is_active=n.is_active,
                        health_score=100.0,
                        active_interfaces=ifaces or ["eth1", "eth2"],
                        services=list(n.services),
                        criticality=n.criticality,
                    )

            # 3. Load Interfaces from Providers & Devices
            for pid, pdef in self._providers.items():
                sdev = pdef.get("source_device", "branch3-uplink")
                wif = pdef.get("wan_interface", "eth1")
                if_key = f"{sdev}:{wif}"
                self._interfaces[if_key] = InterfaceTwinState(
                    interface_id=if_key,
                    device_id=sdev,
                    name=wif,
                    ip_address=pdef.get("next_hop"),
                    bandwidth_mbps=pdef.get("bandwidth_mbps", 1000.0),
                    is_up=True,
                    current_provider=pid,
                    is_simulated=pdef.get("is_simulated", False),
                    utilization_percent=35.0,
                )

            # 4. Load Links from Repository
            links = self._repo.get_all_links()
            for lnk in links:
                lid = lnk.link_id
                self._links[lid] = LinkTwinState(
                    link_id=lid,
                    source_device=lnk.source_node_id,
                    source_interface=lnk.source_interface,
                    target_device=lnk.target_node_id,
                    target_interface=lnk.target_interface,
                    is_up=lnk.state == LinkState.UP,
                    weight=lnk.weight,
                    bandwidth_mbps=lnk.bandwidth_mbps or 1000.0,
                    is_redundant=lnk.is_redundant,
                    is_simulated=False,
                )

            # Add simulated links for ISP-C and ISP-D
            sim_c_id = "link-branch3-isp-c"
            self._links[sim_c_id] = LinkTwinState(
                link_id=sim_c_id,
                source_device="branch3-uplink",
                source_interface="Branch3-Cellular",
                target_device="cellular-tower",
                target_interface="cell0",
                is_up=True,
                weight=30.0,
                bandwidth_mbps=250.0,
                is_redundant=True,
                is_simulated=True,
            )

            sim_d_id = "link-branch3-isp-d"
            self._links[sim_d_id] = LinkTwinState(
                link_id=sim_d_id,
                source_device="branch3-uplink",
                source_interface="Branch3-Satellite",
                target_device="satellite-gw",
                target_interface="sat0",
                is_up=True,
                weight=50.0,
                bandwidth_mbps=100.0,
                is_redundant=True,
                is_simulated=True,
            )

            # 5. Load Initial Routes
            for p in self._wan_registry:
                pid = p["provider_id"]
                prio = p.get("priority", 1)
                dist = 10 if pid == "ISP-A" else (20 if pid == "ISP-B" else (30 if pid == "ISP-C" else 40))
                self._routes.append(
                    RouteTwinState(
                        prefix="0.0.0.0/0",
                        next_hop=p.get("next_hop", "10.10.1.1"),
                        interface=p.get("wan_interface", "Branch3-Uplink"),
                        distance=dist,
                        provider_name=pid,
                        is_active=(pid == "ISP-A"),
                        is_simulated=p.get("is_simulated", False),
                    )
                )

            # 6. Initial Health Summary
            for pid in self._providers:
                self._health_summary[pid] = 100.0
            for did in self._devices:
                self._health_summary[did] = 100.0

            logger.info(
                f"NetworkDigitalTwin initialized: {len(self._devices)} devices, "
                f"{len(self._interfaces)} interfaces, {len(self._links)} links, "
                f"{len(self._routes)} routes, {len(self._providers)} providers."
            )

    def snapshot(self) -> DigitalTwinSnapshot:
        """
        Capture an immutable DigitalTwinSnapshot representing current state.
        """
        with self._lock:
            return DigitalTwinSnapshot(
                snapshot_id=str(uuid.uuid4()),
                version="1.5.0",
                devices={k: v.model_copy() for k, v in self._devices.items()},
                interfaces={k: v.model_copy() for k, v in self._interfaces.items()},
                links={k: v.model_copy() for k, v in self._links.items()},
                routes=[r.model_copy() for r in self._routes],
                providers=deepcopy(self._providers),
                health_summary=dict(self._health_summary),
                created_at=datetime.now(timezone.utc),
            )

    def update_health(self, entity_id: str, health_score: float) -> None:
        """Update operational health score of a device or provider in the twin."""
        with self._lock:
            self._health_summary[entity_id] = max(0.0, min(100.0, health_score))
            if entity_id in self._devices:
                self._devices[entity_id].health_score = max(0.0, min(100.0, health_score))

    def simulate_provider_failure(self, provider_name: str) -> TwinSimulationResult:
        """
        Simulate total failure of a WAN provider inside the Digital Twin.
        Evaluates route failover candidates and reachability impact.
        """
        with self._lock:
            snap = self.snapshot()
            sim_id = str(uuid.uuid4())

            p_def = snap.providers.get(provider_name)
            if not p_def:
                return TwinSimulationResult(
                    simulation_id=sim_id,
                    scenario=TwinSimulationScenario.PROVIDER_FAILURE,
                    target_entity=provider_name,
                    summary=f"Provider '{provider_name}' not found in Digital Twin.",
                    impact_severity="LOW",
                )

            sdev = p_def.get("source_device", "branch3-uplink")
            wif = p_def.get("wan_interface", "Branch3-Uplink")

            # Identify surviving routes
            surviving_routes = [r for r in snap.routes if r.provider_name != provider_name]
            surviving_routes.sort(key=lambda r: r.distance)

            alt_provider = surviving_routes[0].provider_name if surviving_routes else None
            alt_nh = surviving_routes[0].next_hop if surviving_routes else None

            # Calculate affected components
            affected_nodes = [sdev]
            affected_links = [lid for lid, lnk in snap.links.items() if lnk.source_interface == wif or lnk.target_interface == wif]
            affected_services = ["wan_egress", "internet_uplink"]

            isolated_nodes: List[str] = []
            reachability: Dict[str, bool] = {}
            rerouted_paths: Dict[str, List[str]] = {}

            for did in snap.devices:
                if alt_provider:
                    reachability[did] = True
                    rerouted_paths[did] = [did, sdev, alt_provider, "Enterprise Gateway"]
                else:
                    reachability[did] = False if did == sdev else True
                    if did == sdev:
                        isolated_nodes.append(did)

            total_nodes = len(snap.devices)
            blast_pct = round((len(affected_nodes) / total_nodes) * 100.0, 1) if total_nodes > 0 else 0.0
            severity = "HIGH" if not alt_provider else ("MEDIUM" if surviving_routes[0].is_simulated else "LOW")

            summary = (
                f"Simulated failure of '{provider_name}' on '{sdev}'. "
                f"Alternative failover target: '{alt_provider}' via next-hop '{alt_nh}' "
                f"(Simulated={surviving_routes[0].is_simulated if surviving_routes else False}). "
                f"{len(isolated_nodes)} node(s) isolated."
            )

            return TwinSimulationResult(
                simulation_id=sim_id,
                scenario=TwinSimulationScenario.PROVIDER_FAILURE,
                target_entity=provider_name,
                affected_node_ids=affected_nodes,
                affected_link_ids=affected_links,
                affected_services=affected_services,
                isolated_nodes=isolated_nodes,
                rerouted_paths=rerouted_paths,
                predicted_reachability=reachability,
                impact_severity=severity,
                blast_radius_pct=blast_pct,
                summary=summary,
            )

    def simulate_link_failure(self, source_node: str, target_node: str) -> TwinSimulationResult:
        """
        Simulate link failure between source_node and target_node.
        """
        with self._lock:
            snap = self.snapshot()
            sim_id = str(uuid.uuid4())

            matched_links = [
                lid for lid, l in snap.links.items()
                if (l.source_device.lower() == source_node.lower() and l.target_device.lower() == target_node.lower())
                or (l.source_device.lower() == target_node.lower() and l.target_device.lower() == source_node.lower())
            ]

            affected_nodes = [source_node, target_node]
            affected_services: List[str] = []
            isolated_nodes: List[str] = []

            # Check if alternative path exists in topology graph
            graph = self._repo.get_graph() if hasattr(self._repo, "get_graph") else None
            spofs = graph.find_single_points_of_failure() if graph else []

            is_spof = source_node in spofs or target_node in spofs
            severity = "HIGH" if is_spof else "LOW"
            blast_pct = round((len(affected_nodes) / len(snap.devices)) * 100.0, 1) if snap.devices else 0.0

            summary = (
                f"Simulated link failure between '{source_node}' and '{target_node}'. "
                f"Impacted links: {matched_links}. Single point of failure: {is_spof}."
            )

            return TwinSimulationResult(
                simulation_id=sim_id,
                scenario=TwinSimulationScenario.LINK_FAILURE,
                target_entity=f"{source_node}<->{target_node}",
                affected_node_ids=affected_nodes,
                affected_link_ids=matched_links,
                affected_services=affected_services,
                isolated_nodes=isolated_nodes,
                rerouted_paths={source_node: [source_node, "Alternative-Core", target_node]},
                predicted_reachability={d: True for d in snap.devices},
                impact_severity=severity,
                blast_radius_pct=blast_pct,
                summary=summary,
            )

    def simulate_failover(
        self,
        source_provider: str,
        target_provider: str,
        target_device: str = "branch3-uplink",
    ) -> TwinSimulationResult:
        """
        Simulate transitioning active WAN traffic from source_provider to target_provider.
        """
        with self._lock:
            snap = self.snapshot()
            sim_id = str(uuid.uuid4())

            tgt_def = snap.providers.get(target_provider)
            is_sim = tgt_def.get("is_simulated", False) if tgt_def else False
            tgt_nh = tgt_def.get("next_hop", "UNKNOWN") if tgt_def else "UNKNOWN"
            tgt_bw = tgt_def.get("bandwidth_mbps", 1000.0) if tgt_def else 1000.0

            rerouted = {target_device: [target_device, f"{target_provider}-POP", "Enterprise Gateway"]}

            summary = (
                f"Simulated failover: '{source_provider}' -> '{target_provider}' on '{target_device}'. "
                f"Target next-hop: {tgt_nh}, Capacity: {tgt_bw:.0f} Mbps, Simulated: {is_sim}."
            )

            return TwinSimulationResult(
                simulation_id=sim_id,
                scenario=TwinSimulationScenario.FAILOVER,
                target_entity=f"{source_provider}->{target_provider}",
                affected_node_ids=[target_device],
                affected_link_ids=[f"link-{target_device}-{target_provider.lower()}"],
                affected_services=["egress_routing", "corporate_wan"],
                isolated_nodes=[],
                rerouted_paths=rerouted,
                predicted_reachability={d: True for d in snap.devices},
                impact_severity="LOW",
                blast_radius_pct=round((1.0 / len(snap.devices)) * 100.0, 1) if snap.devices else 10.0,
                summary=summary,
            )

    def get_affected_components(self, failed_entities: List[str]) -> AffectedComponentsSummary:
        """
        Compute affected nodes, downstream components, and SPOFs for a set of failing entities.
        """
        with self._lock:
            snap = self.snapshot()
            direct: Set[str] = set()
            transitive: Set[str] = set()
            services: Set[str] = set()

            graph = self._repo.get_graph() if hasattr(self._repo, "get_graph") else None
            for ent in failed_entities:
                direct.add(ent)
                if graph:
                    downstream = graph.get_downstream(ent)
                    transitive.update(downstream)
                if ent in snap.devices:
                    services.update(snap.devices[ent].services)

            spofs = graph.find_single_points_of_failure() if graph else []
            exposed_spofs = [s for s in spofs if s in direct or s in transitive]

            total_nodes = len(snap.devices)
            all_affected = direct | transitive
            impact_score = round((len(all_affected) / total_nodes) * 100.0, 1) if total_nodes > 0 else 0.0

            return AffectedComponentsSummary(
                origin_entity=",".join(failed_entities),
                directly_affected=sorted(direct),
                transitively_affected=sorted(transitive),
                affected_services=sorted(services),
                single_points_of_failure=sorted(exposed_spofs),
                impact_score=impact_score,
            )
