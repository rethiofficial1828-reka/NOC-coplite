"""
Data models for isolated stress-testing framework.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ScenarioFamily(str, Enum):
    TELEMETRY_DEGRADATION = "TELEMETRY_DEGRADATION"
    PACKET_METRICS = "PACKET_METRICS"
    PROVIDER_HEALTH = "PROVIDER_HEALTH"
    INTERFACE_FLAP = "INTERFACE_FLAP"
    PATH_SCORING = "PATH_SCORING"
    TRUST_POLICY = "TRUST_POLICY"
    BLAST_RADIUS = "BLAST_RADIUS"
    APPROVAL_LIFECYCLE = "APPROVAL_LIFECYCLE"
    PRECHECK_VALIDATION = "PRECHECK_VALIDATION"
    EXECUTION_ADAPTER = "EXECUTION_ADAPTER"
    VERIFICATION_LIFECYCLE = "VERIFICATION_LIFECYCLE"
    ROLLBACK_ENGINE = "ROLLBACK_ENGINE"
    ADAPTIVE_TRANSITION = "ADAPTIVE_TRANSITION"
    FEDERATED_PRIVACY_SIGNATURE = "FEDERATED_PRIVACY_SIGNATURE"
    OLLAMA_CAPABILITY = "OLLAMA_CAPABILITY"
    EDGE_CASE_MALFORMED = "EDGE_CASE_MALFORMED"


class FailureCategory(str, Enum):
    EXPECTED_FAILURE = "EXPECTED_FAILURE"      # Handled business rejection / precheck block
    UNEXPECTED_FAILURE = "UNEXPECTED_FAILURE"  # Service crash or unhandled exception
    SAFETY_VIOLATION = "SAFETY_VIOLATION"      # Critical safety or security invariant breached
    HARNESS_FAILURE = "HARNESS_FAILURE"        # Test framework / mock error


@dataclass
class StressTestCase:
    case_id: str
    seed: int
    scenario_family: ScenarioFamily
    input_data: Dict[str, Any]
    expected_behavior: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InvariantResult:
    invariant_name: str
    passed: bool
    category: FailureCategory
    expected: str
    actual: str
    message: str


@dataclass
class FailureRecord:
    case_id: str
    seed: int
    scenario_family: str
    input_data: Dict[str, Any]
    failed_invariant: str
    failure_category: str
    exception_type: Optional[str] = None
    exception_message: Optional[str] = None
    traceback_str: Optional[str] = None
    elapsed_ms: float = 0.0


@dataclass
class CampaignSummary:
    timestamp: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    safety_violations: int
    elapsed_sec: float
    cases_per_sec: float
    mean_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    failures_by_family: Dict[str, int] = field(default_factory=dict)
    failures_by_category: Dict[str, int] = field(default_factory=dict)
