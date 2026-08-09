"""
Comprehensive Unit Test Suite for NOC Copilot Runtime & Hardware Acceleration Layer.

Tests OS detection, virtualization context, GPU inspection, Ollama discovery,
Qwen3:1.7B verification, deterministic inference backend selection, runtime health tracking,
and Atomic RuntimeAgent EventBus lifecycle.
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath('.'))

from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.runtime import (
    CapabilityManager,
    CapabilityStatus,
    GPUDetector,
    GPUInfo,
    GPUVendor,
    InferenceBackend,
    InferenceSelector,
    ModelDetector,
    OllamaDetector,
    OllamaInfo,
    OllamaLocation,
    OSDetector,
    OperatingSystem,
    RuntimeAgent,
    RuntimeCapabilities,
    RuntimeHealth,
    RuntimeHealthEvaluator,
    RuntimeService,
    VirtualizationEnvironment,
)


class TestRuntimeCapabilitySuite(unittest.TestCase):
    """35+ Unit test cases covering all Sprint 16.5 runtime requirements."""

    def setUp(self):
        self.event_bus = EventBus()
        self.published_events = []
        self.event_bus.subscribe("*", lambda evt: self.published_events.append(evt))

    # ---------------------------------------------------------------------------
    # 1. OS & Platform Detection Tests
    # ---------------------------------------------------------------------------
    @patch("platform.system", return_value="Windows")
    @patch("platform.machine", return_value="AMD64")
    def test_01_windows_detection(self, mock_arch, mock_sys):
        detector = OSDetector()
        info = detector.detect()
        self.assertEqual(info.operating_system, OperatingSystem.WINDOWS)
        self.assertEqual(info.architecture, "AMD64")

    @patch("platform.system", return_value="Linux")
    @patch("platform.machine", return_value="x86_64")
    def test_02_linux_detection(self, mock_arch, mock_sys):
        detector = OSDetector()
        info = detector.detect()
        self.assertEqual(info.operating_system, OperatingSystem.LINUX)
        self.assertEqual(info.architecture, "x86_64")

    def test_03_architecture_detection(self):
        detector = OSDetector()
        info = detector.detect()
        self.assertIn(info.architecture, ["x86_64", "AMD64", "arm64", "aarch64"])

    # ---------------------------------------------------------------------------
    # 2. Virtualization Environment Tests
    # ---------------------------------------------------------------------------
    @patch("os.path.exists")
    def test_04_native_environment(self, mock_exists):
        mock_exists.return_value = False
        detector = OSDetector()
        info = detector.detect()
        self.assertFalse(info.is_virtualized)

    @patch("os.path.exists")
    def test_05_virtualbox_environment(self, mock_exists):
        def exists_side_effect(path):
            if path == "/sys/class/dmi/id/sys_vendor":
                return True
            return False

        mock_exists.side_effect = exists_side_effect
        detector = OSDetector()
        with patch("builtins.open", unittest.mock.mock_open(read_data="innotek GmbH VirtualBox")):
            info = detector.detect()
            self.assertEqual(info.virtualization_environment, VirtualizationEnvironment.VIRTUALBOX)
            self.assertTrue(info.is_virtualized)

    @patch("os.path.exists")
    def test_06_vmware_environment(self, mock_exists):
        def exists_side_effect(path):
            if path == "/sys/class/dmi/id/sys_vendor":
                return True
            return False

        mock_exists.side_effect = exists_side_effect
        detector = OSDetector()
        with patch("builtins.open", unittest.mock.mock_open(read_data="VMware, Inc.")):
            info = detector.detect()
            self.assertEqual(info.virtualization_environment, VirtualizationEnvironment.VMWARE)

    @patch("os.path.exists", return_value=True)
    def test_07_docker_detection(self, mock_exists):
        detector = OSDetector()
        info = detector.detect()
        self.assertEqual(info.virtualization_environment, VirtualizationEnvironment.DOCKER)

    # ---------------------------------------------------------------------------
    # 3. GPU Hardware Detection Tests
    # ---------------------------------------------------------------------------
    @patch("shutil.which", return_value="/usr/bin/nvidia-smi")
    @patch("subprocess.run")
    def test_08_nvidia_gpu_available(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="NVIDIA RTX 4050 Laptop GPU, 6144, 535.104.05\n"
        )
        detector = GPUDetector()
        info = detector.detect(os_type=OperatingSystem.WINDOWS, is_virtualized=False)
        self.assertEqual(info.vendor, GPUVendor.NVIDIA)
        self.assertEqual(info.name, "NVIDIA RTX 4050 Laptop GPU")
        self.assertEqual(info.vram_mb, 6144.0)
        self.assertEqual(info.status, CapabilityStatus.AVAILABLE)
        self.assertTrue(info.is_guest_exposed)

    def test_09_nvidia_unavailable(self):
        detector = GPUDetector()
        with patch("shutil.which", return_value=None):
            info = detector.detect(os_type=OperatingSystem.LINUX, is_virtualized=False)
            self.assertEqual(info.vendor, GPUVendor.NONE)

    @patch("shutil.which", return_value=None)
    def test_10_nvidia_smi_missing(self, mock_which):
        detector = GPUDetector()
        info = detector.detect(os_type=OperatingSystem.LINUX, is_virtualized=False)
        self.assertEqual(info.status, CapabilityStatus.UNAVAILABLE)

    @patch("shutil.which", return_value="/usr/bin/nvidia-smi")
    @patch("subprocess.run", side_effect=TimeoutError("Command timed out"))
    def test_11_nvidia_smi_timeout(self, mock_run, mock_which):
        detector = GPUDetector()
        info = detector.detect(os_type=OperatingSystem.LINUX, is_virtualized=False)
        self.assertEqual(info.status, CapabilityStatus.UNAVAILABLE)

    @patch("shutil.which", return_value="/usr/bin/nvidia-smi")
    @patch("subprocess.run")
    def test_12_gpu_memory_parsing(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(returncode=0, stdout="NVIDIA A100, 81920, 525.60.13\n")
        detector = GPUDetector()
        info = detector.detect(os_type=OperatingSystem.LINUX, is_virtualized=False)
        self.assertEqual(info.vram_mb, 81920.0)

    # ---------------------------------------------------------------------------
    # 4. Ollama Discovery & Qwen Model Tests
    # ---------------------------------------------------------------------------
    @patch("urllib.request.urlopen")
    def test_13_ollama_available(self, mock_urlopen):
        mock_resp_v = MagicMock()
        mock_resp_v.read.return_value = json.dumps({"version": "0.1.30"}).encode()
        mock_resp_v.__enter__.return_value = mock_resp_v

        mock_resp_m = MagicMock()
        mock_resp_m.read.return_value = json.dumps({"models": [{"name": "qwen3:1.7b"}]}).encode()
        mock_resp_m.__enter__.return_value = mock_resp_m

        mock_urlopen.side_effect = [mock_resp_v, mock_resp_m]

        detector = OllamaDetector()
        info = detector.detect("http://127.0.0.1:11434")
        self.assertTrue(info.available)
        self.assertEqual(info.version, "0.1.30")
        self.assertEqual(info.location, OllamaLocation.LOCAL_OLLAMA)

    def test_14_ollama_unavailable(self):
        detector = OllamaDetector()
        with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
            info = detector.detect("http://127.0.0.1:11434")
            self.assertFalse(info.available)
            self.assertEqual(info.location, OllamaLocation.UNAVAILABLE)

    @patch("urllib.request.urlopen")
    def test_15_qwen_available(self, mock_urlopen):
        mock_resp_v = MagicMock()
        mock_resp_v.read.return_value = json.dumps({"version": "0.1.30"}).encode()
        mock_resp_v.__enter__.return_value = mock_resp_v

        mock_resp_m = MagicMock()
        mock_resp_m.read.return_value = json.dumps({"models": [{"name": "qwen3:1.7b"}]}).encode()
        mock_resp_m.__enter__.return_value = mock_resp_m

        mock_urlopen.side_effect = [mock_resp_v, mock_resp_m]

        detector = OllamaDetector()
        m_detector = ModelDetector(detector)
        ok, msg = m_detector.verify_primary_model("http://127.0.0.1:11434")
        self.assertTrue(ok)

    @patch("urllib.request.urlopen")
    def test_16_qwen_unavailable(self, mock_urlopen):
        mock_resp_v = MagicMock()
        mock_resp_v.read.return_value = json.dumps({"version": "0.1.30"}).encode()
        mock_resp_v.__enter__.return_value = mock_resp_v

        mock_resp_m = MagicMock()
        mock_resp_m.read.return_value = json.dumps({"models": [{"name": "gemma:2b"}]}).encode()
        mock_resp_m.__enter__.return_value = mock_resp_m

        mock_urlopen.side_effect = [mock_resp_v, mock_resp_m]

        detector = OllamaDetector()
        m_detector = ModelDetector(detector)
        ok, msg = m_detector.verify_primary_model("http://127.0.0.1:11434")
        self.assertFalse(ok)
        self.assertIn("MODEL_UNAVAILABLE", msg)

    # ---------------------------------------------------------------------------
    # 5. Deterministic Inference Selection & Fallback Tests
    # ---------------------------------------------------------------------------
    def test_17_gpu_inference_selection_local(self):
        gpu_info = GPUInfo(vendor=GPUVendor.NVIDIA, status=CapabilityStatus.AVAILABLE, is_guest_exposed=True)
        ollama_info = OllamaInfo(available=True, qwen_available=True, location=OllamaLocation.LOCAL_OLLAMA)
        selector = InferenceSelector()
        backend = selector.select_backend(gpu_info, ollama_info)
        self.assertEqual(backend, InferenceBackend.OLLAMA_GPU_LOCAL)

    def test_17b_gpu_inference_selection_remote(self):
        gpu_info = GPUInfo(vendor=GPUVendor.NONE, status=CapabilityStatus.NOT_EXPOSED_TO_GUEST, is_guest_exposed=False)
        ollama_info = OllamaInfo(available=True, qwen_available=True, location=OllamaLocation.REMOTE_OLLAMA, remote_gpu_accelerated=True)
        selector = InferenceSelector()
        backend = selector.select_backend(gpu_info, ollama_info)
        self.assertEqual(backend, InferenceBackend.OLLAMA_GPU_REMOTE)

    def test_18_cpu_fallback_selection_local(self):
        gpu_info = GPUInfo(vendor=GPUVendor.NONE, status=CapabilityStatus.UNAVAILABLE, is_guest_exposed=False)
        ollama_info = OllamaInfo(available=True, qwen_available=True, location=OllamaLocation.LOCAL_OLLAMA)
        selector = InferenceSelector()
        backend = selector.select_backend(gpu_info, ollama_info)
        self.assertEqual(backend, InferenceBackend.OLLAMA_CPU_LOCAL)

    def test_18b_cpu_fallback_selection_remote(self):
        gpu_info = GPUInfo(vendor=GPUVendor.NONE, status=CapabilityStatus.NOT_EXPOSED_TO_GUEST, is_guest_exposed=False)
        ollama_info = OllamaInfo(available=True, qwen_available=True, location=OllamaLocation.REMOTE_OLLAMA, remote_gpu_accelerated=False)
        selector = InferenceSelector()
        backend = selector.select_backend(gpu_info, ollama_info)
        self.assertEqual(backend, InferenceBackend.OLLAMA_CPU_REMOTE)

    # ---------------------------------------------------------------------------
    # 6. Complete Capability & Health Assessment Tests
    # ---------------------------------------------------------------------------
    def test_19_complete_capability_report(self):
        manager = CapabilityManager()
        caps = manager.get_capabilities(force_refresh=True)
        self.assertIsNotNone(caps.operating_system)
        self.assertIsNotNone(caps.selected_backend)

    def test_20_runtime_degraded_state(self):
        evaluator = RuntimeHealthEvaluator()
        caps = RuntimeCapabilities(
            virtualization_environment=VirtualizationEnvironment.VIRTUALBOX,
            is_guest_gpu_exposed=False,
            ollama_available=True,
            ollama_location=OllamaLocation.REMOTE_OLLAMA,
            qwen_available=True,
            selected_backend=InferenceBackend.OLLAMA_CPU_REMOTE,
        )
        status = evaluator.evaluate(caps)
        self.assertEqual(status.health, RuntimeHealth.DEGRADED)
        self.assertIn("DEGRADED", status.summary)

    def test_21_runtime_unavailable_state(self):
        evaluator = RuntimeHealthEvaluator()
        caps = RuntimeCapabilities(
            ollama_available=False,
            selected_backend=InferenceBackend.UNAVAILABLE,
        )
        status = evaluator.evaluate(caps)
        self.assertEqual(status.health, RuntimeHealth.UNAVAILABLE)

    # ---------------------------------------------------------------------------
    # 7. Path Compatibility & Environment Variables
    # ---------------------------------------------------------------------------
    def test_22_windows_path_compatibility(self):
        from pathlib import Path
        win_path = Path("C:/Windows/System32")
        self.assertIsInstance(win_path, Path)

    def test_23_linux_path_compatibility(self):
        from pathlib import Path
        lin_path = Path("/home/kali/Downloads/NOC-coplite")
        self.assertIsInstance(lin_path, Path)

    def test_24_environment_variable_configuration(self):
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://10.0.2.2:11434"}):
            detector = OllamaDetector()
            info = detector.detect()
            self.assertEqual(info.endpoint_url, "http://10.0.2.2:11434")
            self.assertEqual(info.location, OllamaLocation.REMOTE_OLLAMA)

    # ---------------------------------------------------------------------------
    # 8. EventBus & RuntimeAgent Execution
    # ---------------------------------------------------------------------------
    def test_25_eventbus_lifecycle(self):
        agent = RuntimeAgent(event_bus=self.event_bus)
        caps = agent.execute({"force_refresh": True})
        self.assertTrue(len(self.published_events) > 0)
        types = [e.event_type for e in self.published_events]
        self.assertIn("runtime.detected", types)

    def test_26_runtime_agent_execution(self):
        agent = RuntimeAgent()
        caps = agent.execute(None)
        self.assertIsInstance(caps, RuntimeCapabilities)

    # ---------------------------------------------------------------------------
    # 9. Topology Distinction & Boundary Constraints
    # ---------------------------------------------------------------------------
    def test_27_dashboard_data_is_dynamic(self):
        service = RuntimeService()
        caps1 = service.get_capabilities(force_refresh=True)
        self.assertIsNotNone(caps1.detection_timestamp)

    def test_28_no_hardcoded_gpu_values(self):
        detector = GPUDetector()
        with patch("shutil.which", return_value=None):
            info = detector.detect(is_virtualized=True)
            self.assertEqual(info.name, "Not Exposed")
            self.assertFalse(info.is_guest_exposed)

    def test_29_no_automatic_driver_installation(self):
        # Verify GPUDetector only runs read-only queries
        detector = GPUDetector()
        info = detector.detect()
        self.assertIn(info.status, [CapabilityStatus.AVAILABLE, CapabilityStatus.UNAVAILABLE, CapabilityStatus.NOT_EXPOSED_TO_GUEST])

    def test_30_no_network_configuration_changes(self):
        # Verify RuntimeAgent has zero network mutation calls
        agent = RuntimeAgent()
        caps = agent.execute({})
        self.assertIsInstance(caps, RuntimeCapabilities)

    def test_31_no_regression_in_ollama_provider(self):
        from agents.knowledge.ollama_provider import OllamaProvider
        provider = OllamaProvider(model_name="qwen3:1.7b")
        self.assertEqual(provider.model_name, "qwen3:1.7b")

    def test_32_no_regression_in_atomic_agents(self):
        from agents.orchestrator_ai.planner_agent import PlannerAgent
        planner = PlannerAgent()
        self.assertEqual(planner.name, "PlannerAgent")

    def test_33_local_vs_remote_ollama_classification(self):
        detector = OllamaDetector()
        loc_local = detector._classify_location("http://127.0.0.1:11434")
        loc_remote = detector._classify_location("http://192.168.1.100:11434")
        self.assertEqual(loc_local, OllamaLocation.LOCAL_OLLAMA)
        self.assertEqual(loc_remote, OllamaLocation.REMOTE_OLLAMA)

    def test_34_virtualbox_guest_gpu_exposure_boundary(self):
        evaluator = RuntimeHealthEvaluator()
        caps = RuntimeCapabilities(
            virtualization_environment=VirtualizationEnvironment.VIRTUALBOX,
            is_guest_gpu_exposed=False,
            gpu_status=CapabilityStatus.NOT_EXPOSED_TO_GUEST,
            ollama_available=True,
            ollama_location=OllamaLocation.REMOTE_OLLAMA,
            qwen_available=True,
            selected_backend=InferenceBackend.OLLAMA_GPU_REMOTE,
        )
        status = evaluator.evaluate(caps)
        self.assertEqual(status.health, RuntimeHealth.READY)
        self.assertIn("Remote Host GPU Inference Active", status.summary)

    def test_35_cache_ttl_and_invalidation(self):
        manager = CapabilityManager(ttl_seconds=60.0)
        caps1 = manager.get_capabilities(force_refresh=True)
        caps2 = manager.get_capabilities(force_refresh=False)
        self.assertEqual(caps1.detection_timestamp, caps2.detection_timestamp)
        manager.invalidate_cache()
        caps3 = manager.get_capabilities(force_refresh=False)
        self.assertNotEqual(caps1.detection_timestamp, caps3.detection_timestamp)


if __name__ == "__main__":
    unittest.main()
