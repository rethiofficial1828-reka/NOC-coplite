"""
Retrieval Cache Module.

Implements an enterprise LRU/TTL cache for storing retrieval results and query embeddings.
Includes cache hit/miss statistics, query hashing, and invalidation rules.
"""

from collections import OrderedDict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import threading
from typing import Any, Dict, List, Optional, Tuple

from agents.core.logger import get_agent_logger
from agents.rag.models import RetrievalResult

logger = get_agent_logger("RetrievalCache")


class CacheEntry:
    """Internal cache item storing data, expiry time, and metadata."""

    def __init__(self, key: str, value: Any, ttl_seconds: float) -> None:
        self.key = key
        self.value = value
        self.created_at = datetime.now(timezone.utc)
        self.expires_at = self.created_at + timedelta(seconds=ttl_seconds)

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at


class RetrievalCache:
    """
    Thread-safe LRU/TTL cache for retrieval queries and context results.
    """

    def __init__(self, max_entries: int = 500, default_ttl_seconds: float = 300.0) -> None:
        self._max_entries = max_entries
        self._default_ttl_seconds = default_ttl_seconds
        self._lock = threading.RLock()

        # Cache store (LRU ordered dict)
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()

        # Metrics
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, query: str, metadata_filter: Optional[Dict[str, Any]] = None) -> Optional[List[RetrievalResult]]:
        """
        Retrieve cached RetrievalResult list if available and unexpired.
        """
        key = self._hash_key(query, metadata_filter)

        with self._lock:
            if key not in self._store:
                self._misses += 1
                return None

            entry = self._store[key]

            if entry.is_expired():
                del self._store[key]
                self._misses += 1
                logger.debug(f"Cache expired for query key '{key[:8]}...'.")
                return None

            # Move to end (LRU hit)
            self._store.move_to_end(key)
            self._hits += 1
            logger.debug(f"Cache hit for query key '{key[:8]}...'.")
            return entry.value

    def set(
        self,
        query: str,
        results: List[RetrievalResult],
        metadata_filter: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[float] = None,
    ) -> None:
        """
        Cache a query result with TTL and LRU eviction.
        """
        key = self._hash_key(query, metadata_filter)
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl_seconds

        with self._lock:
            if key in self._store:
                del self._store[key]
            elif len(self._store) >= self._max_entries:
                # Evict oldest entry (LRU)
                oldest_key, _ = self._store.popitem(last=False)
                self._evictions += 1
                logger.debug(f"Evicted cache entry '{oldest_key[:8]}...'.")

            self._store[key] = CacheEntry(key=key, value=results, ttl_seconds=ttl)

    def invalidate(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._store.clear()
            logger.info("Cleared all RetrievalCache entries.")

    def get_statistics(self) -> Dict[str, Any]:
        """Return cache performance statistics."""
        with self._lock:
            total = self._hits + self._misses
            hit_ratio = (self._hits / total) if total > 0 else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_ratio": round(hit_ratio, 4),
                "evictions": self._evictions,
                "cached_entries": len(self._store),
                "max_entries": self._max_entries,
            }

    @staticmethod
    def _hash_key(query: str, metadata_filter: Optional[Dict[str, Any]]) -> str:
        """Generate a SHA-256 hash key from query and filter dictionary."""
        raw = f"q:{query.strip().lower()}|m:{json.dumps(metadata_filter or {}, sort_keys=True)}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
