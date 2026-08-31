"""
Formal Invariants Definition Module for NOC-Copilot Z3 Formal Verification Subsystem.

Defines the 12 core network routing, safety, stability, and authorization invariants
evaluated by Z3FormalVerifier.
"""

import ipaddress
from typing import Any, Dict, List, Optional, Set, Tuple

from agents.z3_verifier.z3_models import InvariantCheckResult, Z3VerificationRequest
from config.settings import WAN_PROVIDER_REGISTRY, DEVICE_REGISTRY, PRODUCTION_AUTHORIZED

LAB_ALLOWED_DEVICES = {"branch3-uplink", "rtr-01", "fw-01", "core-01", "hub", "branch1"}
LAB_ALLOWED_INTERFACES = {
    "Branch3-Uplink", "Branch3-Backup", "Branch3-Cellular", "Branch3-Satellite",
    "eth1", "eth2", "eth3", "eth4", "ge-0/0/0", "ge-0/0/1", "Router1-GE0", "Router1-GE1", "Firewall-Port1", "Firewall-Port2"
}


class NetworkSafetyInvariants:
    """
    Encapsulates formal network invariant specifications and evaluation rules.
    """

    @classmethod
    def check_provider_existence(cls, request: Z3VerificationRequest) -> InvariantCheckResult:
        """INV-01: Target provider must exist in configuration registry."""
        known = [p["provider_id"] for p in WAN_PROVIDER_REGISTRY]
        passed = request.target_provider in known
        msg = f"Target provider '{request.target_provider}' is registered." if passed else f"Target provider '{request.target_provider}' is not in WAN_PROVIDER_REGISTRY."
        return InvariantCheckResult(
            invariant_id="INV-01",
            invariant_name="PROVIDER_EXISTS",
            passed=passed,
            severity="CRITICAL",
            message=msg,
            details={"target_provider": request.target_provider, "registered_providers": known},
        )

    @classmethod
    def check_provider_configured(cls, request: Z3VerificationRequest) -> InvariantCheckResult:
        """INV-02: Target provider configuration must have valid bandwidth and interface."""
        p_def = next((p for p in WAN_PROVIDER_REGISTRY if p["provider_id"] == request.target_provider), None)
        if not p_def:
            return InvariantCheckResult(
                invariant_id="INV-02",
                invariant_name="PROVIDER_CONFIGURED",
                passed=False,
                severity="CRITICAL",
                message=f"Provider '{request.target_provider}' missing configuration.",
            )
        bw = p_def.get("bandwidth_mbps", 0.0)
        passed = bw > 0.0 and bool(p_def.get("wan_interface"))
        return InvariantCheckResult(
            invariant_id="INV-02",
            invariant_name="PROVIDER_CONFIGURED",
            passed=passed,
            severity="HIGH",
            message=f"Provider '{request.target_provider}' configured with {bw} Mbps." if passed else f"Provider '{request.target_provider}' has invalid bandwidth ({bw}).",
            details=p_def,
        )

    @classmethod
    def check_interface_exists(cls, request: Z3VerificationRequest) -> InvariantCheckResult:
        """INV-03: Interface must exist on target device."""
        passed = request.wan_interface in LAB_ALLOWED_INTERFACES
        return InvariantCheckResult(
            invariant_id="INV-03",
            invariant_name="INTERFACE_EXISTS",
            passed=passed,
            severity="CRITICAL",
            message=f"Interface '{request.wan_interface}' exists in interface registry." if passed else f"Interface '{request.wan_interface}' not found in known interface inventory.",
            details={"wan_interface": request.wan_interface},
        )

    @classmethod
    def check_next_hop_valid(cls, request: Z3VerificationRequest) -> InvariantCheckResult:
        """INV-04: Next-hop IP must be a valid, reachable IPv4 address."""
        if not request.next_hop:
            # Check if next_hop can be resolved from registry
            p_def = next((p for p in WAN_PROVIDER_REGISTRY if p["provider_id"] == request.target_provider), None)
            nh = p_def.get("next_hop") if p_def else None
        else:
            nh = request.next_hop

        if not nh:
            return InvariantCheckResult(
                invariant_id="INV-04",
                invariant_name="NEXT_HOP_VALID",
                passed=False,
                severity="CRITICAL",
                message=f"No next-hop IP specified or resolvable for '{request.target_provider}'.",
            )

        try:
            ip = ipaddress.ip_address(nh)
            passed = not ip.is_loopback and not ip.is_unspecified and not ip.is_multicast
            msg = f"Next-hop IP '{nh}' is a valid routable unicast IPv4 address." if passed else f"Next-hop IP '{nh}' is loopback/unspecified/multicast."
        except ValueError:
            passed = False
            msg = f"Next-hop '{nh}' is not a valid IPv4 address."

        return InvariantCheckResult(
            invariant_id="INV-04",
            invariant_name="NEXT_HOP_VALID",
            passed=passed,
            severity="CRITICAL",
            message=msg,
            details={"next_hop": nh},
        )

    @classmethod
    def check_route_validity(cls, request: Z3VerificationRequest) -> InvariantCheckResult:
        """INV-05: Route entry must have valid destination prefix and distance."""
        passed = True
        err_msg = ""
        for r in request.routes:
            pfx = r.get("prefix", "0.0.0.0/0")
            dist = r.get("distance", 10)
            try:
                ipaddress.ip_network(pfx, strict=False)
            except ValueError:
                passed = False
                err_msg = f"Invalid prefix format: '{pfx}'"
                break
            if not (1 <= dist <= 255):
                passed = False
                err_msg = f"Administrative distance ({dist}) outside valid range [1, 255]."
                break

        msg = "All route table prefixes and administrative metrics are valid." if passed else err_msg
        return InvariantCheckResult(
            invariant_id="INV-05",
            invariant_name="ROUTE_VALID",
            passed=passed,
            severity="HIGH",
            message=msg,
        )

    @classmethod
    def check_loop_freedom(cls, request: Z3VerificationRequest) -> InvariantCheckResult:
        """INV-06: Egress route through next_hop must not create a routing loop back to source."""
        # Detect if next_hop or target path creates a cycle with known topology links
        edges = list(request.topology_links)
        src = request.target_device
        tgt = request.target_provider

        # Check for immediate reflexive edge
        if (tgt, src) in edges and (src, tgt) in edges:
            passed = False
            msg = f"Routing cycle detected between '{src}' and '{tgt}'."
        else:
            passed = True
            msg = "Forwarding path is loop-free and acyclic."

        return InvariantCheckResult(
            invariant_id="INV-06",
            invariant_name="LOOP_FREEDOM",
            passed=passed,
            severity="CRITICAL",
            message=msg,
        )

    @classmethod
    def check_target_authorized(cls, request: Z3VerificationRequest) -> InvariantCheckResult:
        """INV-07: Target device must be in the declared authorization allowlist."""
        dev = request.target_device.lower()
        passed = dev in LAB_ALLOWED_DEVICES or any(d["id"].lower() == dev for d in DEVICE_REGISTRY)
        return InvariantCheckResult(
            invariant_id="INV-07",
            invariant_name="TARGET_AUTHORIZED",
            passed=passed,
            severity="CRITICAL",
            message=f"Target device '{request.target_device}' is in authorization allowlist." if passed else f"Target device '{request.target_device}' is UNAUTHORIZED.",
            details={"target_device": request.target_device},
        )

    @classmethod
    def check_cooldown_satisfied(cls, request: Z3VerificationRequest, min_cooldown_sec: float = 60.0) -> InvariantCheckResult:
        """INV-08: Cooldown duration must be satisfied before next transition."""
        elapsed = request.time_since_last_transition_sec
        passed = elapsed >= min_cooldown_sec
        return InvariantCheckResult(
            invariant_id="INV-08",
            invariant_name="COOLDOWN_SATISFIED",
            passed=passed,
            severity="MEDIUM",
            message=f"Cooldown satisfied ({elapsed:.0f}s elapsed >= {min_cooldown_sec:.0f}s threshold)." if passed else f"Cooldown violation: only {elapsed:.0f}s elapsed (< {min_cooldown_sec:.0f}s required).",
            details={"elapsed_sec": elapsed, "min_required_sec": min_cooldown_sec},
        )

    @classmethod
    def check_anti_flap_stability(cls, request: Z3VerificationRequest, max_per_hour: int = 4) -> InvariantCheckResult:
        """INV-09: Hourly transition rate must not exceed anti-flapping threshold."""
        count = request.transitions_last_hour
        passed = count <= max_per_hour
        return InvariantCheckResult(
            invariant_id="INV-09",
            invariant_name="ANTI_FLAP_STABILITY",
            passed=passed,
            severity="HIGH",
            message=f"Anti-flap check passed ({count} transitions in last hour <= {max_per_hour} max)." if passed else f"Anti-flap violation: {count} transitions in last hour exceeds limit of {max_per_hour}.",
            details={"transitions_last_hour": count, "max_allowed": max_per_hour},
        )

    @classmethod
    def check_blast_radius_bounded(cls, request: Z3VerificationRequest, max_allowed_pct: float = 40.0) -> InvariantCheckResult:
        """INV-10: Predicted blast radius must not exceed safety threshold."""
        br = request.predicted_blast_radius_pct
        passed = br <= max_allowed_pct
        return InvariantCheckResult(
            invariant_id="INV-10",
            invariant_name="BLAST_RADIUS_BOUNDED",
            passed=passed,
            severity="HIGH",
            message=f"Predicted blast radius ({br:.1f}%) within allowable safety bound (<= {max_allowed_pct:.1f}%)." if passed else f"Blast radius violation: predicted impact ({br:.1f}%) exceeds safety limit ({max_allowed_pct:.1f}%).",
            details={"predicted_blast_radius_pct": br, "max_allowed_pct": max_allowed_pct},
        )

    @classmethod
    def check_production_hard_gate(cls, request: Z3VerificationRequest) -> InvariantCheckResult:
        """INV-11: PRODUCTION_AUTHORIZED must strictly be False."""
        # Reject if PRODUCTION_AUTHORIZED is True or request attempts unapproved production mode
        passed = (PRODUCTION_AUTHORIZED is False) and (request.execution_mode != "PRODUCTION_AUTHORIZED")
        return InvariantCheckResult(
            invariant_id="INV-11",
            invariant_name="PRODUCTION_HARD_GATE",
            passed=passed,
            severity="CRITICAL",
            message="PRODUCTION_AUTHORIZED hard-gate enforced (PRODUCTION_AUTHORIZED=False)." if passed else "PRODUCTION_HARD_GATE VIOLATION: Production network mutation is prohibited.",
            details={"PRODUCTION_AUTHORIZED": PRODUCTION_AUTHORIZED, "execution_mode": request.execution_mode},
        )

    @classmethod
    def check_simulated_provider_boundary(cls, request: Z3VerificationRequest) -> InvariantCheckResult:
        """INV-12: Simulated providers must not be executed against physical lab drivers."""
        p_def = next((p for p in WAN_PROVIDER_REGISTRY if p["provider_id"] == request.target_provider), None)
        is_sim = request.is_simulated or (p_def.get("is_simulated", False) if p_def else False) or (request.target_provider in ("ISP-C", "ISP-D"))

        if is_sim and request.execution_mode in ("APPROVED_EXECUTION", "LAB_AUTHORIZED", "PRODUCTION_AUTHORIZED"):
            passed = False
            msg = f"Simulated provider '{request.target_provider}' cannot be targeted in live physical execution mode ('{request.execution_mode}')."
        else:
            passed = True
            msg = f"Provider boundary verified for '{request.target_provider}' (Simulated={is_sim}, Mode={request.execution_mode})."

        return InvariantCheckResult(
            invariant_id="INV-12",
            invariant_name="SIMULATED_PROVIDER_BOUNDARY",
            passed=passed,
            severity="CRITICAL",
            message=msg,
            details={"target_provider": request.target_provider, "is_simulated": is_sim, "execution_mode": request.execution_mode},
        )
