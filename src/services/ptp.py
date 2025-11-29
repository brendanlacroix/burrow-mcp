"""PassThePopcorn API client.

PTP uses a semi-unofficial API with ApiUser/ApiKey authentication.
This client handles searching for movies and downloading torrent files.
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from utils.rate_limit import TokenBucketRateLimiter
from utils.retry import retry_async, CircuitBreaker, CircuitBreakerOpen

logger = logging.getLogger(__name__)

PTP_BASE_URL = "https://passthepopcorn.me"

# Rate limit PTP requests - be respectful of their servers
# Conservative: 10 requests per minute with burst of 3
_ptp_rate_limiter = TokenBucketRateLimiter(requests_per_minute=10, burst_size=3)

# Circuit breaker for PTP API
_ptp_circuit_breaker = CircuitBreaker(
    failure_threshold=3,
    recovery_timeout=60.0,
    half_open_max_calls=2,
)


@dataclass
class PTPTorrent:
    """A torrent available on PTP for a movie."""

    torrent_id: int
    quality: str  # e.g., "High Definition"
    resolution: str  # e.g., "1080p", "2160p", "720p"
    source: str  # e.g., "Blu-ray", "WEB", "HDTV", "DVD"
    codec: str  # e.g., "x264", "x265", "HEVC"
    container: str  # e.g., "MKV", "MP4"
    size_bytes: int
    seeders: int
    leechers: int
    snatched: int  # download count
    is_golden_popcorn: bool
    is_scene: bool
    release_name: str
    release_group: str | None = None
    uploaded_time: str | None = None

    @property
    def size_gb(self) -> float:
        """Size in gigabytes."""
        return self.size_bytes / (1024 ** 3)

    @property
    def resolution_value(self) -> int:
        """Numeric resolution for comparison (higher is better)."""
        resolution_map = {
            "2160p": 2160,
            "1080p": 1080,
            "1080i": 1080,
            "720p": 720,
            "576p": 576,
            "576i": 576,
            "480p": 480,
            "480i": 480,
            "SD": 480,
        }
        return resolution_map.get(self.resolution, 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "torrent_id": self.torrent_id,
            "resolution": self.resolution,
            "source": self.source,
            "codec": self.codec,
            "size_gb": round(self.size_gb, 2),
            "seeders": self.seeders,
            "is_golden_popcorn": self.is_golden_popcorn,
            "release_name": self.release_name,
        }


@dataclass
class PTPMovie:
    """A movie result from PTP."""

    movie_id: int
    title: str
    year: int
    imdb_id: str | None = None
    imdb_rating: float | None = None
    cover_url: str | None = None
    directors: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    torrents: list[PTPTorrent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "movie_id": self.movie_id,
            "title": self.title,
            "year": self.year,
            "imdb_id": self.imdb_id,
            "imdb_rating": self.imdb_rating,
            "torrent_count": len(self.torrents),
        }


class PTPAuthError(Exception):
    """Authentication failed with PTP."""
    pass


class PTPRateLimitError(Exception):
    """Rate limited by PTP."""

    def __init__(self, retry_after: float | None = None):
        self.retry_after = retry_after
        super().__init__(f"Rate limited by PTP. Retry after {retry_after}s")


class PTPClient:
    """Client for PassThePopcorn API.

    Requires PTP_API_USER and PTP_API_KEY environment variables.
    """

    def __init__(
        self,
        api_user: str | None = None,
        api_key: str | None = None,
    ):
        """Initialize PTP client.

        Args:
            api_user: PTP API username (defaults to PTP_API_USER env var)
            api_key: PTP API key (defaults to PTP_API_KEY env var)
        """
        self.api_user = api_user or os.environ.get("PTP_API_USER")
        self.api_key = api_key or os.environ.get("PTP_API_KEY")
        self._client: httpx.AsyncClient | None = None

        if not self.api_user or not self.api_key:
            logger.warning("PTP credentials not configured")

    @property
    def is_configured(self) -> bool:
        """Check if PTP credentials are configured."""
        return bool(self.api_user and self.api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "ApiUser": self.api_user or "",
                    "ApiKey": self.api_key or "",
                    "User-Agent": "Burrow-MCP/1.0",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        raw_response: bool = False,
    ) -> dict[str, Any] | bytes | None:
        """Make a request to PTP API.

        Args:
            endpoint: API endpoint path
            params: Query parameters
            raw_response: If True, return raw bytes (for torrent download)

        Returns:
            JSON response dict, raw bytes, or None on error
        """
        if not self.is_configured:
            logger.error("PTP credentials not configured")
            return None

        if _ptp_circuit_breaker.is_open:
            logger.warning("PTP circuit breaker is open")
            raise CircuitBreakerOpen("PTP service is temporarily unavailable")

        # Apply rate limiting
        await _ptp_rate_limiter.acquire()

        client = await self._get_client()
        url = f"{PTP_BASE_URL}{endpoint}"

        try:
            response = await client.get(url, params=params)

            if response.status_code == 401:
                _ptp_circuit_breaker.record_failure()
                raise PTPAuthError("Invalid PTP credentials")

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                _ptp_circuit_breaker.record_failure()
                raise PTPRateLimitError(
                    float(retry_after) if retry_after else 60.0
                )

            if response.status_code != 200:
                logger.error(f"PTP API error: {response.status_code}")
                _ptp_circuit_breaker.record_failure()
                return None

            _ptp_circuit_breaker.record_success()

            if raw_response:
                return response.content

            return response.json()

        except (httpx.TimeoutException, httpx.ConnectError) as e:
            logger.error(f"PTP request failed: {e}")
            _ptp_circuit_breaker.record_failure()
            return None

    def _parse_torrent(self, data: dict[str, Any]) -> PTPTorrent:
        """Parse torrent data from PTP API response."""
        # Parse size - PTP returns size as string like "8.5 GB"
        size_str = data.get("Size", "0")
        size_bytes = int(size_str) if size_str.isdigit() else 0

        # Parse resolution from Quality and Resolution fields
        resolution = data.get("Resolution", "SD")
        if resolution == "Other":
            resolution = "SD"

        # Check for Golden Popcorn
        is_gp = data.get("GoldenPopcorn", False)
        if isinstance(is_gp, str):
            is_gp = is_gp.lower() == "true"

        return PTPTorrent(
            torrent_id=int(data.get("Id", 0)),
            quality=data.get("Quality", "Standard Definition"),
            resolution=resolution,
            source=data.get("Source", "Unknown"),
            codec=data.get("Codec", "Unknown"),
            container=data.get("Container", "Unknown"),
            size_bytes=size_bytes,
            seeders=int(data.get("Seeders", 0)),
            leechers=int(data.get("Leechers", 0)),
            snatched=int(data.get("Snatched", 0)),
            is_golden_popcorn=is_gp,
            is_scene=data.get("Scene", False),
            release_name=data.get("ReleaseName", ""),
            release_group=data.get("ReleaseGroup"),
            uploaded_time=data.get("UploadTime"),
        )

    def _parse_movie(self, data: dict[str, Any]) -> PTPMovie:
        """Parse movie data from PTP API response."""
        # Parse torrents
        torrents = []
        for t in data.get("Torrents", []):
            try:
                torrents.append(self._parse_torrent(t))
            except Exception as e:
                logger.warning(f"Failed to parse torrent: {e}")

        # Parse directors
        directors = []
        for d in data.get("Directors", []):
            if isinstance(d, dict):
                directors.append(d.get("Name", ""))
            elif isinstance(d, str):
                directors.append(d)

        return PTPMovie(
            movie_id=int(data.get("GroupId", data.get("Id", 0))),
            title=data.get("Title", "Unknown"),
            year=int(data.get("Year", 0)),
            imdb_id=data.get("ImdbId"),
            imdb_rating=float(data["ImdbRating"]) if data.get("ImdbRating") else None,
            cover_url=data.get("Cover"),
            directors=directors,
            tags=data.get("Tags", []),
            torrents=torrents,
        )

    async def search(
        self,
        query: str,
        year: int | None = None,
    ) -> list[PTPMovie]:
        """Search for movies on PTP.

        Args:
            query: Movie title to search for
            year: Optional year filter

        Returns:
            List of matching movies
        """
        params: dict[str, Any] = {
            "searchstr": query,
            "json": "noredirect",
        }
        if year:
            params["year"] = str(year)

        data = await self._request("/torrents.php", params)
        if not data or not isinstance(data, dict):
            return []

        movies = []
        for movie_data in data.get("Movies", []):
            try:
                movies.append(self._parse_movie(movie_data))
            except Exception as e:
                logger.warning(f"Failed to parse movie: {e}")

        return movies

    async def get_movie(self, movie_id: int) -> PTPMovie | None:
        """Get detailed information about a movie.

        Args:
            movie_id: PTP movie ID

        Returns:
            Movie details with all torrents
        """
        params = {
            "id": str(movie_id),
            "json": "noredirect",
        }

        data = await self._request("/torrents.php", params)
        if not data or not isinstance(data, dict):
            return None

        try:
            return self._parse_movie(data)
        except Exception as e:
            logger.error(f"Failed to parse movie {movie_id}: {e}")
            return None

    async def download_torrent(self, torrent_id: int) -> bytes | None:
        """Download a torrent file.

        Args:
            torrent_id: PTP torrent ID

        Returns:
            Torrent file bytes or None on error
        """
        params = {
            "action": "download",
            "id": str(torrent_id),
        }

        result = await self._request("/torrents.php", params, raw_response=True)
        if isinstance(result, bytes):
            return result
        return None

    async def search_exact(
        self,
        title: str,
        year: int | None = None,
    ) -> PTPMovie | None:
        """Search for an exact movie match.

        Args:
            title: Movie title
            year: Optional year for disambiguation

        Returns:
            Best matching movie or None
        """
        movies = await self.search(title, year)
        if not movies:
            return None

        # If year specified, prefer exact year match
        if year:
            for movie in movies:
                if movie.year == year:
                    return movie

        # Otherwise return first result (best match by relevance)
        return movies[0]

    async def search_batch(
        self,
        titles: list[tuple[str, int | None]],
        delay: float = 1.5,
    ) -> list[PTPMovie | None]:
        """Search for multiple movies with rate limiting.

        Args:
            titles: List of (title, year) tuples
            delay: Delay between requests in seconds

        Returns:
            List of movies (None for not found)
        """
        results = []
        for i, (title, year) in enumerate(titles):
            if i > 0:
                # Add delay between requests to be respectful
                await asyncio.sleep(delay)

            movie = await self.search_exact(title, year)
            results.append(movie)

        return results
