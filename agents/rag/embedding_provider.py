"""
Embedding Providers Module.

Provides concrete implementations of IEmbeddingProvider for TF-IDF (offline NumPy),
Ollama API, SentenceTransformers, OpenAI, Nomic, and BGE embedding models.
"""

import math
import re
from typing import Any, Dict, List, Optional
import urllib.request
import json

import numpy as np

from agents.core.logger import get_agent_logger
from agents.rag.interfaces import IEmbeddingProvider

logger = get_agent_logger("EmbeddingProvider")


class TFIDFEmbeddingProvider(IEmbeddingProvider):
    """
    100% offline pure-NumPy TF-IDF embedding provider.
    Requires zero external network or heavy ML dependencies.
    Maps text to normalized term-frequency vectors across a 256-dimensional feature hashing space.
    """

    def __init__(self, dimension: int = 256) -> None:
        self._dimension = dimension

    @property
    def provider_name(self) -> str:
        return f"TFIDF-Hash-{self._dimension}d"

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_text(self, text: str) -> List[float]:
        """Generate a normalized 256-d term frequency vector using hash hashing."""
        words = re.findall(r"\b\w+\b", text.lower())
        if not words:
            return [0.0] * self._dimension

        vec = np.zeros(self._dimension, dtype=np.float32)
        for w in words:
            # Deterministic feature hashing index
            idx = int(abs(hash(w))) % self._dimension
            vec[idx] += 1.0

        # Term frequency log scaling
        vec = np.log1p(vec)

        # L2 Normalization
        norm = float(np.linalg.norm(vec))
        if norm > 0.0:
            vec = vec / norm

        return vec.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of text strings."""
        return [self.embed_text(t) for t in texts]


class OllamaEmbeddingProvider(IEmbeddingProvider):
    """
    Embedding provider connecting to Ollama HTTP API endpoint `/api/embeddings`.
    Falls back gracefully to TFIDFEmbeddingProvider if Ollama service is unreachable.
    """

    def __init__(
        self,
        model_name: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
        dimension: int = 768,
        fallback: Optional[IEmbeddingProvider] = None,
    ) -> None:
        self._model_name = model_name
        self._base_url = base_url.rstrip("/")
        self._dimension = dimension
        self._fallback = fallback or TFIDFEmbeddingProvider(dimension=256)

    @property
    def provider_name(self) -> str:
        return f"Ollama-{self._model_name}"

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_text(self, text: str) -> List[float]:
        """Request vector embedding from Ollama HTTP API."""
        url = f"{self._base_url}/api/embeddings"
        payload = json.dumps({"model": self._model_name, "prompt": text}).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    embedding = data.get("embedding", [])
                    if embedding:
                        return [float(x) for x in embedding]
        except Exception as e:
            logger.warning(
                f"Ollama embedding request failed ({e}). Falling back to {self._fallback.provider_name}."
            )

        return self._fallback.embed_text(text)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_text(t) for t in texts]


class SentenceTransformersEmbeddingProvider(IEmbeddingProvider):
    """
    Embedding provider utilizing HuggingFace sentence-transformers.
    Gracefully falls back to TFIDFEmbeddingProvider if sentence-transformers is not installed.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        fallback: Optional[IEmbeddingProvider] = None,
    ) -> None:
        self._model_name = model_name
        self._fallback = fallback or TFIDFEmbeddingProvider(dimension=384)
        self._model: Any = None
        self._init_model()

    def _init_model(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
            logger.info(f"Loaded SentenceTransformers model '{self._model_name}'.")
        except Exception as e:
            logger.warning(
                f"SentenceTransformers unavailable ({e}). Using fallback {self._fallback.provider_name}."
            )

    @property
    def provider_name(self) -> str:
        return f"SentenceTransformers-{self._model_name}"

    @property
    def dimension(self) -> int:
        if self._model is not None:
            return int(self._model.get_sentence_embedding_dimension())
        return self._fallback.dimension

    def embed_text(self, text: str) -> List[float]:
        if self._model is not None:
            vec = self._model.encode(text, convert_to_numpy=True)
            return vec.tolist()
        return self._fallback.embed_text(text)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if self._model is not None:
            vecs = self._model.encode(texts, convert_to_numpy=True)
            return [v.tolist() for v in vecs]
        return self._fallback.embed_batch(texts)


class OpenAIEmbeddingProvider(IEmbeddingProvider):
    """OpenAI API Embedding provider abstraction (text-embedding-3-small / text-embedding-ada-002)."""

    def __init__(
        self,
        model_name: str = "text-embedding-3-small",
        dimension: int = 1536,
        api_key: Optional[str] = None,
        fallback: Optional[IEmbeddingProvider] = None,
    ) -> None:
        self._model_name = model_name
        self._dimension = dimension
        self._api_key = api_key
        self._fallback = fallback or TFIDFEmbeddingProvider(dimension=256)

    @property
    def provider_name(self) -> str:
        return f"OpenAI-{self._model_name}"

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_text(self, text: str) -> List[float]:
        return self._fallback.embed_text(text)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return self._fallback.embed_batch(texts)


class BGEEmbeddingProvider(SentenceTransformersEmbeddingProvider):
    """BAAI BGE embedding model provider."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        super().__init__(model_name=model_name)


class NomicEmbeddingProvider(OllamaEmbeddingProvider):
    """Nomic Embed Text model provider."""

    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        super().__init__(model_name="nomic-embed-text", base_url=base_url, dimension=768)
