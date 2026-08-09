# NOC Copilot Enterprise Runtime & Hardware Acceleration Subsystem (`agents/runtime/`)

## Overview

The `agents/runtime/` subsystem provides NOC Copilot with cross-platform environment discovery, virtualization detection, safe NVIDIA GPU/CUDA hardware inspection, Ollama LLM endpoint discovery, deterministic inference backend selection, and runtime health tracking.

It ensures NOC Copilot operates cleanly across:
1. Native Windows Host (with physical NVIDIA GPU acceleration)
2. Native Linux Host (with physical NVIDIA GPU acceleration)
3. Kali Linux (Native or VirtualBox Guest)
4. Virtualized VM environments (VirtualBox, VMware, WSL, Docker)
5. CPU-only hosts and network-bridged remote Ollama hosts

---

## Key Domain Enums & Models

- **`OperatingSystem`**: `WINDOWS`, `LINUX`, `MACOS`, `UNKNOWN`
- **`VirtualizationEnvironment`**: `NATIVE`, `VIRTUALBOX`, `VMWARE`, `WSL`, `DOCKER`, `UNKNOWN`
- **`GPUVendor`**: `NVIDIA`, `AMD`, `INTEL`, `NONE`, `UNKNOWN`
- **`CapabilityStatus`**: `AVAILABLE`, `UNAVAILABLE`, `NOT_EXPOSED_TO_GUEST`, `UNKNOWN`
- **`OllamaLocation`**: `LOCAL_OLLAMA`, `REMOTE_OLLAMA`, `UNAVAILABLE`
- **`InferenceBackend`**: `OLLAMA_GPU_LOCAL`, `OLLAMA_GPU_REMOTE`, `OLLAMA_CPU_LOCAL`, `OLLAMA_CPU_REMOTE`, `LOCAL_CPU`, `UNAVAILABLE`
- **`RuntimeHealth`**: `READY`, `DEGRADED`, `UNAVAILABLE`

---

## Topology & Execution Matrix

### Scenario 1: Native Windows Host
- **Host**: Windows 11 + NVIDIA RTX 4050 6GB + Ollama + Qwen3:1.7B
- **Guest GPU Status**: `AVAILABLE` (`NVIDIA RTX 4050 Laptop GPU`)
- **Ollama Location**: `LOCAL_OLLAMA` (`http://127.0.0.1:11434`)
- **Inference Backend**: `OLLAMA_GPU_LOCAL`
- **Health**: `READY`

### Scenario 2: Kali Linux VirtualBox Guest (Development Setup)
- **Host**: Windows 11 Host running Ollama (`qwen3:1.7b`)
- **Guest VM**: Kali Linux VirtualBox VM running NOC Copilot
- **Guest GPU Status**: `NOT_EXPOSED_TO_GUEST` (Local `nvidia-smi` unavailable)
- **Ollama Location**: `REMOTE_OLLAMA` (e.g. `http://10.0.2.2:11434` or network bridge)
- **Inference Backend**: `OLLAMA_GPU_REMOTE` (or `OLLAMA_CPU_REMOTE`)
- **Health**: `DEGRADED` (*"Physical NVIDIA GPU is not exposed to VirtualBox guest VM; utilizing remote host Ollama endpoint."*)

### Scenario 3: Native Linux Host
- **Host**: Linux / Kali Native + NVIDIA GPU + Ollama
- **Guest GPU Status**: `AVAILABLE`
- **Inference Backend**: `OLLAMA_GPU_LOCAL`
- **Health**: `READY`

---

## Atomic Agent Philosophy & Safety Boundaries

`RuntimeAgent` inherits `BaseAgent` and strictly adheres to Atomic Agent principles:
- **Read-Only Operations Only**: Executes non-privileged subprocess checks (`nvidia-smi` with strict timeouts) and HTTP GET probes (`/api/version`, `/api/tags`).
- **No Driver Modification**: Never attempts to install drivers or modify OS registry/kernel modules.
- **No Network Mutation**: NEVER modifies network configuration, router CLI parameters, SSH tunnels, or firewall rules.
- **EventBus Integration**: Publishes structured events (`runtime.detected`, `runtime.gpu.detected`, `runtime.ollama.detected`, `runtime.model.detected`, `runtime.inference.selected`, `runtime.degraded`, `runtime.health.changed`).
