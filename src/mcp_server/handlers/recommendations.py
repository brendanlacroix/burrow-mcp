"""MCP handlers for TV recommendations."""

import logging
from typing import Any

from persistence import StateStore
from recommendation import RecommendationEngine

logger = logging.getLogger(__name__)


class RecommendationHandlers:
    """Handlers for TV recommendation tools."""

    def __init__(self, store: StateStore):
        self.store = store
        self.engine = RecommendationEngine(store)

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
