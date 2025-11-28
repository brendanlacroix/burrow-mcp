"""Rate limiting utilities for Burrow MCP.

Provides rate limiting for API calls to prevent hitting service limits.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""

    requests_per_minute: int = 30
    burst_size: int = 5
    retry_after_rate_limit: float = 30.0


class TokenBucketRateLimiter:
    """Token bucket rate limiter for API calls.

    Uses the token bucket algorithm to allow bursts while maintaining
    a steady rate over time.
    """

    def __init__(
        self,
        requests_per_minute: int = 30,
        burst_size: int | None = None,
    ):
        """Initialize rate limiter.

        Args:
            requests_per_minute: Maximum sustained requests per minute
            burst_size: Maximum burst size (defaults to requests_per_minute / 6)
        """
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size or max(1, requests_per_minute // 6)
        self.tokens = float(self.burst_size)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

        # Calculate refill rate (tokens per second)
        self.refill_rate = requests_per_minute / 60.0

    async def acquire(self, tokens: int = 1) -> float:
        """Acquire tokens, waiting if necessary.

        Args:
            tokens: Number of tokens to acquire

        Returns:
            Time waited in seconds
        """
        async with self._lock:
            wait_time = 0.0
            now = time.monotonic()

            # Refill tokens based on elapsed time
            elapsed = now - self.last_update
            self.tokens = min(
                self.burst_size,
                self.tokens + elapsed * self.refill_rate
            )
            self.last_update = now

            # Calculate wait time if not enough tokens
            if self.tokens < tokens:
                deficit = tokens - self.tokens
                wait_time = deficit / self.refill_rate
                logger.debug(
                    f"Rate limiter: waiting {wait_time:.2f}s "
                    f"(tokens: {self.tokens:.1f}, need: {tokens})"
                )
                await asyncio.sleep(wait_time)
                # After waiting, we should have enough tokens
                self.tokens = tokens
                self.last_update = time.monotonic()

            self.tokens -= tokens
            return wait_time

    async def try_acquire(self, tokens: int = 1) -> bool:
        """Try to acquire tokens without waiting.

        Args:
            tokens: Number of tokens to acquire

        Returns:
            True if tokens were acquired, False otherwise
        """
        async with self._lock:
            now = time.monotonic()

            # Refill tokens
            elapsed = now - self.last_update
            self.tokens = min(
                self.burst_size,
                self.tokens + elapsed * self.refill_rate
            )
            self.last_update = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False


class ServiceRateLimiter:
    """Rate limiter for multiple services/endpoints.

    Manages separate rate limiters for different services or API endpoints.
    """

    def __init__(self, default_rpm: int = 30):
        """Initialize service rate limiter.

        Args:
            default_rpm: Default requests per minute for new services
        """
        self.default_rpm = default_rpm
        self._limiters: dict[str, TokenBucketRateLimiter] = {}
        self._configs: dict[str, RateLimitConfig] = {}

    def configure_service(
        self,
        service: str,
        requests_per_minute: int,
        burst_size: int | None = None,
    ) -> None:
        """Configure rate limiting for a specific service.

        Args:
            service: Service identifier
            requests_per_minute: Maximum sustained requests per minute
            burst_size: Maximum burst size
        """
        self._limiters[service] = TokenBucketRateLimiter(
            requests_per_minute=requests_per_minute,
            burst_size=burst_size,
        )
        self._configs[service] = RateLimitConfig(
            requests_per_minute=requests_per_minute,
            burst_size=burst_size or max(1, requests_per_minute // 6),
        )
        logger.info(
            f"Configured rate limiter for {service}: "
            f"{requests_per_minute} RPM, burst={burst_size or 'auto'}"
        )

    def get_limiter(self, service: str) -> TokenBucketRateLimiter:
        """Get rate limiter for a service, creating if needed.

        Args:
            service: Service identifier

        Returns:
            Rate limiter for the service
        """
        if service not in self._limiters:
            self._limiters[service] = TokenBucketRateLimiter(
                requests_per_minute=self.default_rpm
            )
        return self._limiters[service]

    async def acquire(self, service: str, tokens: int = 1) -> float:
        """Acquire tokens for a service.

        Args:
            service: Service identifier
            tokens: Number of tokens to acquire

        Returns:
            Time waited in seconds
        """
        limiter = self.get_limiter(service)
        return await limiter.acquire(tokens)


# Global rate limiter instance for API services
_service_rate_limiter: ServiceRateLimiter | None = None


def get_service_rate_limiter() -> ServiceRateLimiter:
    """Get the global service rate limiter instance."""
    global _service_rate_limiter
    if _service_rate_limiter is None:
        _service_rate_limiter = ServiceRateLimiter()
        # Configure known services with their rate limits
        _service_rate_limiter.configure_service("govee", requests_per_minute=30, burst_size=5)
        _service_rate_limiter.configure_service("august", requests_per_minute=20, burst_size=3)
        _service_rate_limiter.configure_service("ring", requests_per_minute=20, burst_size=3)
    return _service_rate_limiter


def rate_limited(service: str):
    """Decorator for rate-limited async functions.

    Args:
        service: Service identifier for rate limiting

    Returns:
        Decorated function
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            limiter = get_service_rate_limiter()
            wait_time = await limiter.acquire(service)
            if wait_time > 0:
                logger.debug(f"Rate limited {func.__name__}: waited {wait_time:.2f}s")
            return await func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator
