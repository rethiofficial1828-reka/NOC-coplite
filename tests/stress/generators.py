"""
Deterministic scenario generator for isolated stress-testing framework.
"""

from datetime import datetime, timezone
import hashlib
import random
from typing import Any, Dict, List, Tuple

from tests.stress.models import ScenarioFamily, StressTestCase


class StressDataGenerator:
    """
    Seed-reproducible multi-domain scenario generator.
    Produces deterministic test inputs across 16 scenario families.
    """

    SCENARIO_FAMILIES = list(ScenarioFamily)

    def __init__(self, base_seed: int = 42):
        self.base_seed = base_seed

    def generate_case(self, case_index: int, target_family: ScenarioFamily = None) -> StressTestCase:
        """
        Generate a single StressTestCase for a given case_index (1-indexed).
        Same base_seed + case_index guarantees 100% identical outputs.
        """
        # Mix base_seed and case_index deterministically
        seed_bytes = f"{self.base_seed}:{case_index}".encode("utf-8")
        case_seed = int(hashlib.sha256(seed_bytes).hexdigest()[:8], 16)
        rng = random.Random(case_seed)

        case_id = f"STRESS-{case_index:06d}"
        if target_family is None:
            family = self.SCENARIO_FAMILIES[(case_index - 1) % len(self.SCENARIO_FAMILIES)]
        else:
            family = target_family

        generator_func = getattr(self, f"_gen_{family.value.lower()}", self._gen_edge_case_malformed)
        input_data, expected_behavior = generator_func(rng, case_seed)

        return StressTestCase(
            case_id=case_id,
            seed=case_seed,
            scenario_family=family,
            input_data=input_data,
            expected_behavior=expected_behavior,
        )

    def generate_batch(self, count: int, offset: int = 0) -> List[StressTestCase]:
        """Generate a batch of deterministic test cases."""
        return [self.generate_case(i + 1 + offset) for i in range(count)]

    # -----------------------------------------------------------------------
    # Family Generators
    # -----------------------------------------------------------------------

    def _gen_telemetry_degradation(self, rng: random.Random, case_seed: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        mode = rng.choice(["GRADUAL", "SUDDEN", "NOISY", "EXTREME_NEGATIVE", "EXTREME_HIGH"])
        if mode == "GRADUAL":
            lat = rng.uniform(10.0, 150.0)
            loss = rng.uniform(0.0, 5.0)
        elif mode == "SUDDEN":
            lat = rng.uniform(180.0, 500.0)
            loss = rng.uniform(8.0, 25.0)
        elif mode == "EXTREME_NEGATIVE":
            lat = -50.0
            loss = -5.0
        elif mode == "EXTREME_HIGH":
            lat = 99999.0
            loss = 100.0
        else:
            lat = rng.uniform(5.0, 300.0)
            loss = rng.uniform(0.0, 15.0)

        data = {
            "interface_id": rng.choice(["Branch3-Uplink", "ISP-A-eth0", "ISP-B-eth1", "WAN-01"]),
            "mode": mode,
            "metrics": {
                "latency_ms": lat,
                "packet_loss_percent": loss,
                "jitter_ms": rng.uniform(0.0, 80.0),
                "utilization_percent": rng.uniform(0.0, 100.0),
                "routing_flaps": rng.randint(0, 10),
            },
        }
        expected = {"degraded": lat > 150.0 or loss > 5.0}
        return data, expected

    def _gen_packet_metrics(self, rng: random.Random, case_seed: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        lat = rng.choice([15.0, 45.0, 150.0, 194.9, 195.0, 250.0, 1000.0])
        loss = rng.choice([0.0, 1.0, 5.0, 7.9, 8.0, 12.0, 50.0])
        jitter = rng.choice([2.0, 10.0, 44.9, 45.0, 90.0])
        data = {
            "active_metrics": {"latency_ms": lat, "packet_loss_percent": loss, "jitter_ms": jitter},
            "candidate_metrics": {"latency_ms": 15.0, "packet_loss_percent": 0.0, "jitter_ms": 2.0},
        }
        expected = {"sla_breached": lat >= 195.0 or loss >= 8.0}
        return data, expected

    def _gen_provider_health(self, rng: random.Random, case_seed: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        provider_a_state = rng.choice(["HEALTHY", "DEGRADED", "CRITICAL", "FAILED"])
        provider_b_state = rng.choice(["HEALTHY", "DEGRADED", "CRITICAL", "FAILED"])
        data = {
            "provider_a": "ISP-A",
            "provider_a_state": provider_a_state,
            "provider_b": "ISP-B",
            "provider_b_state": provider_b_state,
        }
        expected = {"recommend_failover": provider_a_state in ["CRITICAL", "FAILED"] and provider_b_state == "HEALTHY"}
        return data, expected

    def _gen_interface_flap(self, rng: random.Random, case_seed: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        flaps = rng.randint(0, 15)
        duration_sec = rng.uniform(1.0, 600.0)
        data = {
            "active_provider": "ISP-A",
            "flaps_count": flaps,
            "degradation_duration_sec": duration_sec,
            "min_confirmation_sec": 30.0,
        }
        expected = {"hysteresis_passed": flaps < 3 and duration_sec >= 30.0}
        return data, expected

    def _gen_path_scoring(self, rng: random.Random, case_seed: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        data = {
            "interface_id": "Branch3-Uplink",
            "latency_weight": rng.uniform(0.1, 0.9),
            "loss_weight": rng.uniform(0.1, 0.9),
            "cost_weight": rng.uniform(0.0, 0.5),
        }
        expected = {"score_range": [0.0, 100.0]}
        return data, expected

    def _gen_trust_policy(self, rng: random.Random, case_seed: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        risk = rng.uniform(0.0, 1.0)
        blast = rng.choice(["LOW", "MEDIUM", "HIGH", "CRITICAL"])
        action = rng.choice(["FAILOVER", "FAILBACK", "RECONFIG", "RESTART"])
        data = {
            "risk_score": risk,
            "action_name": action,
            "blast_radius": blast,
            "cost_estimate": rng.uniform(0.0, 500.0),
        }
        expected = {"auto_eligible": blast in ["LOW", "MEDIUM"] and risk < 0.7}
        return data, expected

    def _gen_blast_radius(self, rng: random.Random, case_seed: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        blast = rng.choice(["HIGH", "CRITICAL"])
        data = {
            "risk_score": rng.uniform(0.1, 0.95),
            "action_name": "ROUTER_INTERFACED_SHUTDOWN",
            "blast_radius": blast,
            "attempted_auto_approve": True,
        }
        expected = {"must_block_or_require_human": True}
        return data, expected

    def _gen_approval_lifecycle(self, rng: random.Random, case_seed: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        tamper = rng.choice([True, False])
        data = {
            "interface_id": "Branch3-Uplink",
            "plan_hash": "PLAN-HASH-ORIGINAL-12345",
            "execution_hash": "PLAN-HASH-TAMPERED-99999" if tamper else "PLAN-HASH-ORIGINAL-12345",
            "is_tampered": tamper,
        }
        expected = {"approval_valid": not tamper}
        return data, expected

    def _gen_precheck_validation(self, rng: random.Random, case_seed: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        stale = rng.choice([True, False])
        data = {
            "interface_id": "Branch3-Uplink",
            "sim_context": {
                "telemetry_timestamp": "2020-01-01T00:00:00Z" if stale else datetime.now(timezone.utc).isoformat(),
                "route_table_valid": not rng.choice([True, False, False]),
            },
            "is_stale": stale,
        }
        expected = {"prechecks_passed": not stale}
        return data, expected

    def _gen_execution_adapter(self, rng: random.Random, case_seed: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        mode = rng.choice(["DRY_RUN", "SIMULATION", "APPROVED_EXECUTION"])
        data = {
            "interface_id": "Branch3-Uplink",
            "execution_mode": mode,
            "commands": ["ip route replace default via 10.0.2.1", "ssh router-1 'show ip bgp'"],
        }
        expected = {"zero_subprocesses": True}
        return data, expected

    def _gen_verification_lifecycle(self, rng: random.Random, case_seed: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        override_status = rng.choice(["PASSED", "FAILED", "PARTIAL", "TIMEOUT"])
        data = {
            "interface_id": "Branch3-Uplink",
            "override_verification_status": override_status,
            "auto_approve": True,
        }
        expected = {"trigger_rollback": override_status in ["FAILED", "TIMEOUT"]}
        return data, expected

    def _gen_rollback_engine(self, rng: random.Random, case_seed: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        data = {
            "interface_id": "Branch3-Uplink",
            "sim_context": {"restore_route": "10.0.1.1"},
            "override_verification_status": "FAILED",
        }
        expected = {"final_status": "ROLLED_BACK", "verification_status": "FAILED"}
        return data, expected

    def _gen_adaptive_transition(self, rng: random.Random, case_seed: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        rec_dur = rng.uniform(0.0, 120.0)
        data = {
            "active_provider": "ISP-B",
            "candidate_provider": "ISP-A",
            "recovery_duration_sec": rec_dur,
            "override_satisfied": rec_dur >= 60.0,
        }
        expected = {"failback_recommended": rec_dur >= 60.0}
        return data, expected

    def _gen_federated_privacy_signature(self, rng: random.Random, case_seed: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        has_pii = rng.choice([True, False])
        tamper_sig = rng.choice([True, False])
        raw_text = "Incident on 10.50.0.1 with MAC 00:11:22:33:44:55 token sec_99" if has_pii else "Clean WAN degradation report"
        data = {
            "raw_text": raw_text,
            "has_pii": has_pii,
            "tamper_signature": tamper_sig,
            "trust_origin": "FEDERATED_SITE_ALPHA",
        }
        expected = {"pii_scrubbed": True, "signature_valid": not tamper_sig}
        return data, expected

    def _gen_ollama_capability(self, rng: random.Random, case_seed: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        available = rng.choice([True, False])
        data = {
            "endpoint": "http://10.0.2.2:11434" if available else "http://127.0.0.1:9999",
            "timeout_sec": rng.choice([0.001, 2.0, 10.0]),
            "is_available": available,
        }
        expected = {"graceful_fallback": True}
        return data, expected

    def _gen_edge_case_malformed(self, rng: random.Random, case_seed: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        kind = rng.choice(["EMPTY_STR", "NONE_VAL", "UNICODE_EMOJI", "HUGE_STR", "INVALID_TYPE"])
        if kind == "EMPTY_STR":
            payload = ""
        elif kind == "NONE_VAL":
            payload = None
        elif kind == "UNICODE_EMOJI":
            payload = "🔥 Network Down! ⚠️⚡"
        elif kind == "HUGE_STR":
            payload = "A" * 10000
        else:
            payload = 123456789

        data = {"interface_id": payload, "malformed_kind": kind}
        expected = {"handled_safely": True}
        return data, expected
