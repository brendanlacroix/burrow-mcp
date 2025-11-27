"""Tests for utility modules."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from utils.health import DeviceHealth, HealthMonitor
from utils.retry import (
    CircuitBreaker,
    CircuitBreakerOpen,
    RetryExhausted,
    retry_async,
    with_circuit_breaker,
    with_retry,
)


class TestRetry:
    """Tests for retry utilities."""

    @pytest.mark.asyncio
    async def test_retry_success_first_try(self):
        """Test successful operation on first try."""
        mock_func = AsyncMock(return_value="success")

        result = await retry_async(mock_func, max_attempts=3, initial_delay=0.01)

        assert result == "success"
        assert mock_func.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_success_after_failures(self):
        """Test successful operation after some failures."""
        mock_func = AsyncMock(side_effect=[ValueError, ValueError, "success"])

        result = await retry_async(mock_func, max_attempts=3, initial_delay=0.01)

        assert result == "success"
        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        """Test retry exhaustion."""
        mock_func = AsyncMock(side_effect=ValueError("always fails"))

        with pytest.raises(RetryExhausted) as exc_info:
            await retry_async(mock_func, max_attempts=3, initial_delay=0.01)

        assert exc_info.value.attempts == 3
        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_specific_exceptions(self):
        """Test retrying only specific exception types."""
        mock_func = AsyncMock(side_effect=TypeError("not retryable"))

        with pytest.raises(RetryExhausted):
            await retry_async(
                mock_func,
                max_attempts=3,
                initial_delay=0.01,
                retryable_exceptions=(TypeError,),
            )

    @pytest.mark.asyncio
    async def test_with_retry_decorator(self):
        """Test the retry decorator."""
        call_count = 0

        @with_retry(max_attempts=3, initial_delay=0.01)
        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("temporary failure")
            return "success"

        result = await flaky_func()
        assert result == "success"
        assert call_count == 2


class TestCircuitBreaker:
    """Tests for circuit breaker."""

    def test_initial_state(self):
        """Test circuit breaker initial state."""
        breaker = CircuitBreaker()
        assert breaker.state == CircuitBreaker.CLOSED
        assert not breaker.is_open

    def test_opens_after_threshold(self):
        """Test circuit opens after failure threshold."""
        breaker = CircuitBreaker(failure_threshold=3)

        breaker.record_failure()
        assert breaker.state == CircuitBreaker.CLOSED

        breaker.record_failure()
        assert breaker.state == CircuitBreaker.CLOSED

        breaker.record_failure()
        assert breaker.state == CircuitBreaker.OPEN
        assert breaker.is_open

    def test_success_resets_failures(self):
        """Test success resets failure count."""
        breaker = CircuitBreaker(failure_threshold=3)

        breaker.record_failure()
        breaker.record_failure()
        breaker.record_success()

        # Should be back to 0 failures
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitBreaker.CLOSED

    def test_reset(self):
        """Test manual reset."""
        breaker = CircuitBreaker(failure_threshold=1)
        breaker.record_failure()
        assert breaker.state == CircuitBreaker.OPEN

        breaker.reset()
        assert breaker.state == CircuitBreaker.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_breaker_decorator(self):
        """Test circuit breaker decorator."""
        breaker = CircuitBreaker(failure_threshold=2)
        call_count = 0

        @with_circuit_breaker(breaker)
        async def protected_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("always fails")

        # First two calls should attempt the function
        with pytest.raises(ValueError):
            await protected_func()
        with pytest.raises(ValueError):
            await protected_func()

        assert call_count == 2
        assert breaker.is_open

        # Third call should fail fast
        with pytest.raises(CircuitBreakerOpen):
            await protected_func()

        # Call count shouldn't increase
        assert call_count == 2


class TestDeviceHealth:
    """Tests for device health tracking."""

    def test_initial_state(self):
        """Test initial health state."""
        health = DeviceHealth(device_id="test")
        assert health.is_healthy is True
        assert health.consecutive_failures == 0
        assert health.total_failures == 0

    def test_record_success(self):
        """Test recording success."""
        health = DeviceHealth(device_id="test")
        health.record_success()

        assert health.is_healthy is True
        assert health.total_successes == 1
        assert health.last_successful_contact is not None

    def test_record_failure(self):
        """Test recording failures."""
        health = DeviceHealth(device_id="test")
        health.record_failure()

        assert health.consecutive_failures == 1
        assert health.total_failures == 1
        assert health.is_healthy is True  # Still healthy after 1 failure

        health.record_failure()
        health.record_failure()

        assert health.consecutive_failures == 3
        assert health.is_healthy is False  # Unhealthy after 3 consecutive failures

    def test_success_resets_consecutive_failures(self):
        """Test success resets consecutive failure count."""
        health = DeviceHealth(device_id="test")
        health.record_failure()
        health.record_failure()
        health.record_success()

        assert health.consecutive_failures == 0
        assert health.total_failures == 2  # Total still tracked

    def test_failure_rate(self):
        """Test failure rate calculation."""
        health = DeviceHealth(device_id="test")
        assert health.failure_rate == 0.0

        health.record_success()
        health.record_success()
        health.record_failure()

        assert health.failure_rate == pytest.approx(1 / 3)


class TestHealthMonitor:
    """Tests for health monitor."""

    @pytest.mark.asyncio
    async def test_register_device(self):
        """Test registering a device."""
        monitor = HealthMonitor()
        check_func = AsyncMock()

        monitor.register_device("test_device", check_func)

        health = monitor.get_device_health("test_device")
        assert health is not None
        assert health.device_id == "test_device"

    @pytest.mark.asyncio
    async def test_check_device_success(self):
        """Test successful health check."""
        monitor = HealthMonitor()
        check_func = AsyncMock()

        monitor.register_device("test_device", check_func)
        result = await monitor.check_device("test_device")

        assert result is True
        check_func.assert_called_once()

        health = monitor.get_device_health("test_device")
        assert health.is_healthy is True

    @pytest.mark.asyncio
    async def test_check_device_failure(self):
        """Test failed health check."""
        # DeviceHealth.is_healthy goes false after 3 consecutive failures
        monitor = HealthMonitor(unhealthy_threshold=3)
        check_func = AsyncMock(side_effect=Exception("check failed"))

        monitor.register_device("test_device", check_func)

        # Need 3 consecutive failures to mark unhealthy
        for _ in range(3):
            result = await monitor.check_device("test_device")
            assert result is False

        health = monitor.get_device_health("test_device")
        assert health.is_healthy is False
        assert health.consecutive_failures == 3

    @pytest.mark.asyncio
    async def test_check_all(self):
        """Test checking all devices."""
        monitor = HealthMonitor()
        monitor.register_device("device_1", AsyncMock())
        monitor.register_device("device_2", AsyncMock(side_effect=Exception("fail")))

        results = await monitor.check_all()

        assert results["device_1"] is True
        assert results["device_2"] is False

    @pytest.mark.asyncio
    async def test_get_unhealthy_devices(self):
        """Test getting list of unhealthy devices."""
        # DeviceHealth.is_healthy goes false after 3 consecutive failures
        monitor = HealthMonitor(unhealthy_threshold=3)
        monitor.register_device("healthy", AsyncMock())
        monitor.register_device("unhealthy", AsyncMock(side_effect=Exception("fail")))

        # Need 3 checks to trigger unhealthy status
        for _ in range(3):
            await monitor.check_all()

        unhealthy = monitor.get_unhealthy_devices()
        assert "unhealthy" in unhealthy
        assert "healthy" not in unhealthy

    @pytest.mark.asyncio
    async def test_get_summary(self):
        """Test health summary."""
        # DeviceHealth.is_healthy goes false after 3 consecutive failures
        monitor = HealthMonitor(unhealthy_threshold=3)
        monitor.register_device("device_1", AsyncMock())
        monitor.register_device("device_2", AsyncMock(side_effect=Exception("fail")))

        # Need 3 checks to trigger unhealthy status
        for _ in range(3):
            await monitor.check_all()
        summary = monitor.get_summary()

        assert summary["total_devices"] == 2
        assert summary["healthy_devices"] == 1
        assert summary["unhealthy_devices"] == 1

    @pytest.mark.asyncio
    async def test_unregister_device(self):
        """Test unregistering a device."""
        monitor = HealthMonitor()
        monitor.register_device("test_device", AsyncMock())
        monitor.unregister_device("test_device")

        health = monitor.get_device_health("test_device")
        assert health is None
