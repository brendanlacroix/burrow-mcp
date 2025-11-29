"""TV show metadata from TMDb (The Movie Database).

Provides episode schedules, air dates, and show information.
Free API: https://www.themoviedb.org/documentation/api
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TMDB_BASE_URL = "https://api.themoviedb.org/3"


@dataclass
class Episode:
    """Information about a TV episode."""

    season: int
    episode: int
    name: str
    air_date: date | None
    overview: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "season": self.season,
            "episode": self.episode,
            "name": self.name,
            "air_date": self.air_date.isoformat() if self.air_date else None,
        }


@dataclass
class Show:
    """Information about a TV show."""

    tmdb_id: int
    name: str
    status: str  # "Returning Series", "Ended", "Canceled", etc.
    next_episode: Episode | None = None
    last_episode: Episode | None = None
    networks: list[str] | None = None  # Where it airs/streams
    genres: list[str] | None = None

    @property
    def is_airing(self) -> bool:
        """Check if show is currently airing new episodes."""
        return self.status in ("Returning Series", "In Production")

    def to_dict(self) -> dict[str, Any]:
        d = {
            "tmdb_id": self.tmdb_id,
            "name": self.name,
            "status": self.status,
            "is_airing": self.is_airing,
        }
        if self.next_episode:
            d["next_episode"] = self.next_episode.to_dict()
        if self.last_episode:
            d["last_episode"] = self.last_episode.to_dict()
        if self.networks:
            d["networks"] = self.networks
        if self.genres:
            d["genres"] = self.genres
        return d


class TVMetadata:
    """Client for TMDb API to get TV show information."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(self, endpoint: str, params: dict | None = None) -> dict | None:
        """Make a request to TMDb API."""
        if not self.api_key:
            logger.debug("No TMDb API key configured")
            return None

        client = await self._get_client()
        url = f"{TMDB_BASE_URL}{endpoint}"

        request_params = {"api_key": self.api_key}
        if params:
            request_params.update(params)

        try:
            response = await client.get(url, params=request_params)
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"TMDb API error: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"TMDb API request failed: {e}")
            return None

    async def search_show(self, query: str) -> list[dict[str, Any]]:
        """Search for a TV show by name."""
        data = await self._request("/search/tv", {"query": query})
        if not data:
            return []

        results = []
        for item in data.get("results", [])[:5]:  # Top 5 results
            results.append({
                "tmdb_id": item["id"],
                "name": item["name"],
                "first_air_date": item.get("first_air_date"),
                "overview": item.get("overview", "")[:200],
            })
        return results

    async def get_show(self, tmdb_id: int) -> Show | None:
        """Get detailed information about a TV show."""
        data = await self._request(f"/tv/{tmdb_id}")
        if not data:
            return None

        # Parse next episode
        next_ep = None
        if data.get("next_episode_to_air"):
            ep = data["next_episode_to_air"]
            air_date = None
            if ep.get("air_date"):
                try:
                    air_date = date.fromisoformat(ep["air_date"])
                except ValueError:
                    pass
            next_ep = Episode(
                season=ep.get("season_number", 0),
                episode=ep.get("episode_number", 0),
                name=ep.get("name", ""),
                air_date=air_date,
                overview=ep.get("overview"),
            )

        # Parse last episode
        last_ep = None
        if data.get("last_episode_to_air"):
            ep = data["last_episode_to_air"]
            air_date = None
            if ep.get("air_date"):
                try:
                    air_date = date.fromisoformat(ep["air_date"])
                except ValueError:
                    pass
            last_ep = Episode(
                season=ep.get("season_number", 0),
                episode=ep.get("episode_number", 0),
                name=ep.get("name", ""),
                air_date=air_date,
            )

        # Parse networks
        networks = [n["name"] for n in data.get("networks", [])]

        # Parse genres
        genres = [g["name"] for g in data.get("genres", [])]

        return Show(
            tmdb_id=tmdb_id,
            name=data["name"],
            status=data.get("status", "Unknown"),
            next_episode=next_ep,
            last_episode=last_ep,
            networks=networks if networks else None,
            genres=genres if genres else None,
        )

    async def get_show_by_name(self, name: str) -> Show | None:
        """Search for a show and get its details."""
        results = await self.search_show(name)
        if not results:
            return None

        # Get details for top result
        return await self.get_show(results[0]["tmdb_id"])

    async def get_upcoming_episodes(
        self, show_ids: list[int], days_ahead: int = 7
    ) -> list[dict[str, Any]]:
        """Get upcoming episodes for a list of shows."""
        upcoming = []
        today = date.today()
        cutoff = today + timedelta(days=days_ahead)

        for tmdb_id in show_ids:
            show = await self.get_show(tmdb_id)
            if show and show.next_episode and show.next_episode.air_date:
                if today <= show.next_episode.air_date <= cutoff:
                    upcoming.append({
                        "show": show.name,
                        "tmdb_id": tmdb_id,
                        "episode": show.next_episode.to_dict(),
                        "days_until": (show.next_episode.air_date - today).days,
                    })

        # Sort by air date
        upcoming.sort(key=lambda x: x["episode"]["air_date"] or "")
        return upcoming


# Network to streaming service mapping
# This helps map where shows air to where you can watch them
NETWORK_TO_SERVICE = {
    # Broadcast -> streaming
    "NBC": "Peacock",
    "CBS": "Paramount+",
    "ABC": "Hulu",
    "FOX": "Hulu",
    "The CW": "Netflix",  # Usually next-day
    # Cable
    "Bravo": "Peacock",  # Real Housewives!
    "HBO": "Max",
    "Showtime": "Paramount+",
    "FX": "Hulu",
    "AMC": "AMC+",
    "Comedy Central": "Paramount+",
    "MTV": "Paramount+",
    "USA Network": "Peacock",
    "Syfy": "Peacock",
    "TBS": "Max",
    "TNT": "Max",
    # Streaming originals
    "Netflix": "Netflix",
    "Amazon": "Prime Video",
    "Prime Video": "Prime Video",
    "Apple TV+": "Apple TV+",
    "Disney+": "Disney+",
    "Hulu": "Hulu",
    "Max": "Max",
    "Peacock": "Peacock",
    "Paramount+": "Paramount+",
}


def get_streaming_service(networks: list[str] | None) -> str | None:
    """Map broadcast/cable networks to streaming services."""
    if not networks:
        return None

    for network in networks:
        if network in NETWORK_TO_SERVICE:
            return NETWORK_TO_SERVICE[network]

    # Return first network if no mapping found
    return networks[0] if networks else None
