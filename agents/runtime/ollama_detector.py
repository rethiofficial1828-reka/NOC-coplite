"""
Ollama Service Endpoint and GPU Offloading Discovery Detector.

Probes Ollama service connectivity, version, endpoint location (LOCAL vs REMOTE),
and queries running model offload details.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional, Tuple

from agents.runtime.runtime_models import (
    OllamaInfo,
    OllamaLocation,
)
from config.settings import OLLAMA_BASE_URL, OLLAMA_MODEL


class OllamaDetector:
    """
    Detector for discovering Ollama LLM endpoint availability and location.
    """

    def __init__(self, default_url: Optional[str] = None, timeout_sec: float = 3.0) -> None:
        url = default_url or os.environ.get("OLLAMA_BASE_URL", OLLAMA_BASE_URL)
        self._default_url = url.rstrip("/")
        self._timeout_sec = timeout_sec

    def detect(self, target_url: Optional[str] = None) -> OllamaInfo:
        """
        Probe specified or configured Ollama URL.

        Args:
            target_url: Optional override endpoint URL.
        """
        url = (target_url or self._default_url).rstrip("/")
        location = self._classify_location(url)

        try:
            # Probe version endpoint
            version_url = f"{url}/api/version"
            req = urllib.request.Request(version_url, headers={"User-Agent": "NOC-Copilot/1.0"})
            with urllib.request.urlopen(req, timeout=self._timeout_sec) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                version_str = data.get("version", "Active")

            # Probe tags endpoint for qwen3:1.7b presence
            qwen_present, remote_gpu = self._probe_models_and_gpu(url)

            return OllamaInfo(
                available=True,
                location=location,
                endpoint_url=url,
                version=version_str,
                qwen_available=qwen_present,
                qwen_model_tag=OLLAMA_MODEL,
                remote_gpu_accelerated=remote_gpu,
            )
        except urllib.error.URLError as e:
            return OllamaInfo(
                available=False,
                location=OllamaLocation.UNAVAILABLE,
                endpoint_url=url,
                version="Unavailable",
                qwen_available=False,
                qwen_model_tag=OLLAMA_MODEL,
                error_message=f"Connection failed: {e.reason if hasattr(e, 'reason') else str(e)}",
            )
        except Exception as e:
            return OllamaInfo(
                available=False,
                location=OllamaLocation.UNAVAILABLE,
                endpoint_url=url,
                version="Unavailable",
                qwen_available=False,
                qwen_model_tag=OLLAMA_MODEL,
                error_message=str(e),
            )

    def _classify_location(self, url: str) -> OllamaLocation:
        """Classify endpoint as LOCAL_OLLAMA or REMOTE_OLLAMA based on URL host."""
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        if host in ("127.0.0.1", "localhost", "0.0.0.0", "::1"):
            return OllamaLocation.LOCAL_OLLAMA
        return OllamaLocation.REMOTE_OLLAMA

    def _probe_models_and_gpu(self, base_url: str) -> Tuple[bool, bool]:
        """
        Check for target Qwen3:1.7B model and probe if remote Ollama is GPU offloading.
        """
        tags_url = f"{base_url}/api/tags"
        qwen_found = False
        remote_gpu = False

        try:
            req = urllib.request.Request(tags_url, headers={"User-Agent": "NOC-Copilot/1.0"})
            with urllib.request.urlopen(req, timeout=self._timeout_sec) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = data.get("models", [])
                for m in models:
                    name = m.get("name", "").lower()
                    if "qwen3:1.7b" in name or "qwen3" in name or "qwen" in name:
                        qwen_found = True
                    # Check details for GPU layer offload indicators
                    details = m.get("details", {})
                    if details.get("parameter_size") or m.get("size"):
                        # If running on remote host with model loaded, assume active server capability
                        remote_gpu = True

            # Also check running processes / models via /api/ps if supported
            try:
                ps_url = f"{base_url}/api/ps"
                req_ps = urllib.request.Request(ps_url, headers={"User-Agent": "NOC-Copilot/1.0"})
                with urllib.request.urlopen(req_ps, timeout=self._timeout_sec) as resp_ps:
                    ps_data = json.loads(resp_ps.read().decode("utf-8"))
                    running = ps_data.get("models", [])
                    for rm in running:
                        size_vram = rm.get("size_vram", 0)
                        if size_vram > 0:
                            remote_gpu = True
            except Exception:
                pass

        except Exception:
            pass

        return qwen_found, remote_gpu
