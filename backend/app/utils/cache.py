"""
In-memory computation cache.

Caches the dict result of expensive pandas computation functions so that
repeated API requests serve pre-computed results instantly.

Cache key = (function_name, frozen params).
Cache invalidates entirely when GLOBAL_DF changes (tracked by filename).

Usage in an endpoint:

    from app.utils.cache import cached_call

    result = cached_call(
        "compute_stockout_risk",
        ialerts.compute_stockout_risk,
        df_raw_sale=sale, ...,
        window_days=90,
    )
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cache: Dict[str, Tuple[Any, float]] = {}  # key -> (result, timestamp)
_filename: Optional[str] = None  # tracks the current data file


def _make_key(func_name: str, kwargs: dict) -> str:
    """Create a stable cache key from function name + parameters.

    DataFrames are excluded from the key (they are session-global and tracked
    via _filename instead). Only scalar / small params are hashed.
    """
    parts = [func_name]
    for k in sorted(kwargs):
        v = kwargs[k]
        # Skip DataFrames and Timestamps (not part of user-visible params)
        if hasattr(v, "shape") or k.startswith("df_") or k == "as_of":
            continue
        parts.append(f"{k}={v}")
    raw = "|".join(str(p) for p in parts)
    return hashlib.md5(raw.encode()).hexdigest()


def invalidate(new_filename: Optional[str] = None) -> int:
    """Drop all cached entries. Called when GLOBAL_DF reloads.

    Returns the number of entries cleared.
    """
    global _filename
    with _lock:
        count = len(_cache)
        _cache.clear()
        if new_filename is not None:
            _filename = new_filename
        logger.info("Cache invalidated (%d entries cleared, new file: %s)", count, new_filename)
    return count


def cached_call(func_name: str, func: Callable, **kwargs: Any) -> Any:
    """Call *func* with *kwargs*, returning a cached result if available.

    On cache miss the function is called, its result is stored, and the
    result is returned. On cache hit the stored result is returned directly.
    """
    global _filename

    # Check if GLOBAL_DF changed (different filename)
    from app.utils.helper_functions import GLOBAL_DF
    current_file = GLOBAL_DF.get("filename")
    with _lock:
        if current_file != _filename:
            _cache.clear()
            _filename = current_file

    key = _make_key(func_name, kwargs)

    with _lock:
        if key in _cache:
            result, ts = _cache[key]
            return result

    # Cache miss — compute (outside lock to avoid blocking other requests)
    t0 = time.perf_counter()
    result = func(**kwargs)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    with _lock:
        _cache[key] = (result, time.time())

    logger.info("Cache MISS %s — computed in %.0fms (key=%s)", func_name, elapsed_ms, key[:8])
    return result


def stats() -> Dict[str, Any]:
    """Return cache statistics."""
    with _lock:
        return {
            "entries": len(_cache),
            "filename": _filename,
        }
