"""Error handling utilities for Burrow MCP.

Provides structured error types and utilities for consistent error handling
across the MCP server with actionable recovery suggestions.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Categories of errors for appropriate handling."""

    TIMEOUT = "timeout"
    DEVICE_OFFLINE = "device_offline"
    DEVICE_NOT_FOUND = "device_not_found"
    INVALID_INPUT = "invalid_input"
    API_ERROR = "api_error"
    RATE_LIMITED = "rate_limited"
    CIRCUIT_OPEN = "circuit_open"
    INTERNAL_ERROR = "internal_error"


@dataclass
class ToolError:
    """Structured error response for MCP tools."""

    category: ErrorCategory
    message: str
    device_id: str | None = None
    request_id: str | None = None
    recovery: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to response dict."""
        result: dict[str, Any] = {
            "error": self.message,
            "error_category": self.category.value,
        }
        if self.request_id:
            result["request_id"] = self.request_id
        if self.device_id:
            result["device_id"] = self.device_id
        if self.recovery:
            result["recovery"] = self.recovery
        if self.details:
            result["details"] = self.details
        return result


# Recovery suggestions for different error types
RECOVERY_SUGGESTIONS = {
    ErrorCategory.TIMEOUT: "Device may be unresponsive. Check network connectivity and try again.",
    ErrorCategory.DEVICE_OFFLINE: "Device is offline. Check power and network connection.",
    ErrorCategory.DEVICE_NOT_FOUND: "Use 'list_devices' to see available devices.",
    ErrorCategory.INVALID_INPUT: "Check parameter values and try again.",
    ErrorCategory.API_ERROR: "External API error. Try again in a moment.",
    ErrorCategory.RATE_LIMITED: "Too many requests. Wait 30 seconds before retrying.",
    ErrorCategory.CIRCUIT_OPEN: "Device temporarily unavailable due to repeated failures. Will retry automatically.",
    ErrorCategory.INTERNAL_ERROR: "An unexpected error occurred. Please try again.",
}


def get_recovery_suggestion(category: ErrorCategory) -> str:
    """Get recovery suggestion for an error category."""
    return RECOVERY_SUGGESTIONS.get(category, "Please try again.")


class DeviceOfflineError(Exception):
    """Raised when a device is offline."""

    def __init__(self, device_id: str, message: str | None = None):
        self.device_id = device_id
        super().__init__(message or f"Device {device_id} is offline")


class DeviceTimeoutError(Exception):
    """Raised when a device operation times out."""

    def __init__(self, device_id: str, operation: str, timeout: float):
        self.device_id = device_id
        self.operation = operation
        self.timeout = timeout
        super().__init__(
            f"Device {device_id} timed out during {operation} after {timeout}s"
        )


class RateLimitedError(Exception):
    """Raised when rate limited by an API."""

    def __init__(self, service: str, retry_after: float | None = None):
        self.service = service
        self.retry_after = retry_after
        msg = f"Rate limited by {service}"
        if retry_after:
            msg += f". Retry after {retry_after}s"
        super().__init__(msg)


def generate_request_id() -> str:
    """Generate a short unique request ID for tracing."""
    return str(uuid.uuid4())[:8]


def classify_exception(e: Exception, device_id: str | None = None) -> ToolError:
    """Classify an exception into a structured error.

    Args:
        e: The exception to classify
        device_id: Optional device ID for context

    Returns:
        ToolError with appropriate category and recovery suggestion
    """
    # Import here to avoid circular imports
    from utils.retry import CircuitBreakerOpen

    if isinstance(e, asyncio.TimeoutError):
        category = ErrorCategory.TIMEOUT
        message = "Operation timed out"
        if device_id:
            message = f"Device {device_id} operation timed out"
    elif isinstance(e, DeviceTimeoutError):
        category = ErrorCategory.TIMEOUT
        message = str(e)
        device_id = e.device_id
    elif isinstance(e, DeviceOfflineError):
        category = ErrorCategory.DEVICE_OFFLINE
        message = str(e)
        device_id = e.device_id
    elif isinstance(e, RateLimitedError):
        category = ErrorCategory.RATE_LIMITED
        message = str(e)
    elif isinstance(e, CircuitBreakerOpen):
        category = ErrorCategory.CIRCUIT_OPEN
        message = "Device temporarily unavailable due to repeated failures"
        if device_id:
            message = f"Device {device_id} temporarily unavailable due to repeated failures"
    elif isinstance(e, ValueError):
        category = ErrorCategory.INVALID_INPUT
        message = str(e)
    elif isinstance(e, RuntimeError):
        error_str = str(e).lower()
        if "not connected" in error_str or "circuit breaker" in error_str:
            category = ErrorCategory.DEVICE_OFFLINE
        else:
            category = ErrorCategory.INTERNAL_ERROR
        message = str(e)
    elif isinstance(e, ConnectionError):
        category = ErrorCategory.API_ERROR
        message = f"Connection error: {e}"
    else:
        category = ErrorCategory.INTERNAL_ERROR
        message = f"Unexpected error: {e}"

    return ToolError(
        category=category,
        message=message,
        device_id=device_id,
        recovery=get_recovery_suggestion(category),
    )


# Default timeouts
DEFAULT_HANDLER_TIMEOUT = 15.0  # Total time for handler execution
DEFAULT_DEVICE_TIMEOUT = 10.0  # Time for individual device operations
DEFAULT_API_TIMEOUT = 10.0  # Time for external API calls


async def execute_with_timeout(
    coro: Any,
    timeout: float = DEFAULT_DEVICE_TIMEOUT,
    device_id: str | None = None,
    operation: str = "operation",
) -> Any:
    """Execute a coroutine with a timeout.

    Args:
        coro: Coroutine to execute
        timeout: Timeout in seconds
        device_id: Optional device ID for error context
        operation: Operation name for error messages

    Returns:
        Result of the coroutine

    Raises:
        DeviceTimeoutError: If the operation times out
    """
    try:
        async with asyncio.timeout(timeout):
            return await coro
    except asyncio.TimeoutError:
        if device_id:
            raise DeviceTimeoutError(device_id, operation, timeout)
        raise
