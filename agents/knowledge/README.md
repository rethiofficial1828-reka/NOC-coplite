# NOC Copilot — Knowledge Agent & Subsystem (Sprint 9 — Production Ollama Provider)

## Overview

The `KnowledgeSubsystem` features an enterprise-grade LLM provider layer supporting dynamic provider selection (`MockProvider`, `OllamaProvider`, or future cloud/local models) via `ProviderFactory`. `KnowledgeAgent` depends strictly on the `LLMProvider` abstract interface, keeping model execution, connection retries, and HTTP protocols completely decoupled from business agent logic.

---

## Architecture Diagram

```
+-----------------------------------------------------------------------------------+
|                                EVENT BUS SYSTEM                                   |
|       Listens to 'recommendation.generated' / Emits 'knowledge.generated'         |
|       Lifecycle events: 'provider.initialized', 'provider.failed', 'provider.shutdown'|
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                  AGENT LAYER                                      |
|            KnowledgeAgent (BaseAgent subclass, calls KnowledgeService)            |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                 SERVICE LAYER                                     |
|    KnowledgeService (Orchestrates cache, repository docs, prompt, & provider)     |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                               PROVIDER FACTORY                                    |
|   ProviderFactory.create_provider() -> resolves configured LLMProvider instance   |
+-----------------------------------------------------------------------------------+
     |                                    |                                    |
     v                                    v                                    v
+--------------------+           +--------------------+           +--------------------+
|    MockProvider    |           |   OllamaProvider   |           | FutureProvider...  |
|  (Testing/Offline) |           | (Local Ollama API) |           |  (OpenAI, vLLM...) |
+--------------------+           +--------------------+           +--------------------+
```

---

## Component Layers

### 1. LLMProvider Interface (`agents.knowledge.LLMProvider`)
Abstract interface contract for all inference engines:
- `initialize()`
- `shutdown()`
- `generate(prompt, parameters)`
- `health()`
- `metadata()`

### 2. ProviderFactory (`agents.knowledge.ProviderFactory`)
Central factory reading `LLM_PROVIDER_TYPE` from `ConfigManager` (`'mock'`, `'ollama'`, etc.) or `ServiceContainer`. Supports dynamic registration of custom provider classes via `register_provider_class(type_name, provider_cls)`.

### 3. OllamaProvider (`agents.knowledge.OllamaProvider`)
Production-grade provider connecting to Ollama HTTP server (`/api/generate`, `/api/tags`).
Features:
- Parameterized model execution (`OLLAMA_MODEL`, e.g. `llama3`, `qwen2.5`).
- Connection reuse and HTTP request management.
- Configurable retry policy (`OLLAMA_RETRY_COUNT=3`) with exponential backoff.
- Request timeout handling (`OLLAMA_TIMEOUT_SEC=30.0`).
- Health checks verifying server status and model availability.
- Event publishing: emits `provider.initialized`, `provider.failed`, and `provider.shutdown` on `EventBus`.

### 4. MockProvider (`agents.knowledge.MockProvider`)
Lightweight, deterministic provider returning structured root cause analysis and remediation steps for fast offline unit testing.

---

## Configuration Settings (`ConfigManager`)

| Setting Key | Default Value | Description |
| :--- | :--- | :--- |
| `LLM_PROVIDER_TYPE` | `"mock"` | Provider key (`"mock"` or `"ollama"`) |
| `OLLAMA_BASE_URL` | `"http://localhost:11434"` | Ollama daemon base URL |
| `OLLAMA_MODEL` | `"llama3"` | Target Ollama model name |
| `OLLAMA_TIMEOUT_SEC` | `30.0` | HTTP request timeout in seconds |
| `OLLAMA_RETRY_COUNT` | `3` | Maximum retry attempts for failed requests |
| `OLLAMA_TEMPERATURE` | `0.2` | Generation temperature |
| `OLLAMA_TOP_P` | `0.9` | Top-P sampling parameter |
| `OLLAMA_MAX_TOKENS` | `2048` | Maximum output token count |

---

## Provider Lifecycle Events

- **`provider.initialized`**: Emitted when provider finishes initialization.
- **`provider.failed`**: Emitted when inference retries are exhausted.
- **`provider.shutdown`**: Emitted when provider shuts down.

---

## Developer Guide: Switching Providers

To run NOC Copilot using local Ollama model `llama3`:
```python
from config.config_manager import ConfigManager
from agents.knowledge import ProviderFactory, KnowledgeService

# Set runtime override
ConfigManager.get_instance().set_override("LLM_PROVIDER_TYPE", "ollama")
ConfigManager.get_instance().set_override("OLLAMA_MODEL", "llama3")

# Create KnowledgeService — ProviderFactory automatically instantiates OllamaProvider
service = KnowledgeService()
print(service.provider.metadata())
```
