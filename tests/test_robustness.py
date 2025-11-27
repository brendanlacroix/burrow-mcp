"""Tests for robustness features: errors, timeouts, circuit breakers, rate limiting."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.errors import (
    DEFAULT_DEVICE_TIMEOUT,
    DeviceOfflineError,
    DeviceTimeoutError,
    ErrorCategory,
    RateLimitedError,
    ToolError,
    classify_exception,
    execute_with_timeout,
    generate_request_id,
    get_recovery_suggestion,
)
from utils.rate_limit import ServiceRateLimiter, TokenBucketRateLimiter
from utils.retry import CircuitBreaker, CircuitBreakerOpen, retry_async


class TestErrorClassification:
    """Tests for error classification utilities."""

    def test_classify_timeout_error(self):
        """Test classification of asyncio timeout errors."""
        error = classify_exception(asyncio.TimeoutError())
        assert error.category == ErrorCategory.TIMEOUT
        assert "timed out" in error.message.lower()

    def test_classify_device_timeout_error(self):
        """Test classification of device timeout errors."""
        exc = DeviceTimeoutError("light-1", "set_power", 10.0)
        error = classify_exception(exc)
        assert error.category == ErrorCategory.TIMEOUT
        assert error.device_id == "light-1"
        assert "light-1" in error.message

    def test_classify_device_offline_error(self):
        """Test classification of device offline errors."""
        exc = DeviceOfflineError("light-1")
        error = classify_exception(exc)
        assert error.category == ErrorCategory.DEVICE_OFFLINE
        assert error.device_id == "light-1"

    def test_classify_rate_limited_error(self):
        """Test classification of rate limited errors."""
        exc = RateLimitedError("govee", retry_after=30.0)
        error = classify_exception(exc)
        assert error.category == ErrorCategory.RATE_LIMITED
        assert "govee" in error.message.lower()

    def test_classify_circuit_breaker_open(self):
        """Test classification of circuit breaker errors."""
        exc = CircuitBreakerOpen("test breaker")
        error = classify_exception(exc)
        assert error.category == ErrorCategory.CIRCUIT_OPEN

    def test_classify_value_error(self):
        """Test classification of value errors as invalid input."""
        exc = ValueError("brightness must be 0-100")
        error = classify_exception(exc)
        assert error.category == ErrorCategory.INVALID_INPUT

    def test_classify_connection_error(self):
        """Test classification of connection errors."""
        exc = ConnectionError("failed to connect")
        error = classify_exception(exc)
        assert error.category == ErrorCategory.API_ERROR

    def test_classify_unknown_error(self):
        """Test classification of unknown errors."""
        exc = RuntimeError("something went wrong")
        error = classify_exception(exc)
        assert error.category == ErrorCategory.INTERNAL_ERROR

    def test_classify_with_device_id(self):
        """Test that device_id is passed through in classification."""
        exc = asyncio.TimeoutError()
        error = classify_exception(exc, device_id="my-device")
        assert error.device_id == "my-device"
        assert "my-device" in error.message


class TestToolError:
    """Tests for ToolError class."""

    def test_tool_error_to_dict_minimal(self):
        """Test ToolError serialization with minimal fields."""
        error = ToolError(
            category=ErrorCategory.TIMEOUT,
            message="Operation timed out",
        )
        result = error.to_dict()
        assert result["error"] == "Operation timed out"
        assert result["error_category"] == "timeout"
        assert "request_id" not in result
        assert "device_id" not in result

    def test_tool_error_to_dict_full(self):
        """Test ToolError serialization with all fields."""
        error = ToolError(
            category=ErrorCategory.DEVICE_OFFLINE,
            message="Device is offline",
            device_id="light-1",
            request_id="abc123",
            recovery="Check power connection",
            details={"last_seen": "2024-01-01"},
        )
        result = error.to_dict()
        assert result["error"] == "Device is offline"
        assert result["error_category"] == "device_offline"
        assert result["request_id"] == "abc123"
        assert result["device_id"] == "light-1"
        assert result["recovery"] == "Check power connection"
        assert result["details"]["last_seen"] == "2024-01-01"


class TestRecoverySuggestions:
    """Tests for recovery suggestions."""

    def test_all_categories_have_suggestions(self):
        """Test that all error categories have recovery suggestions."""
        for category in ErrorCategory:
            suggestion = get_recovery_suggestion(category)
            assert suggestion is not None
            assert len(suggestion) > 0


class TestRequestId:
    """Tests for request ID generation."""

    def test_request_id_format(self):
        """Test request ID format."""
        request_id = generate_request_id()
        assert len(request_id) == 8
        # Should be hex characters
        assert all(c in "0123456789abcdef-" for c in request_id)

    def test_request_ids_unique(self):
        """Test that request IDs are unique."""
        ids = [generate_request_id() for _ in range(100)]
        assert len(set(ids)) == 100


class TestExecuteWithTimeout:
    """Tests for execute_with_timeout utility."""

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        """Test successful execution within timeout."""

        async def fast_operation():
            return "success"

        result = await execute_with_timeout(
            fast_operation(),
            timeout=1.0,
            device_id="test-device",
            operation="test",
        )
        assert result == "success"

    @pytest.mark.asyncio
    async def test_timeout_raises_device_timeout_error(self):
        """Test that timeout raises DeviceTimeoutError with device_id."""

        async def slow_operation():
            await asyncio.sleep(10)
            return "never"

        with pytest.raises(DeviceTimeoutError) as exc_info:
            await execute_with_timeout(
                slow_operation(),
                timeout=0.01,
                device_id="test-device",
                operation="test_op",
            )
        assert exc_info.value.device_id == "test-device"
        assert exc_info.value.operation == "test_op"

    @pytest.mark.asyncio
    async def test_timeout_without_device_id(self):
        """Test that timeout without device_id raises raw TimeoutError."""

        async def slow_operation():
            await asyncio.sleep(10)

        with pytest.raises(asyncio.TimeoutError):
            await execute_with_timeout(slow_operation(), timeout=0.01)


class TestCircuitBreaker:
    """Tests for circuit breaker functionality."""

    def test_initial_state_closed(self):
        """Test circuit breaker starts in closed state."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
        assert cb.state == CircuitBreaker.CLOSED
        assert not cb.is_open

    def test_opens_after_threshold_failures(self):
        """Test circuit breaker opens after threshold failures."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)

        for _ in range(3):
            cb.record_failure()

        assert cb.state == CircuitBreaker.OPEN
        assert cb.is_open

    def test_success_resets_failure_count(self):
        """Test that success resets failure count."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)

        cb.record_failure()
        cb.record_failure()
        cb.record_success()

        # Should not be open after success reset
        cb.record_failure()
        cb.record_failure()
        assert not cb.is_open

    def test_reset_method(self):
        """Test manual reset of circuit breaker."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0)

        cb.record_failure()
        cb.record_failure()
        assert cb.is_open

        cb.reset()
        assert not cb.is_open
        assert cb.state == CircuitBreaker.CLOSED


class TestRetryAsync:
    """Tests for async retry functionality."""

    @pytest.mark.asyncio
    async def test_successful_on_first_try(self):
        """Test function succeeds on first try."""
        mock_func = AsyncMock(return_value="success")

        result = await retry_async(mock_func, max_attempts=3, initial_delay=0.01)

        assert result == "success"
        assert mock_func.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure(self):
        """Test function retries on failure."""
        call_count = 0

        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("failed")
            return "success"

        result = await retry_async(
            flaky_func,
            max_attempts=5,
            initial_delay=0.01,
            retryable_exceptions=(ConnectionError,),
        )

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_attempts(self):
        """Test function raises RetryExhausted after max attempts exceeded."""
        from utils.retry import RetryExhausted

        async def always_fails():
            raise ConnectionError("always fails")

        with pytest.raises(RetryExhausted) as exc_info:
            await retry_async(
                always_fails,
                max_attempts=3,
                initial_delay=0.01,
                retryable_exceptions=(ConnectionError,),
            )

        assert exc_info.value.attempts == 3
        assert isinstance(exc_info.value.last_exception, ConnectionError)

    @pytest.mark.asyncio
    async def test_does_not_retry_non_retryable_exceptions(self):
        """Test function does not retry non-retryable exceptions."""
        call_count = 0

        async def raises_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("not retryable")

        with pytest.raises(ValueError):
            await retry_async(
                raises_value_error,
                max_attempts=3,
                initial_delay=0.01,
                retryable_exceptions=(ConnectionError,),  # ValueError not included
            )

        assert call_count == 1  # Should not retry


class TestRateLimiter:
    """Tests for rate limiting functionality."""

    @pytest.mark.asyncio
    async def test_allows_burst(self):
        """Test rate limiter allows burst up to burst_size."""
        limiter = TokenBucketRateLimiter(requests_per_minute=60, burst_size=5)

        # Should allow 5 requests immediately (burst)
        wait_times = []
        for _ in range(5):
            wait_time = await limiter.acquire()
            wait_times.append(wait_time)

        # All should have minimal wait time
        assert all(t < 0.1 for t in wait_times)

    @pytest.mark.asyncio
    async def test_rate_limits_after_burst(self):
        """Test rate limiter enforces rate after burst exhausted."""
        # Very slow rate for testing
        limiter = TokenBucketRateLimiter(requests_per_minute=6, burst_size=2)

        # Exhaust burst
        await limiter.acquire()
        await limiter.acquire()

        # Next request should wait
        wait_time = await limiter.acquire()
        # Should wait approximately 10 seconds at 6 RPM, but we'll check > 0
        assert wait_time > 0

    @pytest.mark.asyncio
    async def test_try_acquire_returns_false_when_no_tokens(self):
        """Test try_acquire returns False when no tokens available."""
        limiter = TokenBucketRateLimiter(requests_per_minute=60, burst_size=1)

        # First should succeed
        assert await limiter.try_acquire() is True
        # Second should fail (no tokens)
        assert await limiter.try_acquire() is False


class TestServiceRateLimiter:
    """Tests for service-based rate limiting."""

    def test_configure_service(self):
        """Test configuring a service rate limiter."""
        limiter = ServiceRateLimiter(default_rpm=30)
        limiter.configure_service("govee", requests_per_minute=60, burst_size=10)

        govee_limiter = limiter.get_limiter("govee")
        assert govee_limiter.requests_per_minute == 60
        assert govee_limiter.burst_size == 10

    def test_creates_default_limiter_for_unknown_service(self):
        """Test default limiter is created for unknown services."""
        limiter = ServiceRateLimiter(default_rpm=45)

        unknown_limiter = limiter.get_limiter("unknown_service")
        assert unknown_limiter.requests_per_minute == 45

    @pytest.mark.asyncio
    async def test_acquire_for_service(self):
        """Test acquiring tokens for a specific service."""
        limiter = ServiceRateLimiter(default_rpm=60)
        limiter.configure_service("test", requests_per_minute=60, burst_size=5)

        # Should not wait for first few requests
        wait_time = await limiter.acquire("test")
        assert wait_time < 0.1


class TestDeviceOfflineError:
    """Tests for DeviceOfflineError."""

    def test_error_message(self):
        """Test DeviceOfflineError message."""
        error = DeviceOfflineError("light-1")
        assert error.device_id == "light-1"
        assert "light-1" in str(error)

    def test_custom_message(self):
        """Test DeviceOfflineError with custom message."""
        error = DeviceOfflineError("light-1", "Light is unreachable")
        assert "Light is unreachable" in str(error)


class TestRateLimitedError:
    """Tests for RateLimitedError."""

    def test_error_message(self):
        """Test RateLimitedError message."""
        error = RateLimitedError("govee")
        assert error.service == "govee"
        assert "govee" in str(error).lower()

    def test_error_with_retry_after(self):
        """Test RateLimitedError with retry_after."""
        error = RateLimitedError("govee", retry_after=30.0)
        assert error.retry_after == 30.0
        assert "30" in str(error)
