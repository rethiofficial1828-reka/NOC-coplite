"""
Timing Utilities for Atomic Agent Framework.

Provides high-precision timing measurement utilities for agent execution metrics.
"""

import time
from typing import Callable, Tuple, TypeVar, Any

T = TypeVar("T")


class ExecutionTimer:
    """Context manager for measuring execution time in milliseconds."""

    def __init__(self) -> None:
        self.start_time: float = 0.0
        self.end_time: float = 0.0
        self.elapsed_ms: float = 0.0

    def __enter__(self) -> "ExecutionTimer":
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.end_time = time.perf_counter()
        self.elapsed_ms = (self.end_time - self.start_time) * 1000.0


def measure_execution_time(func: Callable[..., T], *args: Any, **kwargs: Any) -> Tuple[T, float]:
    """
    Execute a callable and return the result along with execution duration in ms.

    Args:
        func: Callable to execute.
        *args: Positional arguments for func.
        **kwargs: Keyword arguments for func.

    Returns:
        Tuple of (result, execution_duration_ms).
    """
    timer = ExecutionTimer()
    with timer:
        result = func(*args, **kwargs)
    return result, timer.elapsed_ms
