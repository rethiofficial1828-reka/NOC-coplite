"""
Z3 Formal Verification Models Module for NOC-Copilot Formal Verification Subsystem.

Defines Pydantic V2 domain models representing formal verification requests,
satisfiability outcomes (SAT / UNSAT), invariant check results, counterexamples,
and formal verification audit reports.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import uuid

from pydantic import BaseModel, ConfigDict, Field


class Z3VerificationStatus(str, Enum):
    """Satisfiability classification for formal invariant verification."""

    SAT = "SAT"          # Invariants are satisfied / Candidate plan is formally verified safe
    UNSAT = "UNSAT"      # Invariant violation found / Candidate plan rejected
    UNKNOWN = "UNKNOWN"  # Solver could not determine satisfiability within resource bounds


class InvariantCheckResult(BaseModel):
    """Result of an individual formal invariant verification check."""

    model_config = ConfigDict(frozen=False)

    invariant_id: str = Field(..., description="Unique invariant key identifier")
    invariant_name: str = Field(..., description="Human-readable invariant title")
    passed: bool = Field(..., description="Whether invariant was formally proved")
    severity: str = Field(default="CRITICAL", description="CRITICAL, HIGH, MEDIUM, LOW")
    message: str = Field(default="", description="Detailed proof or counterexample message")
    details: Dict[str, Any] = Field(default_factory=dict, description="Sanitized evaluation details")


class Z3VerificationRequest(BaseModel):
    """Complete specification payload for formal safety invariant verification."""

    model_config = ConfigDict(frozen=False)

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    plan_id: str = Field(default="", description="Execution plan ID")
    source_provider: str = Field(..., description="Source provider being replaced")
    target_provider: str = Field(..., description="Target candidate provider to activate")
    target_device: str = Field(default="branch3-uplink", description="Target router or gateway device")
    wan_interface: str = Field(default="Branch3-Uplink", description="Target WAN interface")
    next_hop: Optional[str] = Field(default=None, description="Proposed next-hop IP address")
    is_simulated: bool = Field(default=False, description="Whether target provider is simulated")
    execution_mode: str = Field(default="DRY_RUN", description="DRY_RUN, SIMULATION, APPROVED_EXECUTION, PRODUCTION_AUTHORIZED")
    predicted_blast_radius_pct: float = Field(default=0.0, ge=0.0, le=100.0, description="Predicted blast radius from Twin/GNN")
    time_since_last_transition_sec: float = Field(default=9999.0, description="Seconds elapsed since prior transition")
    transitions_last_hour: int = Field(default=0, description="Count of transitions in the last 60 minutes")
    routes: List[Dict[str, Any]] = Field(default_factory=list, description="Active route table entries")
    topology_nodes: List[str] = Field(default_factory=list, description="All known topology node IDs")
    topology_links: List[Tuple[str, str]] = Field(default_factory=list, description="Topology adjacency edges (src, dst)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extended operational attributes")


class Z3VerificationResult(BaseModel):
    """Outcome of formal invariant verification by Z3FormalVerifier."""

    model_config = ConfigDict(frozen=False)

    result_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str = Field(...)
    status: Z3VerificationStatus = Field(..., description="SAT (safe) or UNSAT (unsafe)")
    is_safe: bool = Field(..., description="True if SAT and all invariants passed")
    solver_type: str = Field(default="z3_native", description="z3_native or deterministic_fallback")
    passed_invariants: List[str] = Field(default_factory=list, description="List of satisfied invariant names")
    violated_invariants: List[str] = Field(default_factory=list, description="List of violated invariant names")
    invariant_results: List[InvariantCheckResult] = Field(default_factory=list, description="Detailed invariant results")
    counterexample: Optional[Dict[str, Any]] = Field(default=None, description="Counterexample if UNSAT")
    proof_summary: str = Field(default="", description="Formal proof or violation explanation")
    evaluation_time_ms: float = Field(default=0.0, description="Solver execution time in milliseconds")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FormalVerificationReport(BaseModel):
    """Complete auditable formal verification record."""

    model_config = ConfigDict(frozen=False)

    report_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request: Z3VerificationRequest = Field(...)
    result: Z3VerificationResult = Field(...)
    audit_hash: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
