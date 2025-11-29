"""Movie query interpretation for natural language requests.

Handles franchises, filmographies, "newest/latest" requests using TMDB.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TMDB_BASE_URL = "https://api.themoviedb.org/3"

# Known franchise patterns and their TMDB collection IDs
# These are the most commonly requested franchises
KNOWN_COLLECTIONS = {
    "mission impossible": 87359,
    "mission: impossible": 87359,
    "fast and furious": 9485,
    "fast & furious": 9485,
    "fast furious": 9485,
    "james bond": 645,
    "bond": 645,
    "007": 645,
    "harry potter": 1241,
    "lord of the rings": 119,
    "lotr": 119,
    "star wars": 10,
    "marvel cinematic universe": 529892,  # MCU collection
    "mcu": 529892,
    "avengers": 86311,
    "iron man": 131292,
    "spider-man": 531241,  # MCU Spider-Man
    "batman": 263,
    "dark knight": 263,
    "indiana jones": 84,
    "jurassic park": 328,
    "jurassic world": 328,
    "pirates of the caribbean": 295,
    "pirates caribbean": 295,
    "toy story": 10194,
    "john wick": 404609,
    "matrix": 2344,
    "the matrix": 2344,
    "alien": 8091,
    "aliens": 8091,
    "terminator": 528,
    "die hard": 1570,
    "bourne": 31562,
    "jason bourne": 31562,
    "rocky": 1575,
    "creed": 553717,
    "transformers": 8650,
    "x-men": 748,
    "hunger games": 131635,
    "twilight": 33514,
    "maze runner": 295130,
    "planet of the apes": 173710,  # Reboot series
    "dune": 726871,
    "godfather": 230,
    "the godfather": 230,
    "back to the future": 264,
    "men in black": 86055,
    "shrek": 2150,
    "despicable me": 86066,
    "minions": 86066,
    "ice age": 8354,
    "kung fu panda": 77816,
    "how to train your dragon": 89137,
    "cars": 87118,
    "finding nemo": 137697,
    "finding dory": 137697,
    "incredibles": 468222,
    "the incredibles": 468222,
    "ocean's": 304,  # Ocean's Eleven etc
    "oceans": 304,
}

# Known authors whose book adaptations we can look up
KNOWN_AUTHORS = {
    "dan brown": ["The Da Vinci Code", "Angels & Demons", "Inferno"],
    "stephen king": None,  # Too many - use search
    "michael crichton": ["Jurassic Park", "The Lost World", "Congo", "Sphere", "Timeline"],
    "john grisham": None,  # Use search
    "tom clancy": ["The Hunt for Red October", "Patriot Games", "Clear and Present Danger", "The Sum of All Fears", "Jack Ryan: Shadow Recruit"],
    "agatha christie": None,  # Use search
    "jk rowling": None,  # Harry Potter handled via collection
    "j.k. rowling": None,
    "tolkien": None,  # LOTR handled via collection
    "j.r.r. tolkien": None,
}


@dataclass
class MovieTarget:
    """A movie to download."""

    title: str
    year: int | None = None
    tmdb_id: int | None = None


@dataclass
class QueryInterpretation:
    """Result of interpreting a movie query."""

    query_type: str  # "single", "franchise", "filmography", "latest", "multiple"
    movies: list[MovieTarget] = field(default_factory=list)
    original_query: str = ""
    interpretation: str = ""  # Human-readable explanation
    collection_name: str | None = None  # For franchises


class MovieQueryInterpreter:
    """Interprets natural language movie queries using TMDB.

    Handles:
    - Single movies: "Jennifer's Body"
    - Franchises: "the Mission Impossible movies"
    - Filmographies: "Greta Gerwig movies" (as director)
    - Latest/newest: "the new Dune movie"
    - Author adaptations: "Dan Brown movies"
    """

    def __init__(self, tmdb_api_key: str | None = None):
        """Initialize interpreter.

        Args:
            tmdb_api_key: TMDB API key
        """
        self.api_key = tmdb_api_key
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _tmdb_request(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Make a TMDB API request."""
        if not self.api_key:
            logger.warning("TMDB API key not configured")
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
            logger.warning(f"TMDB API error: {response.status_code}")
            return None
        except Exception as e:
            logger.error(f"TMDB request failed: {e}")
            return None

    def _normalize_query(self, query: str) -> str:
        """Normalize query for matching."""
        return query.lower().strip()

    def _is_franchise_query(self, query: str) -> bool:
        """Check if query is asking for a franchise."""
        q = self._normalize_query(query)
        patterns = [
            r"^(all )?(the )?.*movies$",
            r"^(all )?(the )?.*films$",
            r"^(all )?(the )?.*franchise$",
            r"^(all )?(the )?.*series$",
            r"^(all )?(the )?.*collection$",
        ]
        return any(re.match(p, q) for p in patterns)

    def _is_latest_query(self, query: str) -> bool:
        """Check if query is asking for the latest/newest."""
        q = self._normalize_query(query)
        patterns = [
            r"^(the )?(new|newest|latest|recent|last).*",
            r".*(new|newest|latest|recent) (one|movie|film)$",
        ]
        return any(re.match(p, q) for p in patterns)

    def _extract_franchise_name(self, query: str) -> str:
        """Extract franchise name from query."""
        q = self._normalize_query(query)
        # Remove common prefixes/suffixes
        q = re.sub(r"^(all )?(the )?", "", q)
        q = re.sub(r" (movies|films|franchise|series|collection)$", "", q)
        return q.strip()

    def _extract_base_title(self, query: str) -> str:
        """Extract base title from 'newest X' style queries."""
        q = self._normalize_query(query)
        q = re.sub(r"^(the )?(new|newest|latest|recent|last) ", "", q)
        q = re.sub(r" (one|movie|film)$", "", q)
        return q.strip()

    async def _get_collection(self, collection_id: int) -> list[MovieTarget]:
        """Get movies from a TMDB collection."""
        data = await self._tmdb_request(f"/collection/{collection_id}")
        if not data:
            return []

        movies = []
        for part in data.get("parts", []):
            year = None
            if part.get("release_date"):
                try:
                    year = int(part["release_date"][:4])
                except (ValueError, IndexError):
                    pass

            movies.append(MovieTarget(
                title=part.get("title", "Unknown"),
                year=year,
                tmdb_id=part.get("id"),
            ))

        # Sort by release year
        movies.sort(key=lambda m: m.year or 9999)
        return movies

    async def _search_collection(self, query: str) -> tuple[int | None, str | None]:
        """Search for a collection by name.

        Returns:
            (collection_id, collection_name) or (None, None)
        """
        data = await self._tmdb_request("/search/collection", {"query": query})
        if not data or not data.get("results"):
            return None, None

        # Return first result
        result = data["results"][0]
        return result.get("id"), result.get("name")

    async def _get_person_movies(
        self, person_name: str, as_director: bool = True
    ) -> list[MovieTarget]:
        """Get movies by a person (director/actor).

        Args:
            person_name: Name to search for
            as_director: If True, get directing credits; if False, get acting

        Returns:
            List of movies
        """
        # Search for person
        data = await self._tmdb_request("/search/person", {"query": person_name})
        if not data or not data.get("results"):
            return []

        person_id = data["results"][0]["id"]

        # Get movie credits
        credits = await self._tmdb_request(f"/person/{person_id}/movie_credits")
        if not credits:
            return []

        # Get relevant credits
        if as_director:
            credit_list = credits.get("crew", [])
            credit_list = [c for c in credit_list if c.get("job") == "Director"]
        else:
            credit_list = credits.get("cast", [])

        movies = []
        seen_ids = set()

        for credit in credit_list:
            movie_id = credit.get("id")
            if movie_id in seen_ids:
                continue
            seen_ids.add(movie_id)

            year = None
            if credit.get("release_date"):
                try:
                    year = int(credit["release_date"][:4])
                except (ValueError, IndexError):
                    pass

            movies.append(MovieTarget(
                title=credit.get("title", "Unknown"),
                year=year,
                tmdb_id=movie_id,
            ))

        # Sort by release year, newest first
        movies.sort(key=lambda m: m.year or 0, reverse=True)
        return movies

    async def _search_movie(self, query: str, year: int | None = None) -> MovieTarget | None:
        """Search for a single movie."""
        params = {"query": query}
        if year:
            params["year"] = str(year)

        data = await self._tmdb_request("/search/movie", params)
        if not data or not data.get("results"):
            return None

        # Prefer newer movies if no year specified
        results = data["results"]
        if not year and len(results) > 1:
            # Sort by release date, newest first
            results.sort(
                key=lambda r: r.get("release_date", "0000"),
                reverse=True
            )

        result = results[0]
        year_found = None
        if result.get("release_date"):
            try:
                year_found = int(result["release_date"][:4])
            except (ValueError, IndexError):
                pass

        return MovieTarget(
            title=result.get("title", query),
            year=year_found,
            tmdb_id=result.get("id"),
        )

    async def _get_latest_in_franchise(self, franchise_name: str) -> MovieTarget | None:
        """Get the most recent movie in a franchise."""
        # Check known collections first
        normalized = self._normalize_query(franchise_name)
        collection_id = KNOWN_COLLECTIONS.get(normalized)

        if not collection_id:
            # Try searching
            collection_id, _ = await self._search_collection(franchise_name)

        if not collection_id:
            return None

        movies = await self._get_collection(collection_id)
        if not movies:
            return None

        # Return the newest one
        return movies[-1]

    async def interpret(
        self, query: str, year: int | None = None
    ) -> QueryInterpretation:
        """Interpret a movie query.

        Args:
            query: Natural language query
            year: Optional year hint

        Returns:
            Interpretation with movie targets
        """
        original = query
        normalized = self._normalize_query(query)

        # Check for "latest/newest" pattern first
        if self._is_latest_query(query):
            base_title = self._extract_base_title(query)

            # Check if it's a franchise
            if base_title in KNOWN_COLLECTIONS or self._is_franchise_query(base_title + " movies"):
                movie = await self._get_latest_in_franchise(base_title)
                if movie:
                    return QueryInterpretation(
                        query_type="latest",
                        movies=[movie],
                        original_query=original,
                        interpretation=f"The newest {base_title} movie: {movie.title} ({movie.year})",
                    )

            # Otherwise search for the base title preferring recent
            movie = await self._search_movie(base_title)
            if movie:
                return QueryInterpretation(
                    query_type="latest",
                    movies=[movie],
                    original_query=original,
                    interpretation=f"Found: {movie.title} ({movie.year})",
                )

        # Check for franchise query
        if self._is_franchise_query(query):
            franchise_name = self._extract_franchise_name(query)

            # Check known collections
            collection_id = KNOWN_COLLECTIONS.get(franchise_name)
            collection_name = None

            if not collection_id:
                collection_id, collection_name = await self._search_collection(franchise_name)

            if collection_id:
                movies = await self._get_collection(collection_id)
                if movies:
                    return QueryInterpretation(
                        query_type="franchise",
                        movies=movies,
                        original_query=original,
                        interpretation=f"Found {len(movies)} movies in the {collection_name or franchise_name} franchise",
                        collection_name=collection_name or franchise_name,
                    )

            # Maybe it's a person (director/actor)
            movies = await self._get_person_movies(franchise_name, as_director=True)
            if movies:
                return QueryInterpretation(
                    query_type="filmography",
                    movies=movies[:10],  # Limit to recent 10
                    original_query=original,
                    interpretation=f"Found {len(movies)} movies directed by {franchise_name}",
                )

        # Check for known author
        for author, known_movies in KNOWN_AUTHORS.items():
            if author in normalized:
                if known_movies:
                    movies = [MovieTarget(title=t) for t in known_movies]
                    return QueryInterpretation(
                        query_type="multiple",
                        movies=movies,
                        original_query=original,
                        interpretation=f"Movies based on {author}'s work",
                    )
                # For authors with many adaptations, just note it
                return QueryInterpretation(
                    query_type="multiple",
                    movies=[],
                    original_query=original,
                    interpretation=f"{author} has many adaptations - please be more specific",
                )

        # Check for "X movies" pattern (person filmography)
        match = re.match(r"^(.+?)\s+(movies|films)$", normalized)
        if match:
            person_name = match.group(1)
            # Try as director first
            movies = await self._get_person_movies(person_name, as_director=True)
            if movies:
                return QueryInterpretation(
                    query_type="filmography",
                    movies=movies[:10],
                    original_query=original,
                    interpretation=f"Movies directed by {person_name}",
                )

        # Default: single movie search
        movie = await self._search_movie(query, year)
        if movie:
            return QueryInterpretation(
                query_type="single",
                movies=[movie],
                original_query=original,
                interpretation=f"Found: {movie.title} ({movie.year})",
            )

        # Nothing found
        return QueryInterpretation(
            query_type="single",
            movies=[],
            original_query=original,
            interpretation=f"Couldn't find anything matching '{query}'",
        )
