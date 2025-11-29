"""Synology Download Station API client.

Handles authentication and torrent management on a Synology NAS.
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx

from utils.retry import CircuitBreaker, CircuitBreakerOpen

logger = logging.getLogger(__name__)

# Circuit breaker for Synology API
_synology_circuit_breaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=30.0,
    half_open_max_calls=2,
)


class DownloadStatus(Enum):
    """Download task status."""

    WAITING = "waiting"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    FINISHING = "finishing"
    FINISHED = "finished"
    HASH_CHECKING = "hash_checking"
    SEEDING = "seeding"
    FILEHOSTING_WAITING = "filehosting_waiting"
    EXTRACTING = "extracting"
    ERROR = "error"


@dataclass
class DownloadTask:
    """A download task on Download Station."""

    task_id: str
    title: str
    status: DownloadStatus
    size_bytes: int
    downloaded_bytes: int
    uploaded_bytes: int
    speed_download: int  # bytes per second
    speed_upload: int
    seeders: int
    leechers: int
    eta_seconds: int | None = None

    @property
    def progress_percent(self) -> float:
        """Download progress as percentage."""
        if self.size_bytes == 0:
            return 0.0
        return (self.downloaded_bytes / self.size_bytes) * 100

    @property
    def size_gb(self) -> float:
        """Size in gigabytes."""
        return self.size_bytes / (1024 ** 3)

    @property
    def downloaded_gb(self) -> float:
        """Downloaded amount in gigabytes."""
        return self.downloaded_bytes / (1024 ** 3)

    @property
    def eta_formatted(self) -> str | None:
        """Human-readable ETA."""
        if self.eta_seconds is None or self.eta_seconds <= 0:
            return None

        hours = self.eta_seconds // 3600
        minutes = (self.eta_seconds % 3600) // 60

        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "status": self.status.value,
            "progress_percent": round(self.progress_percent, 1),
            "size_gb": round(self.size_gb, 2),
            "downloaded_gb": round(self.downloaded_gb, 2),
            "speed_mbps": round(self.speed_download / (1024 * 1024), 2),
            "eta": self.eta_formatted,
            "seeders": self.seeders,
            "leechers": self.leechers,
        }


class SynologyAuthError(Exception):
    """Authentication failed with Synology."""
    pass


class SynologyError(Exception):
    """General Synology API error."""

    def __init__(self, code: int, message: str):
        self.code = code
        super().__init__(f"Synology error {code}: {message}")


# Synology API error codes
SYNOLOGY_ERROR_CODES = {
    100: "Unknown error",
    101: "Invalid parameters",
    102: "API does not exist",
    103: "Method does not exist",
    104: "This API version is not supported",
    105: "Insufficient permissions",
    106: "Session timeout",
    107: "Session interrupted",
    400: "No such account or wrong password",
    401: "Account disabled",
    402: "Account denied access",
    403: "2FA required",
    404: "2FA failed",
}


class SynologyClient:
    """Client for Synology Download Station API.

    Requires SYNOLOGY_URL, SYNOLOGY_USER, SYNOLOGY_PASS, and
    SYNOLOGY_DOWNLOAD_PATH environment variables.
    """

    def __init__(
        self,
        url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        download_path: str | None = None,
    ):
        """Initialize Synology client.

        Args:
            url: Synology NAS URL (defaults to SYNOLOGY_URL env var)
            username: Synology username (defaults to SYNOLOGY_USER env var)
            password: Synology password (defaults to SYNOLOGY_PASS env var)
            download_path: Fixed download path (defaults to SYNOLOGY_DOWNLOAD_PATH env var)
        """
        self.url = (url or os.environ.get("SYNOLOGY_URL", "")).rstrip("/")
        self.username = username or os.environ.get("SYNOLOGY_USER")
        self.password = password or os.environ.get("SYNOLOGY_PASS")
        self.download_path = download_path or os.environ.get("SYNOLOGY_DOWNLOAD_PATH")

        self._client: httpx.AsyncClient | None = None
        self._sid: str | None = None  # Session ID
        self._auth_lock = asyncio.Lock()

        if not self.url or not self.username or not self.password:
            logger.warning("Synology credentials not configured")

    @property
    def is_configured(self) -> bool:
        """Check if Synology is configured."""
        return bool(self.url and self.username and self.password and self.download_path)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the client and logout."""
        if self._sid:
            try:
                await self._logout()
            except Exception:
                pass
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        api: str,
        method: str,
        version: int,
        params: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a request to Synology API.

        Args:
            api: API name (e.g., "SYNO.API.Auth")
            method: Method name (e.g., "login")
            version: API version
            params: Additional parameters
            files: Files to upload (for multipart requests)

        Returns:
            API response data

        Raises:
            SynologyError: On API error
            SynologyAuthError: On authentication error
        """
        if _synology_circuit_breaker.is_open:
            raise CircuitBreakerOpen("Synology service is temporarily unavailable")

        client = await self._get_client()

        # Build request params
        request_params = {
            "api": api,
            "version": str(version),
            "method": method,
        }
        if params:
            request_params.update(params)

        # Add session ID if we have one (except for auth requests)
        if self._sid and api != "SYNO.API.Auth":
            request_params["_sid"] = self._sid

        # Determine endpoint based on API
        if api == "SYNO.API.Auth":
            endpoint = "/webapi/auth.cgi"
        elif api.startswith("SYNO.DownloadStation"):
            endpoint = "/webapi/DownloadStation/task.cgi"
        else:
            endpoint = "/webapi/entry.cgi"

        url = f"{self.url}{endpoint}"

        try:
            if files:
                # Multipart upload
                response = await client.post(
                    url,
                    data=request_params,
                    files=files,
                )
            else:
                # Regular GET request
                response = await client.get(url, params=request_params)

            if response.status_code != 200:
                _synology_circuit_breaker.record_failure()
                raise SynologyError(response.status_code, f"HTTP error {response.status_code}")

            data = response.json()

            if not data.get("success"):
                error_code = data.get("error", {}).get("code", 0)
                error_msg = SYNOLOGY_ERROR_CODES.get(error_code, "Unknown error")

                # Check for auth errors
                if error_code in (400, 401, 402, 403, 404, 105, 106, 107):
                    self._sid = None  # Clear session
                    _synology_circuit_breaker.record_failure()
                    raise SynologyAuthError(f"Auth error {error_code}: {error_msg}")

                _synology_circuit_breaker.record_failure()
                raise SynologyError(error_code, error_msg)

            _synology_circuit_breaker.record_success()
            return data.get("data", {})

        except (httpx.TimeoutException, httpx.ConnectError) as e:
            logger.error(f"Synology request failed: {e}")
            _synology_circuit_breaker.record_failure()
            raise SynologyError(0, str(e))

    async def _login(self) -> None:
        """Login to Synology and get session ID."""
        if not self.username or not self.password:
            raise SynologyAuthError("Synology credentials not configured")

        data = await self._request(
            api="SYNO.API.Auth",
            method="login",
            version=3,
            params={
                "account": self.username,
                "passwd": self.password,
                "session": "DownloadStation",
                "format": "sid",
            },
        )

        self._sid = data.get("sid")
        if not self._sid:
            raise SynologyAuthError("No session ID returned from login")

        logger.info("Successfully logged in to Synology")

    async def _logout(self) -> None:
        """Logout from Synology."""
        if not self._sid:
            return

        try:
            await self._request(
                api="SYNO.API.Auth",
                method="logout",
                version=1,
                params={"session": "DownloadStation"},
            )
        finally:
            self._sid = None

    async def _ensure_auth(self) -> None:
        """Ensure we have a valid session."""
        async with self._auth_lock:
            if not self._sid:
                await self._login()

    async def add_torrent(
        self,
        torrent_data: bytes,
        filename: str = "download.torrent",
    ) -> str | None:
        """Add a torrent to Download Station.

        Args:
            torrent_data: Torrent file bytes
            filename: Filename for the torrent

        Returns:
            Task ID or None on error
        """
        if not self.is_configured:
            logger.error("Synology not configured")
            return None

        await self._ensure_auth()

        params = {}
        if self.download_path:
            params["destination"] = self.download_path

        files = {
            "file": (filename, torrent_data, "application/x-bittorrent"),
        }

        try:
            data = await self._request(
                api="SYNO.DownloadStation.Task",
                method="create",
                version=1,
                params=params,
                files=files,
            )
            # The create method doesn't return the task ID directly
            # We need to list tasks to find it
            logger.info(f"Torrent added successfully")
            return "created"  # Return placeholder, actual ID comes from list

        except SynologyAuthError:
            # Try to re-auth once
            self._sid = None
            await self._ensure_auth()
            data = await self._request(
                api="SYNO.DownloadStation.Task",
                method="create",
                version=1,
                params=params,
                files=files,
            )
            return "created"

    async def list_tasks(self) -> list[DownloadTask]:
        """List all download tasks.

        Returns:
            List of download tasks
        """
        if not self.is_configured:
            logger.error("Synology not configured")
            return []

        await self._ensure_auth()

        try:
            data = await self._request(
                api="SYNO.DownloadStation.Task",
                method="list",
                version=1,
                params={"additional": "detail,transfer"},
            )
        except SynologyAuthError:
            # Try to re-auth once
            self._sid = None
            await self._ensure_auth()
            data = await self._request(
                api="SYNO.DownloadStation.Task",
                method="list",
                version=1,
                params={"additional": "detail,transfer"},
            )

        tasks = []
        for task_data in data.get("tasks", []):
            try:
                tasks.append(self._parse_task(task_data))
            except Exception as e:
                logger.warning(f"Failed to parse task: {e}")

        return tasks

    def _parse_task(self, data: dict[str, Any]) -> DownloadTask:
        """Parse a task from API response."""
        # Get additional info
        additional = data.get("additional", {})
        detail = additional.get("detail", {})
        transfer = additional.get("transfer", {})

        # Parse status
        status_str = data.get("status", "unknown")
        try:
            status = DownloadStatus(status_str)
        except ValueError:
            status = DownloadStatus.ERROR

        # Calculate ETA
        eta = None
        if transfer.get("speed_download", 0) > 0:
            remaining = data.get("size", 0) - transfer.get("size_downloaded", 0)
            if remaining > 0:
                eta = int(remaining / transfer["speed_download"])

        return DownloadTask(
            task_id=data.get("id", ""),
            title=data.get("title", "Unknown"),
            status=status,
            size_bytes=data.get("size", 0),
            downloaded_bytes=transfer.get("size_downloaded", 0),
            uploaded_bytes=transfer.get("size_uploaded", 0),
            speed_download=transfer.get("speed_download", 0),
            speed_upload=transfer.get("speed_upload", 0),
            seeders=detail.get("seeding_peers", 0) if detail else 0,
            leechers=detail.get("connected_leechers", 0) if detail else 0,
            eta_seconds=eta,
        )

    async def get_active_downloads(self) -> list[DownloadTask]:
        """Get only active (downloading or waiting) tasks.

        Returns:
            List of active download tasks
        """
        tasks = await self.list_tasks()
        return [
            t for t in tasks
            if t.status in (
                DownloadStatus.DOWNLOADING,
                DownloadStatus.WAITING,
                DownloadStatus.HASH_CHECKING,
            )
        ]

    async def get_task_by_title(self, title_partial: str) -> DownloadTask | None:
        """Find a task by partial title match.

        Args:
            title_partial: Partial title to search for

        Returns:
            Matching task or None
        """
        tasks = await self.list_tasks()
        title_lower = title_partial.lower()

        for task in tasks:
            if title_lower in task.title.lower():
                return task

        return None
