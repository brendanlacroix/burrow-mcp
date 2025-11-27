"""August lock implementation for Burrow MCP.

Uses the yalexs library for August/Yale smart lock control.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from config import DeviceConfig, SecretsConfig
from models.base import DeviceStatus, DeviceType
from models.lock import Lock, LockState
from utils.retry import CircuitBreaker, CircuitBreakerOpen, retry_async

logger = logging.getLogger(__name__)

# Circuit breaker for August API operations (shared across all August devices)
_august_circuit_breaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60.0,
    half_open_max_calls=2,
)

# Token cache file location
TOKEN_CACHE_PATH = Path.home() / ".cache" / "burrow" / "august_token.json"


@dataclass
class AugustLock(Lock):
    """August lock implementation using yalexs library."""

    device_type: DeviceType = field(default=DeviceType.LOCK, init=False)
    _lock_id: str | None = None
    _api: Any = field(default=None, repr=False)
    _authenticator: Any = field(default=None, repr=False)
    _authentication: Any = field(default=None, repr=False)

    async def _run_with_retry(self, coro_func: Callable[..., Any], *args: Any) -> Any:
        """Run an August API call with retry and circuit breaker.

        Uses retry for transient network errors and circuit breaker
        to prevent hammering an unresponsive service.
        """
        if _august_circuit_breaker.is_open:
            raise CircuitBreakerOpen("August circuit breaker is open")

        async def call_api():
            return await coro_func(*args)

        try:
            result = await retry_async(
                call_api,
                max_attempts=3,
                initial_delay=1.0,
                max_delay=10.0,
                retryable_exceptions=(OSError, TimeoutError, ConnectionError, asyncio.TimeoutError),
            )
            _august_circuit_breaker.record_success()
            return result
        except Exception:
            _august_circuit_breaker.record_failure()
            raise

    async def _ensure_authenticated(self) -> bool:
        """Ensure we have a valid authentication."""
        if self._api is None:
            logger.error(f"August API not initialized for {self.id}")
            return False

        if self._authentication is None:
            logger.error(f"August not authenticated for {self.id}")
            return False

        return True

    async def refresh(self) -> None:
        """Fetch current state from August cloud."""
        if not await self._ensure_authenticated():
            self.status = DeviceStatus.OFFLINE
            return

        if not self._lock_id:
            self.status = DeviceStatus.OFFLINE
            return

        try:
            # yalexs is async-native, use retry wrapper
            lock_detail = await self._run_with_retry(
                self._api.async_get_lock_detail, self._lock_id
            )

            if lock_detail:
                # Map August lock state to our LockState enum
                august_state = lock_detail.lock_status
                if august_state:
                    state_str = str(august_state).lower()
                    if "locked" in state_str:
                        self.lock_state = LockState.LOCKED
                    elif "unlocked" in state_str:
                        self.lock_state = LockState.UNLOCKED
                    elif "jammed" in state_str:
                        self.lock_state = LockState.JAMMED
                    else:
                        self.lock_state = LockState.UNKNOWN

                # Get battery level if available
                if hasattr(lock_detail, "battery_level"):
                    self.battery_percent = lock_detail.battery_level

                self.status = DeviceStatus.ONLINE
                logger.debug(f"Refreshed August {self.id}: state={self.lock_state.value}")
            else:
                self.status = DeviceStatus.OFFLINE

        except CircuitBreakerOpen:
            logger.warning(f"Circuit breaker open for August {self.id}")
            self.status = DeviceStatus.OFFLINE
        except Exception as e:
            logger.error(f"Failed to refresh August lock {self.id}: {e}")
            self.status = DeviceStatus.OFFLINE

    async def lock(self) -> None:
        """Lock the door."""
        if not await self._ensure_authenticated():
            raise RuntimeError(f"August lock {self.id} not authenticated")

        if not self._lock_id:
            raise RuntimeError(f"August lock {self.id} has no lock_id")

        try:
            result = await self._run_with_retry(self._api.async_lock, self._lock_id)
            if result:
                self.lock_state = LockState.LOCKED
                self.status = DeviceStatus.ONLINE
                logger.info(f"Locked August lock {self.id}")
            else:
                raise RuntimeError(f"Failed to lock {self.id}")

        except CircuitBreakerOpen:
            logger.warning(f"Circuit breaker open for August {self.id}")
            self.status = DeviceStatus.OFFLINE
            raise RuntimeError(f"August lock {self.id} temporarily unavailable (circuit breaker open)")
        except Exception as e:
            logger.error(f"Failed to lock August lock {self.id}: {e}")
            raise

    async def unlock(self) -> None:
        """Unlock the door."""
        if not await self._ensure_authenticated():
            raise RuntimeError(f"August lock {self.id} not authenticated")

        if not self._lock_id:
            raise RuntimeError(f"August lock {self.id} has no lock_id")

        try:
            result = await self._run_with_retry(self._api.async_unlock, self._lock_id)
            if result:
                self.lock_state = LockState.UNLOCKED
                self.status = DeviceStatus.ONLINE
                logger.info(f"Unlocked August lock {self.id}")
            else:
                raise RuntimeError(f"Failed to unlock {self.id}")

        except CircuitBreakerOpen:
            logger.warning(f"Circuit breaker open for August {self.id}")
            self.status = DeviceStatus.OFFLINE
            raise RuntimeError(f"August lock {self.id} temporarily unavailable (circuit breaker open)")
        except Exception as e:
            logger.error(f"Failed to unlock August lock {self.id}: {e}")
            raise

    async def reconnect(self) -> None:
        """Attempt to reconnect to August."""
        # Reset circuit breaker to allow retry
        _august_circuit_breaker.reset()
        await self.refresh()


async def create_august_lock(device_config: DeviceConfig, secrets: SecretsConfig) -> AugustLock:
    """Factory function to create an August lock from config.

    August authentication requires either:
    1. A cached token from previous authentication
    2. Username/password with 2FA code (interactive)

    For non-interactive use, run the authentication once interactively
    to cache the token.
    """
    try:
        from yalexs.api_async import ApiAsync
        from yalexs.authenticator_async import AuthenticatorAsync
        from yalexs.authenticator_common import AuthenticationState
    except ImportError:
        logger.error("yalexs package not installed. Install with: pip install yalexs")
        return AugustLock(
            id=device_config.id,
            name=device_config.name,
            room_id=device_config.room,
        )

    lock_id = secrets.august.get("lock_id") or device_config.config.get("lock_id")
    username = secrets.august.get("username")
    password = secrets.august.get("password")
    access_token = secrets.august.get("access_token")

    lock = AugustLock(
        id=device_config.id,
        name=device_config.name,
        room_id=device_config.room,
        _lock_id=lock_id,
    )

    if not lock_id:
        logger.warning(f"No lock_id for August lock {device_config.id}")
        return lock

    # Ensure cache directory exists
    TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Create API and authenticator
        api = ApiAsync(timeout=10)
        lock._api = api

        # If we have an access token, use it directly
        if access_token:
            from yalexs.authenticator_common import Authentication

            lock._authentication = Authentication(
                state=AuthenticationState.AUTHENTICATED,
                access_token=access_token,
                access_token_expires="",
                install_id=secrets.august.get("install_id", ""),
            )
            api.async_setup(lock._authentication)
            logger.info(f"August {device_config.id}: Using provided access token")

        # Otherwise try to authenticate with username/password
        elif username and password:
            authenticator = AuthenticatorAsync(
                api,
                "email",  # login_method
                username,
                password,
                access_token_cache_file=str(TOKEN_CACHE_PATH),
            )
            lock._authenticator = authenticator

            authentication = await authenticator.async_authenticate()
            lock._authentication = authentication

            if authentication.state == AuthenticationState.AUTHENTICATED:
                logger.info(f"August {device_config.id}: Authenticated successfully")
            elif authentication.state == AuthenticationState.REQUIRES_VALIDATION:
                logger.warning(
                    f"August {device_config.id}: Requires 2FA validation. "
                    "Run interactive setup first."
                )
            elif authentication.state == AuthenticationState.BAD_PASSWORD:
                logger.error(f"August {device_config.id}: Bad password")
            else:
                logger.error(f"August {device_config.id}: Authentication failed: {authentication.state}")

        else:
            logger.warning(
                f"August {device_config.id}: No credentials configured. "
                "Add username/password or access_token to secrets.yaml"
            )

        # Try initial refresh
        if lock._authentication:
            try:
                await lock.refresh()
            except Exception as e:
                logger.warning(f"Initial refresh failed for August {device_config.id}: {e}")

    except Exception as e:
        logger.error(f"Failed to initialize August lock {device_config.id}: {e}")

    return lock


async def list_august_locks(secrets: SecretsConfig) -> list[dict[str, Any]]:
    """List all locks associated with the August account.

    Args:
        secrets: Secrets config with August credentials

    Returns:
        List of lock info dicts
    """
    try:
        from yalexs.api_async import ApiAsync
        from yalexs.authenticator_async import AuthenticatorAsync
        from yalexs.authenticator_common import AuthenticationState
    except ImportError:
        logger.error("yalexs package not installed")
        return []

    username = secrets.august.get("username")
    password = secrets.august.get("password")

    if not username or not password:
        logger.error("August username/password required")
        return []

    TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        api = ApiAsync(timeout=10)
        authenticator = AuthenticatorAsync(
            api,
            "email",
            username,
            password,
            access_token_cache_file=str(TOKEN_CACHE_PATH),
        )

        authentication = await authenticator.async_authenticate()

        if authentication.state != AuthenticationState.AUTHENTICATED:
            logger.error(f"August authentication failed: {authentication.state}")
            return []

        locks = await api.async_get_locks(authentication.access_token)
        result = []

        for lock in locks:
            result.append({
                "lock_id": lock.device_id,
                "name": lock.device_name,
                "house_name": lock.house_name if hasattr(lock, "house_name") else None,
            })
            logger.info(f"Found August lock: {lock.device_name} ({lock.device_id})")

        return result

    except Exception as e:
        logger.error(f"Failed to list August locks: {e}")
        return []
