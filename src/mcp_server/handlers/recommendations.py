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

    async def discover_content(self, args: dict[str, Any]) -> dict[str, Any]:
        """Discover content by genre or mood."""
        media_type = args.get("media_type", "movie")
        genre = args.get("genre")
        mood = args.get("mood")
        min_rating = args.get("min_rating")
        exclude = args.get("exclude", [])
        limit = args.get("limit", 5)

        if not genre and not mood:
            return {
                "error": "Please specify a genre or mood",
                "hint": "Try genre='action' or mood='scary'",
            }

        try:
            # Get viewing history to also exclude recently watched
            recent = await self.store.get_recently_watched(limit=20)
            exclude_titles = set(exclude)
            for item in recent:
                title = item.get("title") or item.get("series_name")
                if title:
                    exclude_titles.add(title)

            results = await self.tv_metadata.discover(
                media_type=media_type,
                genre=genre,
                mood=mood,
                min_rating=min_rating,
                limit=limit + len(exclude_titles),  # Get extra to filter
            )

            # Filter out excluded
            filtered = [
                r for r in results
                if r.title.lower() not in {t.lower() for t in exclude_titles}
            ][:limit]

            if not filtered:
                return {
                    "results": [],
                    "message": f"No {media_type}s found matching your criteria. Try broadening your search.",
                }

            return {
                "results": [r.to_dict() for r in filtered],
                "count": len(filtered),
                "query": {
                    "type": media_type,
                    "genre": genre,
                    "mood": mood,
                },
            }

        except Exception as e:
            logger.error(f"Failed to discover content: {e}")
            return {
                "error": "Failed to discover content",
                "message": str(e),
            }

    async def find_similar(self, args: dict[str, Any]) -> dict[str, Any]:
        """Find content similar to a given title."""
        title = args.get("title")
        media_type = args.get("media_type")
        exclude = args.get("exclude", [])
        limit = args.get("limit", 5)

        if not title:
            return {"error": "title is required"}

        try:
            # Also exclude recently watched
            recent = await self.store.get_recently_watched(limit=20)
            exclude_titles = list(exclude)
            for item in recent:
                t = item.get("title") or item.get("series_name")
                if t and t.lower() not in {e.lower() for e in exclude_titles}:
                    exclude_titles.append(t)

            results = await self.tv_metadata.find_similar(
                title=title,
                media_type=media_type,
                exclude_titles=exclude_titles,
                limit=limit,
            )

            if not results:
                # Try recommendations as fallback
                results = await self.tv_metadata.get_recommendations_for(
                    title=title,
                    media_type=media_type,
                    exclude_titles=exclude_titles,
                    limit=limit,
                )

            if not results:
                return {
                    "results": [],
                    "similar_to": title,
                    "message": f"Couldn't find anything similar to '{title}'. Try a different title.",
                }

            return {
                "results": [r.to_dict() for r in results],
                "count": len(results),
                "similar_to": title,
            }

        except Exception as e:
            logger.error(f"Failed to find similar content: {e}")
            return {
                "error": "Failed to find similar content",
                "message": str(e),
            }

    async def not_that_try_again(self, args: dict[str, Any]) -> dict[str, Any]:
        """Find alternatives when a suggestion is rejected."""
        rejected = args.get("rejected", [])
        original_query = args.get("original_query", "")
        media_type = args.get("media_type")

        if not rejected:
            return {"error": "rejected list is required"}

        try:
            # Parse the original query to understand what they wanted
            genre = None
            mood = None
            similar_to = None

            query_lower = original_query.lower()

            # Check if it was a "like X" query
            if "like " in query_lower:
                # Extract the reference title
                parts = query_lower.split("like ")
                if len(parts) > 1:
                    similar_to = parts[1].strip()

            # Check for genres/moods in the query
            from recommendation.tv_metadata import MOVIE_GENRES, TV_GENRES, MOOD_TO_GENRES

            for g in MOVIE_GENRES:
                if g in query_lower:
                    genre = g
                    break

            for m in MOOD_TO_GENRES:
                if m in query_lower:
                    mood = m
                    break

            # Determine media type from query if not specified
            if not media_type:
                if "movie" in query_lower:
                    media_type = "movie"
                elif "show" in query_lower or "series" in query_lower or "tv" in query_lower:
                    media_type = "tv"
                else:
                    media_type = "movie"  # Default

            # Build exclusion list
            exclude_titles = list(rejected)

            # Add recently watched to exclusion
            recent = await self.store.get_recently_watched(limit=20)
            for item in recent:
                t = item.get("title") or item.get("series_name")
                if t:
                    exclude_titles.append(t)

            # If it was a "like X" query, find similar
            if similar_to:
                results = await self.tv_metadata.find_similar(
                    title=similar_to,
                    media_type=media_type,
                    exclude_titles=exclude_titles,
                    limit=5,
                )
            elif genre or mood:
                # Genre/mood based discovery
                results = await self.tv_metadata.discover(
                    media_type=media_type,
                    genre=genre,
                    mood=mood,
                    limit=10,
                )
                # Filter out excluded
                results = [
                    r for r in results
                    if r.title.lower() not in {t.lower() for t in exclude_titles}
                ][:5]
            else:
                # If we can't parse the query, find similar to the first rejected item
                results = await self.tv_metadata.find_similar(
                    title=rejected[0],
                    media_type=media_type,
                    exclude_titles=exclude_titles,
                    limit=5,
                )

            if not results:
                return {
                    "results": [],
                    "message": "Couldn't find alternatives. Try being more specific about what you're in the mood for!",
                    "rejected": rejected,
                }

            return {
                "results": [r.to_dict() for r in results],
                "count": len(results),
                "rejected": rejected,
                "message": f"Here are some alternatives (excluding {', '.join(rejected)})",
            }

        except Exception as e:
            logger.error(f"Failed to find alternatives: {e}")
            return {
                "error": "Failed to find alternatives",
                "message": str(e),
            }
