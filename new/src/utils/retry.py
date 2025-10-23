"""Retry decorator with exponential backoff for async functions."""

import asyncio
import functools
from typing import Callable, TypeVar, Any
from .logger import get_logger
from .errors import TimeoutError

logger = get_logger(__name__)

T = TypeVar('T')


def retry_async(
    max_attempts: int = 3,
    backoff_factor: float = 2.0,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: tuple = (Exception,)
):
    """
    Retry an async function with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts
        backoff_factor: Multiplier for delay between retries
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exceptions: Tuple of exceptions to catch and retry
        
    Returns:
        Decorated function
        
    Example:
        @retry_async(max_attempts=3, backoff_factor=2)
        async def flaky_function():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            delay = initial_delay
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                    
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_attempts:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts",
                            extra={
                                "function": func.__name__,
                                "attempts": max_attempts,
                                "error": str(e),
                            }
                        )
                        raise
                    
                    logger.warning(
                        f"{func.__name__} attempt {attempt}/{max_attempts} failed, retrying...",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt,
                            "max_attempts": max_attempts,
                            "delay_seconds": delay,
                            "error": str(e),
                        }
                    )
                    
                    await asyncio.sleep(delay)
                    delay = min(delay * backoff_factor, max_delay)
            
            # Should never reach here, but just in case
            raise last_exception
        
        return wrapper
    return decorator


async def timeout_async(coro, seconds: float):
    """
    Run an async coroutine with a timeout.
    
    Args:
        coro: Coroutine to run
        seconds: Timeout in seconds
        
    Returns:
        Result of the coroutine
        
    Raises:
        TimeoutError: If timeout is exceeded
    """
    try:
        return await asyncio.wait_for(coro, timeout=seconds)
    except asyncio.TimeoutError:
        raise TimeoutError(f"Operation timed out after {seconds} seconds")