"""MCP handlers for TV recommendations."""

import logging
from typing import Any

from persistence import StateStore
from recommendation import RecommendationEngine
from recommendation.tv_metadata import TVMetadata, get_streaming_service

logger = logging.getLogger(__name__)


class RecommendationHandlers:
    """Handlers for TV recommendation tools."""

    def __init__(self, store: StateStore, tmdb_api_key: str | None = None):
        self.store = store
        self.engine = RecommendationEngine(store)
        self.tv_metadata = TVMetadata(tmdb_api_key)

    async def get_recommendations(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get personalized TV recommendations."""
        limit = args.get("limit", 10)
        include_continue = args.get("include_continue", True)
        include_favorites = args.get("include_favorites", True)
        include_discovery = args.get("include_discovery", True)

        try:
            recs = await self.engine.get_recommendations(
                limit=limit,
                include_continue=include_continue,
                include_favorites=include_favorites,
                include_discovery=include_discovery,
            )

            if not recs:
                return {
                    "recommendations": [],
                    "message": (
                        "No recommendations yet! Start watching some content "
                        "and we'll learn your preferences."
                    ),
                }

            return {
                "recommendations": [r.to_dict() for r in recs],
                "count": len(recs),
            }

        except Exception as e:
            logger.error(f"Failed to get recommendations: {e}")
            return {
                "error": "Failed to generate recommendations",
                "message": str(e),
            }

    async def what_to_watch(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get a single 'what to watch' suggestion."""
        mood = args.get("mood")

        try:
            suggestion = await self.engine.get_what_to_watch(mood=mood)
            return suggestion

        except Exception as e:
            logger.error(f"Failed to get what to watch: {e}")
            return {
                "suggestion": "Browse your streaming apps",
                "reason": "Couldn't generate a personalized suggestion right now",
                "error": str(e),
            }

    async def get_viewing_history(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get viewing history."""
        device_id = args.get("device_id")
        app = args.get("app")
        days = args.get("days", 30)
        limit = args.get("limit", 50)

        try:
            history = await self.store.get_viewing_history(
                device_id=device_id,
                app=app,
                days=days,
                limit=limit,
            )

            # Also get recently watched for summary
            recent = await self.store.get_recently_watched(limit=10)

            return {
                "history": history,
                "count": len(history),
                "recent_titles": [
                    r.get("series_name") or r.get("title")
                    for r in recent
                    if r.get("series_name") or r.get("title")
                ][:5],
            }

        except Exception as e:
            logger.error(f"Failed to get viewing history: {e}")
            return {
                "error": "Failed to retrieve viewing history",
                "message": str(e),
            }

    async def get_viewing_stats(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get viewing statistics."""
        days = args.get("days", 30)

        try:
            stats = await self.store.get_viewing_stats(days=days)

            # Format for readability
            result = {
                "period_days": days,
                "total_sessions": stats.get("total_sessions", 0),
                "total_watch_time_hours": round(
                    stats.get("total_watch_time", 0) / 3600, 1
                ),
            }

            # Add top apps
            by_app = stats.get("by_app", {})
            if by_app:
                result["top_apps"] = [
                    {
                        "app": app,
                        "sessions": data.get("count", 0),
                        "hours": round(data.get("total_time", 0) / 3600, 1),
                    }
                    for app, data in list(by_app.items())[:5]
                ]

            # Add top genres
            by_genre = stats.get("by_genre", {})
            if by_genre:
                result["top_genres"] = list(by_genre.keys())[:5]

            # Add media type breakdown
            by_type = stats.get("by_media_type", {})
            if by_type:
                result["by_media_type"] = by_type

            # Get frequently watched for favorites
            frequent = await self.store.get_frequently_watched(days=days, limit=5)
            if frequent:
                result["favorites"] = [
                    {
                        "name": f.get("series_name") or f.get("title"),
                        "app": f.get("app"),
                        "watch_count": f.get("watch_count"),
                    }
                    for f in frequent
                    if f.get("series_name") or f.get("title")
                ]

            return result

        except Exception as e:
            logger.error(f"Failed to get viewing stats: {e}")
            return {
                "error": "Failed to retrieve viewing statistics",
                "message": str(e),
            }

    async def rate_content(self, args: dict[str, Any]) -> dict[str, Any]:
        """Rate content to improve recommendations."""
        title = args.get("title")
        series_name = args.get("series_name")
        liked = args.get("liked")
        rating = args.get("rating")

        if not title and not series_name:
            return {
                "error": "Must provide either 'title' (for movies) or 'series_name' (for shows)",
            }

        if liked is None and rating is None:
            return {
                "error": "Must provide either 'liked' (true/false) or 'rating' (1-5)",
            }

        try:
            await self.store.set_content_preference(
                title=title,
                series_name=series_name,
                rating=rating,
                liked=liked,
            )

            content_name = series_name or title
            response = {
                "success": True,
                "content": content_name,
            }

            if liked is not None:
                response["liked"] = liked
            if rating is not None:
                response["rating"] = rating

            response["message"] = f"Thanks! Your rating for '{content_name}' will improve future recommendations."

            return response

        except Exception as e:
            logger.error(f"Failed to rate content: {e}")
            return {
                "error": "Failed to save rating",
                "message": str(e),
            }

    async def seed_favorites(self, args: dict[str, Any]) -> dict[str, Any]:
        """Seed initial favorites without watching them first."""
        shows = args.get("shows", [])

        if not shows:
            return {
                "error": "No shows provided",
                "message": "Provide a list of shows with 'series_name' and optionally 'app'",
            }

        try:
            count = await self.store.seed_favorites(shows)

            return {
                "success": True,
                "added": count,
                "message": f"Added {count} shows to your favorites!",
            }

        except Exception as e:
            logger.error(f"Failed to seed favorites: {e}")
            return {
                "error": "Failed to seed favorites",
                "message": str(e),
            }

    async def follow_show(self, args: dict[str, Any]) -> dict[str, Any]:
        """Follow a show to track new episodes."""
        series_name = args.get("series_name")
        app = args.get("app")

        if not series_name:
            return {"error": "series_name is required"}

        try:
            # Try to get TMDb info for the show
            tmdb_id = None
            status = None

            show = await self.tv_metadata.get_show_by_name(series_name)
            if show:
                tmdb_id = show.tmdb_id
                status = show.status
                # If app not specified, try to determine from networks
                if not app and show.networks:
                    app = get_streaming_service(show.networks)

            await self.store.follow_show(
                series_name=series_name,
                app=app,
                tmdb_id=tmdb_id,
                status=status,
            )

            result = {
                "success": True,
                "series_name": series_name,
                "message": f"Now following '{series_name}'",
            }

            if app:
                result["app"] = app
            if status:
                result["status"] = status
            if show and show.next_episode:
                result["next_episode"] = show.next_episode.to_dict()

            return result

        except Exception as e:
            logger.error(f"Failed to follow show: {e}")
            return {
                "error": "Failed to follow show",
                "message": str(e),
            }

    async def unfollow_show(self, args: dict[str, Any]) -> dict[str, Any]:
        """Stop following a show."""
        series_name = args.get("series_name")

        if not series_name:
            return {"error": "series_name is required"}

        try:
            removed = await self.store.unfollow_show(series_name)

            if removed:
                return {
                    "success": True,
                    "series_name": series_name,
                    "message": f"No longer following '{series_name}'",
                }
            else:
                return {
                    "success": False,
                    "series_name": series_name,
                    "message": f"'{series_name}' was not in your followed shows",
                }

        except Exception as e:
            logger.error(f"Failed to unfollow show: {e}")
            return {
                "error": "Failed to unfollow show",
                "message": str(e),
            }

    async def get_followed_shows(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get list of followed shows."""
        try:
            shows = await self.store.get_followed_shows()

            return {
                "shows": shows,
                "count": len(shows),
            }

        except Exception as e:
            logger.error(f"Failed to get followed shows: {e}")
            return {
                "error": "Failed to get followed shows",
                "message": str(e),
            }

    async def check_new_episodes(self, args: dict[str, Any]) -> dict[str, Any]:
        """Check for new episodes of followed shows."""
        days_ahead = args.get("days_ahead", 7)

        try:
            followed = await self.store.get_followed_shows()

            if not followed:
                return {
                    "upcoming": [],
                    "message": "No shows being followed. Use follow_show to add some!",
                }

            # Get TMDb IDs for shows that have them
            tmdb_ids = [s["tmdb_id"] for s in followed if s.get("tmdb_id")]

            if not tmdb_ids:
                return {
                    "upcoming": [],
                    "message": "No TMDb IDs for followed shows. TMDb API key may not be configured.",
                }

            # Check for upcoming episodes
            upcoming = await self.tv_metadata.get_upcoming_episodes(
                tmdb_ids, days_ahead=days_ahead
            )

            # Enhance with where to watch
            for ep in upcoming:
                show_info = next(
                    (s for s in followed if s.get("tmdb_id") == ep["tmdb_id"]),
                    None
                )
                if show_info and show_info.get("app"):
                    ep["where_to_watch"] = show_info["app"]

            result = {
                "upcoming": upcoming,
                "count": len(upcoming),
                "days_ahead": days_ahead,
            }

            if upcoming:
                # Friendly summary
                today_eps = [e for e in upcoming if e["days_until"] == 0]
                if today_eps:
                    result["today"] = [e["show"] for e in today_eps]

            return result

        except Exception as e:
            logger.error(f"Failed to check new episodes: {e}")
            return {
                "error": "Failed to check for new episodes",
                "message": str(e),
            }
