"""TV show metadata from TMDb (The Movie Database).

Provides episode schedules, air dates, and show information.
Free API: https://www.themoviedb.org/documentation/api
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TMDB_BASE_URL = "https://api.themoviedb.org/3"

# TMDb genre IDs
MOVIE_GENRES = {
    "action": 28,
    "adventure": 12,
    "animation": 16,
    "comedy": 35,
    "crime": 80,
    "documentary": 99,
    "drama": 18,
    "family": 10751,
    "fantasy": 14,
    "history": 36,
    "horror": 27,
    "music": 10402,
    "mystery": 9648,
    "romance": 10749,
    "sci-fi": 878,
    "science fiction": 878,
    "thriller": 53,
    "war": 10752,
    "western": 37,
}

TV_GENRES = {
    "action": 10759,
    "action & adventure": 10759,
    "adventure": 10759,
    "animation": 16,
    "comedy": 35,
    "crime": 80,
    "documentary": 99,
    "drama": 18,
    "family": 10751,
    "kids": 10762,
    "mystery": 9648,
    "reality": 10764,
    "sci-fi": 10765,
    "science fiction": 10765,
    "fantasy": 10765,
    "sci-fi & fantasy": 10765,
    "soap": 10766,
    "talk": 10767,
    "war": 10768,
    "western": 37,
}

# Mood to genre mappings for natural language
MOOD_TO_GENRES = {
    "scary": ["horror", "thriller"],
    "spooky": ["horror", "thriller"],
    "funny": ["comedy"],
    "laugh": ["comedy"],
    "romantic": ["romance", "drama"],
    "love": ["romance"],
    "exciting": ["action", "adventure", "thriller"],
    "intense": ["thriller", "action", "drama"],
    "relaxing": ["comedy", "family", "documentary"],
    "chill": ["comedy", "documentary"],
    "mind-bending": ["sci-fi", "mystery", "thriller"],
    "trippy": ["sci-fi", "fantasy"],
    "heartwarming": ["family", "drama", "romance"],
    "feel-good": ["comedy", "family", "romance"],
    "dark": ["thriller", "horror", "drama", "crime"],
    "suspenseful": ["thriller", "mystery", "crime"],
    "epic": ["adventure", "fantasy", "sci-fi", "action"],
    "nostalgic": ["family", "comedy", "drama"],
    "educational": ["documentary"],
    "inspiring": ["documentary", "drama"],
    "tearjerker": ["drama", "romance"],
    "sad": ["drama"],
    "animated": ["animation"],
    "cartoon": ["animation"],
}

# Map genre IDs back to names
GENRE_ID_TO_NAME = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy",
    80: "Crime", 99: "Documentary", 18: "Drama", 10751: "Family",
    14: "Fantasy", 36: "History", 27: "Horror", 10402: "Music",
    9648: "Mystery", 10749: "Romance", 878: "Science Fiction",
    53: "Thriller", 10752: "War", 37: "Western",
    10759: "Action & Adventure", 10762: "Kids", 10764: "Reality",
    10765: "Sci-Fi & Fantasy", 10766: "Soap", 10767: "Talk",
    10768: "War & Politics",
}


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


@dataclass
class Movie:
    """Information about a movie."""

    tmdb_id: int
    title: str
    release_year: int | None = None
    overview: str | None = None
    genres: list[str] = field(default_factory=list)
    rating: float | None = None  # TMDb vote average
    runtime: int | None = None  # minutes
    streaming_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "tmdb_id": self.tmdb_id,
            "title": self.title,
            "type": "movie",
        }
        if self.release_year:
            d["release_year"] = self.release_year
        if self.overview:
            d["overview"] = self.overview[:200] + "..." if len(self.overview or "") > 200 else self.overview
        if self.genres:
            d["genres"] = self.genres
        if self.rating:
            d["rating"] = round(self.rating, 1)
        if self.runtime:
            d["runtime_minutes"] = self.runtime
        if self.streaming_on:
            d["streaming_on"] = self.streaming_on
        return d


@dataclass
class ContentResult:
    """A content recommendation result (movie or TV)."""

    tmdb_id: int
    title: str
    media_type: str  # "movie" or "tv"
    overview: str | None = None
    genres: list[str] = field(default_factory=list)
    rating: float | None = None
    release_year: int | None = None
    streaming_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "tmdb_id": self.tmdb_id,
            "title": self.title,
            "type": self.media_type,
        }
        if self.overview:
            d["overview"] = self.overview[:200] + "..." if len(self.overview) > 200 else self.overview
        if self.genres:
            d["genres"] = self.genres
        if self.rating:
            d["rating"] = round(self.rating, 1)
        if self.release_year:
            d["year"] = self.release_year
        if self.streaming_on:
            d["streaming_on"] = self.streaming_on
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

    async def search_movie(self, query: str) -> list[dict[str, Any]]:
        """Search for a movie by name."""
        data = await self._request("/search/movie", {"query": query})
        if not data:
            return []

        results = []
        for item in data.get("results", [])[:5]:
            release_year = None
            if item.get("release_date"):
                try:
                    release_year = int(item["release_date"][:4])
                except (ValueError, IndexError):
                    pass

            results.append({
                "tmdb_id": item["id"],
                "title": item["title"],
                "release_year": release_year,
                "overview": item.get("overview", "")[:200],
                "rating": item.get("vote_average"),
            })
        return results

    async def get_movie(self, tmdb_id: int) -> Movie | None:
        """Get detailed information about a movie."""
        data = await self._request(f"/movie/{tmdb_id}")
        if not data:
            return None

        release_year = None
        if data.get("release_date"):
            try:
                release_year = int(data["release_date"][:4])
            except (ValueError, IndexError):
                pass

        genres = [g["name"] for g in data.get("genres", [])]

        return Movie(
            tmdb_id=tmdb_id,
            title=data["title"],
            release_year=release_year,
            overview=data.get("overview"),
            genres=genres,
            rating=data.get("vote_average"),
            runtime=data.get("runtime"),
        )

    def _resolve_genres(
        self, genre: str | None, mood: str | None, media_type: str
    ) -> list[int]:
        """Resolve genre/mood to TMDb genre IDs."""
        genre_map = MOVIE_GENRES if media_type == "movie" else TV_GENRES
        genre_ids = []

        if genre:
            genre_lower = genre.lower()
            if genre_lower in genre_map:
                genre_ids.append(genre_map[genre_lower])

        if mood:
            mood_lower = mood.lower()
            if mood_lower in MOOD_TO_GENRES:
                for g in MOOD_TO_GENRES[mood_lower]:
                    if g in genre_map and genre_map[g] not in genre_ids:
                        genre_ids.append(genre_map[g])

        return genre_ids

    async def discover(
        self,
        media_type: str = "movie",
        genre: str | None = None,
        mood: str | None = None,
        min_rating: float | None = None,
        exclude_ids: list[int] | None = None,
        limit: int = 10,
    ) -> list[ContentResult]:
        """Discover content by genre/mood.

        Args:
            media_type: "movie" or "tv"
            genre: Genre name like "action", "comedy", "horror"
            mood: Mood like "scary", "funny", "relaxing"
            min_rating: Minimum TMDb rating (1-10)
            exclude_ids: TMDb IDs to exclude from results
            limit: Max results to return

        Returns:
            List of ContentResult
        """
        endpoint = f"/discover/{media_type}"
        params: dict[str, Any] = {
            "sort_by": "popularity.desc",
            "vote_count.gte": 100,  # Filter out obscure stuff
        }

        # Resolve genres
        genre_ids = self._resolve_genres(genre, mood, media_type)
        if genre_ids:
            params["with_genres"] = ",".join(str(g) for g in genre_ids)

        if min_rating:
            params["vote_average.gte"] = min_rating

        data = await self._request(endpoint, params)
        if not data:
            return []

        exclude_set = set(exclude_ids or [])
        results = []

        for item in data.get("results", []):
            if item["id"] in exclude_set:
                continue

            if len(results) >= limit:
                break

            # Parse release year
            release_year = None
            date_field = "release_date" if media_type == "movie" else "first_air_date"
            if item.get(date_field):
                try:
                    release_year = int(item[date_field][:4])
                except (ValueError, IndexError):
                    pass

            # Map genre IDs to names
            genres = [
                GENRE_ID_TO_NAME.get(gid, f"Genre {gid}")
                for gid in item.get("genre_ids", [])
            ]

            title = item.get("title") or item.get("name", "Unknown")

            results.append(ContentResult(
                tmdb_id=item["id"],
                title=title,
                media_type=media_type,
                overview=item.get("overview"),
                genres=genres,
                rating=item.get("vote_average"),
                release_year=release_year,
            ))

        return results

    async def find_similar(
        self,
        title: str,
        media_type: str | None = None,
        exclude_titles: list[str] | None = None,
        limit: int = 10,
    ) -> list[ContentResult]:
        """Find content similar to a given title.

        Args:
            title: The movie or show to find similar content to
            media_type: "movie" or "tv" (will search both if not specified)
            exclude_titles: Titles to exclude (including the original)
            limit: Max results

        Returns:
            List of similar content
        """
        exclude_set = {t.lower() for t in (exclude_titles or [])}
        exclude_set.add(title.lower())  # Always exclude the original

        # Find the original content first
        tmdb_id = None
        found_type = media_type

        if not media_type or media_type == "movie":
            movie_results = await self.search_movie(title)
            if movie_results:
                tmdb_id = movie_results[0]["tmdb_id"]
                found_type = "movie"

        if not tmdb_id and (not media_type or media_type == "tv"):
            tv_results = await self.search_show(title)
            if tv_results:
                tmdb_id = tv_results[0]["tmdb_id"]
                found_type = "tv"

        if not tmdb_id:
            return []

        # Get similar content
        endpoint = f"/{found_type}/{tmdb_id}/similar"
        data = await self._request(endpoint)
        if not data:
            return []

        results = []
        for item in data.get("results", []):
            item_title = item.get("title") or item.get("name", "Unknown")

            # Skip excluded titles
            if item_title.lower() in exclude_set:
                continue

            if len(results) >= limit:
                break

            release_year = None
            date_field = "release_date" if found_type == "movie" else "first_air_date"
            if item.get(date_field):
                try:
                    release_year = int(item[date_field][:4])
                except (ValueError, IndexError):
                    pass

            genres = [
                GENRE_ID_TO_NAME.get(gid, f"Genre {gid}")
                for gid in item.get("genre_ids", [])
            ]

            results.append(ContentResult(
                tmdb_id=item["id"],
                title=item_title,
                media_type=found_type,
                overview=item.get("overview"),
                genres=genres,
                rating=item.get("vote_average"),
                release_year=release_year,
            ))

        return results

    async def get_recommendations_for(
        self,
        title: str,
        media_type: str | None = None,
        exclude_titles: list[str] | None = None,
        limit: int = 10,
    ) -> list[ContentResult]:
        """Get TMDb recommendations for a title (different from 'similar').

        TMDb's recommendations API uses different algorithms than similar
        and often returns more diverse/curated results.
        """
        exclude_set = {t.lower() for t in (exclude_titles or [])}
        exclude_set.add(title.lower())

        # Find the original
        tmdb_id = None
        found_type = media_type

        if not media_type or media_type == "movie":
            movie_results = await self.search_movie(title)
            if movie_results:
                tmdb_id = movie_results[0]["tmdb_id"]
                found_type = "movie"

        if not tmdb_id and (not media_type or media_type == "tv"):
            tv_results = await self.search_show(title)
            if tv_results:
                tmdb_id = tv_results[0]["tmdb_id"]
                found_type = "tv"

        if not tmdb_id:
            return []

        endpoint = f"/{found_type}/{tmdb_id}/recommendations"
        data = await self._request(endpoint)
        if not data:
            return []

        results = []
        for item in data.get("results", []):
            item_title = item.get("title") or item.get("name", "Unknown")

            if item_title.lower() in exclude_set:
                continue

            if len(results) >= limit:
                break

            release_year = None
            date_field = "release_date" if found_type == "movie" else "first_air_date"
            if item.get(date_field):
                try:
                    release_year = int(item[date_field][:4])
                except (ValueError, IndexError):
                    pass

            genres = [
                GENRE_ID_TO_NAME.get(gid, f"Genre {gid}")
                for gid in item.get("genre_ids", [])
            ]

            results.append(ContentResult(
                tmdb_id=item["id"],
                title=item_title,
                media_type=found_type,
                overview=item.get("overview"),
                genres=genres,
                rating=item.get("vote_average"),
                release_year=release_year,
            ))

        return results


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
