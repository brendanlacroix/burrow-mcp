"""TV recommendation engine based on viewing history.

Analyzes viewing patterns to suggest content you might want to watch.
"""

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from persistence import StateStore

logger = logging.getLogger(__name__)


@dataclass
class Recommendation:
    """A content recommendation."""

    title: str | None = None
    series_name: str | None = None
    app: str | None = None
    genre: str | None = None
    media_type: str | None = None
    reason: str = ""
    score: float = 0.0
    # Additional context
    last_watched: str | None = None
    next_episode: dict[str, int] | None = None  # {"season": X, "episode": Y}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        d: dict[str, Any] = {
            "reason": self.reason,
            "score": round(self.score, 2),
        }

        if self.title:
            d["title"] = self.title
        if self.series_name:
            d["series_name"] = self.series_name
        if self.app:
            d["app"] = self.app
        if self.genre:
            d["genre"] = self.genre
        if self.media_type:
            d["media_type"] = self.media_type
        if self.last_watched:
            d["last_watched"] = self.last_watched
        if self.next_episode:
            d["next_episode"] = self.next_episode

        return d


class RecommendationEngine:
    """Engine for generating TV/movie recommendations.

    Uses viewing history and preferences to suggest content:
    - Continue watching: Shows you've been watching recently
    - Favorites: Shows you watch frequently
    - Same app: Other content on services you use
    - Same genre: Content matching your preferred genres
    - Time-based: Content you typically watch at this time
    """

    def __init__(self, store: StateStore):
        self.store = store

    async def get_recommendations(
        self,
        limit: int = 10,
        include_continue: bool = True,
        include_favorites: bool = True,
        include_discovery: bool = True,
    ) -> list[Recommendation]:
        """Get personalized recommendations.

        Args:
            limit: Maximum number of recommendations
            include_continue: Include "continue watching" suggestions
            include_favorites: Include suggestions based on favorites
            include_discovery: Include discovery suggestions (same genre/app)

        Returns:
            List of recommendations sorted by score
        """
        recommendations: list[Recommendation] = []

        # Get viewing data
        recent = await self.store.get_recently_watched(limit=30)
        frequent = await self.store.get_frequently_watched(days=90, limit=20)
        stats = await self.store.get_viewing_stats(days=30)
        prefs = await self.store.get_content_preferences(liked_only=True)

        # 1. Continue watching (highest priority)
        if include_continue:
            continue_recs = await self._get_continue_watching(recent)
            recommendations.extend(continue_recs)

        # 2. Favorites/frequently watched
        if include_favorites:
            favorite_recs = self._get_favorite_recommendations(frequent, recent)
            recommendations.extend(favorite_recs)

        # 3. Discovery based on patterns
        if include_discovery:
            discovery_recs = self._get_discovery_recommendations(
                stats, prefs, recent, frequent
            )
            recommendations.extend(discovery_recs)

        # Deduplicate by title/series
        seen = set()
        unique_recs = []
        for rec in recommendations:
            key = rec.series_name or rec.title or ""
            if key and key not in seen:
                seen.add(key)
                unique_recs.append(rec)
            elif not key:
                unique_recs.append(rec)

        # Sort by score (descending) and limit
        unique_recs.sort(key=lambda r: r.score, reverse=True)
        return unique_recs[:limit]

    async def _get_continue_watching(
        self, recent: list[dict[str, Any]]
    ) -> list[Recommendation]:
        """Get 'continue watching' recommendations for in-progress shows."""
        recs = []

        # Find TV shows with recent viewing
        shows_seen: dict[str, dict[str, Any]] = {}

        for item in recent:
            series = item.get("series_name")
            if not series:
                continue

            # Track the most recent episode for each series
            if series not in shows_seen:
                shows_seen[series] = item
            else:
                # Check if this is a newer episode
                current = shows_seen[series]
                if item.get("last_watched", "") > current.get("last_watched", ""):
                    shows_seen[series] = item

        # Create recommendations for recent series
        for series, item in shows_seen.items():
            season = item.get("season", 1)
            episode = item.get("episode", 1)

            # Suggest next episode
            next_ep = {"season": season, "episode": episode + 1}

            rec = Recommendation(
                series_name=series,
                app=item.get("app"),
                genre=item.get("genre"),
                media_type="tvshow",
                reason="Continue watching",
                score=0.95,  # High priority for continue watching
                last_watched=item.get("last_watched"),
                next_episode=next_ep,
            )
            recs.append(rec)

        return recs[:5]  # Limit continue watching

    def _get_favorite_recommendations(
        self,
        frequent: list[dict[str, Any]],
        recent: list[dict[str, Any]],
    ) -> list[Recommendation]:
        """Get recommendations based on frequently watched content."""
        recs = []
        recent_titles = {
            r.get("series_name") or r.get("title")
            for r in recent[:10]
        }

        for item in frequent:
            title = item.get("series_name") or item.get("title")
            if not title:
                continue

            # Skip if recently watched (already in continue watching)
            if title in recent_titles:
                continue

            watch_count = item.get("watch_count", 1)
            last_watched = item.get("last_watched", "")

            # Calculate time since last watch
            days_since = self._days_since(last_watched)

            # Higher score for shows not watched recently but frequently watched
            score = min(0.9, 0.5 + (watch_count * 0.05))

            # Boost score if it's been a while (might want to revisit)
            if days_since > 7:
                score += 0.1

            reason = f"Watched {watch_count}x"
            if days_since > 14:
                reason += f" (last {days_since} days ago)"

            rec = Recommendation(
                title=item.get("title"),
                series_name=item.get("series_name"),
                app=item.get("app"),
                genre=item.get("genre"),
                media_type=item.get("media_type"),
                reason=reason,
                score=score,
                last_watched=last_watched,
            )
            recs.append(rec)

        return recs[:5]  # Limit favorites

    def _get_discovery_recommendations(
        self,
        stats: dict[str, Any],
        prefs: list[dict[str, Any]],
        recent: list[dict[str, Any]],
        frequent: list[dict[str, Any]],
    ) -> list[Recommendation]:
        """Get discovery recommendations based on viewing patterns."""
        recs = []

        # Get top apps and genres
        top_apps = list(stats.get("by_app", {}).keys())[:3]
        top_genres = list(stats.get("by_genre", {}).keys())[:3]

        # Get liked genres from preferences
        liked_genres = {p.get("genre") for p in prefs if p.get("genre")}

        # Combine with watched genres
        preferred_genres = list(liked_genres | set(top_genres))[:5]

        # Generate genre-based suggestions
        for genre in preferred_genres:
            if not genre:
                continue

            rec = Recommendation(
                genre=genre,
                reason=f"You enjoy {genre} content",
                score=0.6 + random.random() * 0.2,  # Slight randomization
            )
            recs.append(rec)

        # Generate app-based suggestions
        for app in top_apps:
            if not app:
                continue

            # Suggest exploring more on frequently used apps
            app_stats = stats.get("by_app", {}).get(app, {})
            count = app_stats.get("count", 0)

            if count > 5:
                rec = Recommendation(
                    app=app,
                    reason=f"Explore more on {app} (watched {count} shows)",
                    score=0.5 + (count / 50),  # Scale by usage
                )
                recs.append(rec)

        # Time-based suggestion
        current_hour = datetime.now().hour
        if 18 <= current_hour <= 23:
            # Evening - prime TV time
            rec = Recommendation(
                reason="Evening movie time",
                media_type="movie",
                score=0.55,
            )
            recs.append(rec)
        elif 12 <= current_hour <= 14:
            # Lunch time - short content
            rec = Recommendation(
                reason="Quick watch for lunch",
                media_type="tvshow",
                score=0.45,
            )
            recs.append(rec)

        return recs

    def _days_since(self, timestamp: str | None) -> int:
        """Calculate days since a timestamp."""
        if not timestamp:
            return 999

        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            delta = datetime.now(dt.tzinfo) - dt if dt.tzinfo else datetime.now() - dt
            return max(0, delta.days)
        except (ValueError, TypeError):
            return 999

    async def get_what_to_watch(
        self, mood: str | None = None
    ) -> dict[str, Any]:
        """Get a 'what to watch' suggestion for people who can't decide.

        Args:
            mood: Optional mood hint (e.g., "something light", "action", "comedy")

        Returns:
            A single focused suggestion with reasoning
        """
        # Get all recommendations
        recs = await self.get_recommendations(limit=20)

        if not recs:
            # No viewing history - return discovery suggestion
            return {
                "suggestion": "Start exploring!",
                "reason": "No viewing history yet. Try browsing Netflix or Hulu to get started.",
                "apps_available": [],
            }

        # Filter by mood if provided
        if mood:
            mood_lower = mood.lower()
            mood_recs = [
                r for r in recs
                if (r.genre and mood_lower in r.genre.lower()) or
                   (r.reason and mood_lower in r.reason.lower())
            ]
            if mood_recs:
                recs = mood_recs

        # Pick top recommendation
        top = recs[0]

        # Build suggestion
        suggestion: dict[str, Any] = {}

        if top.series_name:
            if top.next_episode:
                suggestion["watch"] = (
                    f"{top.series_name} - S{top.next_episode['season']}E{top.next_episode['episode']}"
                )
            else:
                suggestion["watch"] = top.series_name
        elif top.title:
            suggestion["watch"] = top.title
        elif top.genre:
            suggestion["watch"] = f"Something in {top.genre}"
        elif top.app:
            suggestion["watch"] = f"Browse {top.app}"
        else:
            suggestion["watch"] = "Check what's new on your streaming apps"

        suggestion["reason"] = top.reason
        suggestion["score"] = top.score

        if top.app:
            suggestion["open_app"] = top.app

        # Add alternatives
        alternatives = [
            r.series_name or r.title or r.genre or r.app
            for r in recs[1:4]
            if r.series_name or r.title or r.genre or r.app
        ]
        if alternatives:
            suggestion["alternatives"] = alternatives

        return suggestion

    async def get_streaming_services_summary(
        self, available_apps: list[str] | None = None
    ) -> dict[str, Any]:
        """Get a summary of streaming service usage.

        Args:
            available_apps: List of apps available on the device

        Returns:
            Summary of which services are used most
        """
        stats = await self.store.get_viewing_stats(days=30)
        by_app = stats.get("by_app", {})

        summary = {
            "services": {},
            "total_watch_time_hours": round(stats.get("total_watch_time", 0) / 3600, 1),
            "total_sessions": stats.get("total_sessions", 0),
        }

        # Rank services by usage
        for app, data in by_app.items():
            summary["services"][app] = {
                "sessions": data.get("count", 0),
                "watch_time_hours": round(data.get("total_time", 0) / 3600, 1),
            }

        # Note which available apps aren't being used
        if available_apps:
            used_apps = set(by_app.keys())
            unused = [a for a in available_apps if a not in used_apps]
            if unused:
                summary["unused_services"] = unused

        return summary
