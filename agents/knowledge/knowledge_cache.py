"""
Knowledge Cache Module.

Thread-safe in-memory caching mechanism for KnowledgeResult objects with TTL expiration support.
"""

import threading
from typing import Dict, Optional

from agents.knowledge.knowledge_models import KnowledgeCacheEntry, KnowledgeResult


class KnowledgeCache:
    """
    Thread-safe in-memory cache for storing and retrieving KnowledgeResult objects.
    """

    def __init__(self, default_ttl_seconds: float = 3600.0) -> None:
        """
        Initialize KnowledgeCache.

        Args:
            default_ttl_seconds: Default Time-To-Live in seconds (default 1 hour).
        """
        self._cache: Dict[str, KnowledgeCacheEntry] = {}
        self._default_ttl = default_ttl_seconds
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[KnowledgeResult]:
        """
        Retrieve a cached KnowledgeResult by key if not expired.

        Args:
            key: Cache key string.

        Returns:
            KnowledgeResult object or None if missing/expired.
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            if entry.is_expired():
                del self._cache[key]
                return None

            return entry.result

    def set(self, key: str, result: KnowledgeResult, ttl_seconds: Optional[float] = None) -> None:
        """
        Store a KnowledgeResult in cache.

        Args:
            key: Cache key string.
            result: KnowledgeResult object.
            ttl_seconds: Optional TTL override in seconds.
        """
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        entry = KnowledgeCacheEntry(cache_key=key, result=result, ttl_seconds=ttl)
        with self._lock:
            self._cache[key] = entry

    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        """Return current cache size."""
        with self._lock:
            return len(self._cache)
