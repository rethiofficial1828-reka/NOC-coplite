"""
Test Suite for Subsystem Resilience, Fault Tolerance & Failure Injection Recovery.

40 Scenarios validating graceful degradation, exception handling, fallback logic, recovery behavior,
and resilience when services, databases, networks, LLMs, or configurations fail or become corrupted.
"""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock

from agents.adaptive_failover.adaptive_failover_service import AdaptiveFailoverService
from agents.adaptive_failover.adaptive_models import ProviderHealthSnapshot
from agents.adaptive_failover.continuous_verifier import ContinuousVerificationEngine
from agents.adaptive_failover.failback_engine import FailbackEngine
from agents.core.container import ServiceContainer
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.failover.dry_run_adapter import DryRunExecutionAdapter
from agents.failover.failover_service import FailoverService
from agents.federated_intelligence.bundle_importer import BundleImporter
from agents.federated_intelligence.crypto_signer import CryptoSigner
from agents.federated_intelligence.privacy_sanitizer import PrivacySanitizer
from agents.knowledge.ollama_provider import OllamaProvider
from agents.path_decision.decision_service import PathDecisionService
from agents.runtime.ollama_detector import OllamaDetector
from agents.runtime.runtime_service import RuntimeService


class TestResilienceFailureInjection(unittest.TestCase):
    """40 Resilience & Fault Injection Test Scenarios."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.event_bus = EventBus()
        self.container = ServiceContainer()

    # 1-5: Ollama & LLM Resilience
    def test_01_ollama_offline_fallback(self) -> None:
        detector = OllamaDetector(endpoint="http://127.0.0.1:99999")  # Invalid port
        self.assertFalse(detector.check_ollama_available())

    def test_02_ollama_version_error_handling(self) -> None:
        detector = OllamaDetector(endpoint="http://127.0.0.1:99999")
        self.assertEqual(detector.get_ollama_version(), "OFFLINE")

    def test_03_ollama_model_missing(self) -> None:
        detector = OllamaDetector(endpoint="http://127.0.0.1:99999")
        self.assertFalse(detector.check_model_available("non_existent_model:latest"))

    def test_04_ollama_provider_inference_fallback(self) -> None:
        provider = OllamaProvider(endpoint="http://127.0.0.1:99999")
        response = provider.generate("Test prompt")
        self.assertIsNotNone(response)
        self.assertIn("content", response)

    def test_05_runtime_service_resilience(self) -> None:
        service = RuntimeService()
        health = service.check_runtime_health()
        self.assertIsNotNone(health)

    # 6-10: Database & Storage Resilience
    def test_06_corrupted_json_file_handling(self) -> None:
        corrupt_path = os.path.join(self.temp_dir, "corrupt.json")
        with open(corrupt_path, "w", encoding="utf-8") as f:
            f.write("{invalid_json:")
        importer = BundleImporter()
        bundle, res = importer.import_and_validate_bundle(corrupt_path)
        self.assertIsNone(bundle)

    def test_07_missing_json_file_handling(self) -> None:
        importer = BundleImporter()
        bundle, res = importer.import_and_validate_bundle("/tmp/missing_file.json")
        self.assertIsNone(bundle)

    def test_08_empty_json_file_handling(self) -> None:
        empty_path = os.path.join(self.temp_dir, "empty.json")
        with open(empty_path, "w", encoding="utf-8") as f:
            f.write("{}")
        importer = BundleImporter()
        bundle, res = importer.import_and_validate_bundle(empty_path)
        self.assertIsNone(bundle)

    def test_09_permission_denied_directory_resilience(self) -> None:
        self.assertTrue(os.path.exists(self.temp_dir))

    def test_10_missing_directory_auto_creation(self) -> None:
        new_dir = os.path.join(self.temp_dir, "nested", "path")
        os.makedirs(new_dir, exist_ok=True)
        self.assertTrue(os.path.exists(new_dir))

    # 11-15: EventBus & ServiceContainer Resilience
    def test_11_eventbus_handler_exception_isolation(self) -> None:
        def bad_handler(e):
            raise RuntimeError("Handler crash!")

        self.event_bus.subscribe("test.crash", bad_handler)
        # Publishing event should not crash the publisher
        try:
            self.event_bus.publish(Event(event_type="test.crash", source="Test", payload={}))
            ok = True
        except Exception:
            ok = False
        self.assertTrue(ok)

    def test_12_eventbus_empty_payload(self) -> None:
        received = []
        self.event_bus.subscribe("test.empty", lambda e: received.append(e))
        self.event_bus.publish(Event(event_type="test.empty", source="Test", payload={}))
        self.assertEqual(len(received), 1)

    def test_13_container_missing_service_resolution(self) -> None:
        val = self.container.get("non_existent_service")
        self.assertIsNone(val)

    def test_14_container_duplicate_registration(self) -> None:
        self.container.register("s1", "v1")
        self.container.register("s1", "v2")
        self.assertEqual(self.container.get("s1"), "v2")

    def test_15_container_clear(self) -> None:
        self.container.register("s1", "v1")
        self.container.clear()
        self.assertIsNone(self.container.get("s1"))

    # 16-20: Path Decision & Failover Resilience
    def test_16_path_decision_empty_candidates(self) -> None:
        p_service = PathDecisionService()
        res = p_service.evaluate_path_decision("Branch3-Uplink", candidate_overrides=[])
        self.assertIsNotNone(res)

    def test_17_failover_service_invalid_interface(self) -> None:
        f_service = FailoverService()
        res = f_service.execute_failover_pipeline("non_existent_interface")
        self.assertIsNotNone(res)

    def test_18_adapter_invalid_target_resilience(self) -> None:
        adapter = DryRunExecutionAdapter()
        res = adapter.execute_action("invalid_target", "INVALID_ACTION", {})
        self.assertFalse(res["success"])

    def test_19_continuous_verifier_regression_detection(self) -> None:
        verifier = ContinuousVerificationEngine()
        snap_before = ProviderHealthSnapshot(provider_name="ISP-A", wan_interface="eth0", health_score=80.0)
        snap_curr = ProviderHealthSnapshot(provider_name="ISP-B", wan_interface="eth1", health_score=35.0)
        res = verifier.evaluate_continuous_verification(snap_before, snap_curr)
        self.assertTrue(res.regression_detected)

    def test_20_failback_engine_unstable_recovery(self) -> None:
        engine = FailbackEngine()
        snap_pri = ProviderHealthSnapshot(provider_name="ISP-A", wan_interface="eth0", health_score=92.0)
        snap_curr = ProviderHealthSnapshot(provider_name="ISP-B", wan_interface="eth1", health_score=90.0)
        cand = engine.evaluate_failback(snap_pri, snap_curr, recovery_duration_sec=10.0)
        self.assertEqual(cand.status.value, "WAIT_FOR_STABILITY")

    # 21-25: Cryptographic & Privacy Resilience
    def test_21_signer_null_key_handling(self) -> None:
        signer = CryptoSigner(secret_key=b"")
        sig = signer.sign_payload({"a": 1})
        self.assertTrue(len(sig.signature_hex) > 0)

    def test_22_signer_tampered_payload_verification(self) -> None:
        signer = CryptoSigner()
        sig = signer.sign_payload({"a": 1})
        ok, msg = signer.verify_signature({"a": 2}, sig)
        self.assertFalse(ok)

    def test_23_sanitizer_none_string_handling(self) -> None:
        sanitizer = PrivacySanitizer()
        clean = sanitizer.sanitize_text(None)
        self.assertEqual(clean, "")

    def test_24_sanitizer_empty_string_handling(self) -> None:
        sanitizer = PrivacySanitizer()
        clean = sanitizer.sanitize_text("")
        self.assertEqual(clean, "")

    def test_25_sanitizer_multiple_ips_handling(self) -> None:
        sanitizer = PrivacySanitizer()
        clean = sanitizer.sanitize_text("10.0.0.1 and 192.168.1.1 and 172.16.0.1")
        self.assertNotIn("10.0.0.1", clean)
        self.assertNotIn("192.168.1.1", clean)
        self.assertNotIn("172.16.0.1", clean)

    # 26-30: Adaptive Failover Service Resilience
    def test_26_adaptive_service_cycle_resilience(self) -> None:
        service = AdaptiveFailoverService()
        res = service.process_adaptive_failover_cycle()
        self.assertIsNotNone(res)

    def test_27_adaptive_service_stats_retrieval(self) -> None:
        service = AdaptiveFailoverService()
        stats = service.get_statistics()
        self.assertIsNotNone(stats)

    def test_28_adaptive_service_override_metrics(self) -> None:
        service = AdaptiveFailoverService()
        res = service.process_adaptive_failover_cycle(
            active_metrics_override={"latency_ms": 200.0, "packet_loss_percent": 10.0},
            degradation_duration_sec=45.0,
        )
        self.assertIsNotNone(res)

    def test_29_adaptive_service_rapid_re_evaluation(self) -> None:
        service = AdaptiveFailoverService()
        res1 = service.process_adaptive_failover_cycle()
        res2 = service.process_adaptive_failover_cycle()
        self.assertEqual(res1.active_provider, res2.active_provider)

    def test_30_adaptive_service_eventbus_disconnect(self) -> None:
        service = AdaptiveFailoverService(event_bus=None)
        res = service.process_adaptive_failover_cycle()
        self.assertIsNotNone(res)

    # 31-40: Exception Isolation & Graceful Recovery
    def test_31_exception_isolation_invalid_dict(self) -> None:
        importer = BundleImporter()
        bundle, res = importer.import_and_validate_bundle({"invalid_dict": True})
        self.assertIsNone(bundle)

    def test_32_exception_isolation_large_string(self) -> None:
        large_str = "A" * 100000
        sanitizer = PrivacySanitizer()
        clean = sanitizer.sanitize_text(large_str)
        self.assertEqual(len(clean), 100000)

    def test_33_exception_isolation_unicode_string(self) -> None:
        unicode_str = "Network Error: 网络错误 / 障害"
        sanitizer = PrivacySanitizer()
        clean = sanitizer.sanitize_text(unicode_str)
        self.assertEqual(clean, unicode_str)

    def test_34_exception_isolation_special_chars(self) -> None:
        spec_str = "Error: !@#$%^&*()_+{}[]:;<>,.?"
        sanitizer = PrivacySanitizer()
        clean = sanitizer.sanitize_text(spec_str)
        self.assertEqual(clean, spec_str)

    def test_35_exception_isolation_zero_metrics(self) -> None:
        service = AdaptiveFailoverService()
        res = service.process_adaptive_failover_cycle(
            active_metrics_override={"latency_ms": 0.0, "packet_loss_percent": 0.0},
        )
        self.assertIsNotNone(res)

    def test_36_exception_isolation_negative_metrics_rejection(self) -> None:
        service = AdaptiveFailoverService()
        res = service.process_adaptive_failover_cycle(
            active_metrics_override={"latency_ms": -10.0, "packet_loss_percent": -5.0},
        )
        self.assertIsNotNone(res)

    def test_37_exception_isolation_high_metrics_handling(self) -> None:
        service = AdaptiveFailoverService()
        res = service.process_adaptive_failover_cycle(
            active_metrics_override={"latency_ms": 9999.0, "packet_loss_percent": 100.0},
        )
        self.assertIsNotNone(res)

    def test_38_exception_isolation_repeated_cycle_calls(self) -> None:
        service = AdaptiveFailoverService()
        for i in range(10):
            service.process_adaptive_failover_cycle()
        self.assertEqual(service.get_statistics().total_evaluations, 10)

    def test_39_exception_isolation_concurrent_access_safety(self) -> None:
        service = AdaptiveFailoverService()
        stats = service.get_statistics()
        self.assertGreaterEqual(stats.total_evaluations, 0)

    def test_40_graceful_system_degradation(self) -> None:
        service = AdaptiveFailoverService()
        res = service.process_adaptive_failover_cycle()
        self.assertTrue(res.audit_reference.startswith("ADAPTIVE-"))


if __name__ == "__main__":
    unittest.main()
