# Enterprise Air-Gapped Federated Incident Intelligence & Signed Knowledge Exchange (`agents/federated_intelligence/`)

## 1. Subsystem Architecture & Operational Loop

The `agents/federated_intelligence/` subsystem enables isolated NOC Copilot deployments to exchange anonymized, privacy-preserved, cryptographically signed incident intelligence without cloud connectivity, raw telemetry leaks, or secret exposure:

$$\text{Local Incident} \rightarrow \text{Privacy Sanitization} \rightarrow \text{Crypto Signing} \rightarrow \text{Offline Export} \rightarrow \text{Offline Import} \rightarrow \text{Signature Verification} \rightarrow \text{RAG Indexing} \rightarrow \text{Enhanced Matching}$$

```
+---------------------------------------------------------------------------------------------------+
|                           FederatedIntelligenceAgent (Atomic Agent)                               |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
|                                   FederatedIntelligenceService                                    |
+---------------------------------------------------------------------------------------------------+
    |                   |                     |                    |                    |
    v                   v                     v                    v                    v
  Privacy             Crypto                Bundle               Bundle             Federated
 Sanitizer            Signer               Exporter             Importer          Knowledge Base
  (PII)            (HMAC/RSA)            (Offline JSON)       (Verification)       (RAG Indexing)
```

---

## 2. Component Reference

### `PrivacySanitizer` (`privacy_sanitizer.py`)
Applies deterministic regex-based scrubbing to strip IP addresses, MAC addresses, hostnames, device IDs, credentials, passwords, tokens, and customer metadata while preserving generic structural network signals (`WAN_LINK_CONGESTION`, `LATENCY_SPIKE_195MS`, `XGBOOST_RISK_SPIKE`).

### `CryptoSigner` (`crypto_signer.py`)
Calculates and verifies HMAC-SHA256 / SHA256 cryptographic signatures over canonicalized JSON bundle content. Detects payload tampering or invalid signing keys.

### `BundleExporter` (`bundle_exporter.py`)
Assembles sanitized incident patterns into cryptographically signed JSON/ZIP knowledge bundles (`.nockb` / `.json`), validates zero PII retention, and exports payloads for air-gapped USB/file transfer.

### `BundleImporter` (`bundle_importer.py`)
Ingests, validates, and audits imported external knowledge bundles. Performs multi-stage cryptographic signature verification, schema validation, and strict PII privacy audit prior to permitting local RAG/VectorStore ingestion.

### `FederatedKnowledgeBaseManager` (`federated_knowledge_base.py`)
Indexes verified anonymized patterns into the local RAG / VectorStore knowledge base (`data/federated_knowledge_index.json`), allowing local incident reasoning to match incoming symptoms against federated cross-site operational patterns.

### `FederatedIntelligenceService` (`federated_intelligence_service.py`)
Domain orchestration service coordinating sanitization, signing, export, import, verification, and RAG knowledge base integration.

### `FederatedIntelligenceAgent` (`federated_intelligence_agent.py`)
Atomic Agent wrapping `FederatedIntelligenceService` within NOC Copilot agent framework. Subscribes to and publishes EventBus lifecycle topics.

---

## 3. Air-Gap & Security Boundaries

> [!CAUTION]
> **Strict Privacy & Zero-Data-Leakage Guarantee**:
> Raw operational telemetry, topology secrets, router credentials, and PII can **NEVER** leave the local security boundary. All exported payloads undergo mandatory privacy audit before cryptographic signing.
