"""
Comprehensive Unit Test Suite for Production OllamaProvider, ProviderFactory,
HTTP connection retry logic, health checks, event emissions, and dependency injection.
"""

import json
import os
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agents.core.container import ServiceContainer
from agents.core.exceptions import ConfigurationError, ExecutionError
from agents.events import Event, EventBus
from agents.knowledge import (
    LLMProvider,
    MockProvider,
    OllamaProvider,
    ProviderFactory,
)
from config.config_manager import ConfigManager


class DummyCustomProvider(LLMProvider):
    """Dummy custom provider for factory extension testing."""

    def initialize(self) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def generate(self, prompt: str, parameters: Optional[Dict[str, Any]] = None) -> str:
        return "Custom Provider Response"

    def health(self) -> Dict[str, Any]:
        return {"status": "ok", "provider_name": "DummyCustomProvider"}

    def metadata(self) -> Dict[str, Any]:
        return {"provider_name": "DummyCustomProvider"}


class TestOllamaProviderFramework(unittest.TestCase):

    def setUp(self):
        ConfigManager.get_instance().reset_overrides()
        EventBus.get_global().clear()
        self.event_bus = EventBus()
        self.container = ServiceContainer()

    def tearDown(self):
        ConfigManager.get_instance().reset_overrides()

    def test_01_provider_factory_resolution(self):
        """Test ProviderFactory provider instantiation and configuration resolution."""
        # Explicit type 'mock'
        p_mock = ProviderFactory.create_provider(provider_type="mock")
        self.assertIsInstance(p_mock, MockProvider)

        # Explicit type 'ollama'
        p_ollama = ProviderFactory.create_provider(provider_type="ollama")
        self.assertIsInstance(p_ollama, OllamaProvider)

        # ConfigManager override
        ConfigManager.get_instance().set_override("LLM_PROVIDER_TYPE", "ollama")
        p_override = ProviderFactory.create_provider()
        self.assertIsInstance(p_override, OllamaProvider)

        # Unknown provider type
        with self.assertRaises(ConfigurationError):
            ProviderFactory.create_provider(provider_type="invalid_provider")

    def test_02_provider_factory_custom_registration(self):
        """Test registering custom LLMProvider class dynamically in ProviderFactory."""
        ProviderFactory.register_provider_class("custom_dummy", DummyCustomProvider)
        p_custom = ProviderFactory.create_provider(provider_type="custom_dummy")
        self.assertIsInstance(p_custom, DummyCustomProvider)
        self.assertEqual(p_custom.generate("test"), "Custom Provider Response")

    def test_03_ollama_provider_metadata_and_health(self):
        """Test OllamaProvider metadata and health check with mocked HTTP response."""
        provider = OllamaProvider(
            model_name="qwen2.5",
            base_url="http://localhost:11434",
            timeout_sec=15.0,
            retry_count=2,
            event_bus=self.event_bus,
        )

        meta = provider.metadata()
        self.assertEqual(meta["provider_name"], "OllamaProvider")
        self.assertEqual(meta["model_name"], "qwen2.5")
        self.assertEqual(meta["base_url"], "http://localhost:11434")
        self.assertTrue(meta["supports_streaming"])

        # Mock health HTTP response
        mock_tags_response = json.dumps({"models": [{"name": "qwen2.5:latest"}]}).encode("utf-8")
        with patch.object(provider, "_http_request", return_value=mock_tags_response):
            health = provider.health()
            self.assertEqual(health["status"], "ok")
            self.assertEqual(health["provider_name"], "OllamaProvider")
            self.assertTrue(health["model_available"])

    def test_04_ollama_provider_successful_generate(self):
        """Test OllamaProvider successful prompt generation and event emission."""
        events_captured = []
        self.event_bus.subscribe("provider.initialized", lambda e: events_captured.append(e))

        provider = OllamaProvider(
            model_name="llama3",
            base_url="http://localhost:11434",
            event_bus=self.event_bus,
        )

        mock_gen_response = json.dumps({
            "model": "llama3",
            "response": "ROOT CAUSE ANALYSIS:\nSaturated interface buffer.\n\nRECOMMENDED ACTIONS:\n1. Enable QoS\n\nCONFIDENCE: 0.95",
            "done": True,
        }).encode("utf-8")

        with patch.object(provider, "_http_request", return_value=mock_gen_response) as mock_req:
            res = provider.generate("Test prompt for network anomaly")

            self.assertIn("ROOT CAUSE ANALYSIS", res)
            self.assertIn("Saturated interface buffer", res)
            mock_req.assert_called_once()

            # Verify request payload
            call_url, call_kwargs = mock_req.call_args[0][0], mock_req.call_args[1]
            data_sent = json.loads(mock_req.call_args[1]["data"].decode("utf-8"))
            self.assertEqual(data_sent["model"], "llama3")
            self.assertFalse(data_sent["stream"])

        self.assertTrue(len(events_captured) > 0)
        self.assertEqual(events_captured[0].event_type, "provider.initialized")

    def test_05_ollama_provider_retry_policy_and_failure(self):
        """Test OllamaProvider retry logic upon HTTP failure and graceful error handling."""
        failed_events = []
        self.event_bus.subscribe("provider.failed", lambda e: failed_events.append(e))

        provider = OllamaProvider(
            model_name="llama3",
            retry_count=2,
            timeout_sec=1.0,
            event_bus=self.event_bus,
        )

        # Test retry recovery (1 failure, 1 success)
        mock_gen_response = json.dumps({"response": "Recovered response"}).encode("utf-8")
        side_effects = [Exception("Connection refused"), mock_gen_response]

        with patch.object(provider, "_http_request", side_effect=side_effects):
            res = provider.generate("Prompt requiring retry")
            self.assertEqual(res, "Recovered response")

        # Test retry exhaustion failure
        with patch.object(provider, "_http_request", side_effect=Exception("Persistent Network Error")):
            with self.assertRaises(ExecutionError):
                provider.generate("Failing prompt")

        self.assertTrue(len(failed_events) >= 1)
        self.assertEqual(failed_events[0].event_type, "provider.failed")

    def test_06_thread_safe_concurrent_ollama_inference(self):
        """Test multi-threaded concurrent execution of OllamaProvider."""
        provider = OllamaProvider(model_name="llama3", retry_count=1)
        mock_gen_response = json.dumps({"response": "Concurrent response"}).encode("utf-8")

        def worker_task(i: int):
            with patch.object(provider, "_http_request", return_value=mock_gen_response):
                return provider.generate(f"Prompt {i}")

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker_task, i) for i in range(10)]
            results = [f.result() for f in futures]

        self.assertEqual(results, ["Concurrent response"] * 10)


if __name__ == "__main__":
    unittest.main()
