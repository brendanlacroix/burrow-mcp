"""MCP handlers for movie downloads via PTP and Synology.

Voice-optimized responses: concise and conversational.
"""

import asyncio
import logging
from typing import Any

from services.ptp import PTPClient, PTPMovie, PTPAuthError, PTPRateLimitError
from services.synology import SynologyClient, SynologyAuthError, DownloadStatus
from services.torrent_selector import TorrentSelector, QualityPreferences
from services.movie_query import MovieQueryInterpreter, MovieTarget

from utils.retry import CircuitBreakerOpen

logger = logging.getLogger(__name__)


class DownloadHandlers:
    """Handlers for movie download tools."""

    def __init__(
        self,
        ptp_client: PTPClient,
        synology_client: SynologyClient,
        tmdb_api_key: str | None = None,
    ):
        """Initialize download handlers.

        Args:
            ptp_client: Configured PTP client
            synology_client: Configured Synology client
            tmdb_api_key: TMDB API key for query interpretation
        """
        self.ptp = ptp_client
        self.synology = synology_client
        self.query_interpreter = MovieQueryInterpreter(tmdb_api_key)
        self.torrent_selector = TorrentSelector()

    async def download_movie(self, args: dict[str, Any]) -> dict[str, Any]:
        """Download a movie from PTP to Synology NAS.

        Handles single movies, franchises, filmographies, and "newest" requests.

        Args:
            args: {
                query: Movie title or description
                year: Optional year for disambiguation
                prefer_4k: Whether to prefer 4K (default False)
            }

        Returns:
            Voice-friendly response dict
        """
        query = args.get("query", "")
        year = args.get("year")
        prefer_4k = args.get("prefer_4k", False)

        if not query:
            return {"error": "No movie specified"}

        # Check service availability
        if not self.ptp.is_configured:
            return {"error": "PTP credentials not configured"}
        if not self.synology.is_configured:
            return {"error": "Synology not configured"}

        # Update quality preferences
        if prefer_4k:
            self.torrent_selector.prefs.prefer_4k = True

        try:
            # Interpret the query
            interpretation = await self.query_interpreter.interpret(query, year)

            if not interpretation.movies:
                return {
                    "success": False,
                    "message": f"Couldn't find anything matching '{query}'",
                }

            # Handle based on query type
            if interpretation.query_type == "single" or interpretation.query_type == "latest":
                return await self._download_single(interpretation.movies[0], prefer_4k)

            elif interpretation.query_type in ("franchise", "filmography", "multiple"):
                return await self._download_multiple(
                    interpretation.movies,
                    interpretation.collection_name or query,
                    prefer_4k,
                )

            else:
                return await self._download_single(interpretation.movies[0], prefer_4k)

        except PTPAuthError:
            return {"error": "PTP authentication failed. Check your credentials."}
        except PTPRateLimitError as e:
            return {"error": f"PTP rate limited. Try again in {e.retry_after:.0f} seconds."}
        except SynologyAuthError:
            return {"error": "Synology authentication failed. Check your credentials."}
        except CircuitBreakerOpen as e:
            return {"error": str(e)}
        except Exception as e:
            logger.exception(f"Download failed: {e}")
            return {"error": f"Download failed: {str(e)}"}

    async def _download_single(
        self, target: MovieTarget, prefer_4k: bool
    ) -> dict[str, Any]:
        """Download a single movie.

        Returns voice-friendly response.
        """
        # Search PTP
        movie = await self.ptp.search_exact(target.title, target.year)

        if not movie:
            return {
                "success": False,
                "message": f"Couldn't find {target.title} on PTP",
            }

        # Select best torrent
        torrent, quality_desc = self.torrent_selector.select_best_with_reason(movie)

        if not torrent:
            rejection = self.torrent_selector.get_rejection_summary(movie)
            return {
                "success": False,
                "message": f"Found {movie.title} but {rejection}",
            }

        # Download torrent file from PTP
        torrent_data = await self.ptp.download_torrent(torrent.torrent_id)
        if not torrent_data:
            return {
                "success": False,
                "message": f"Failed to download torrent file from PTP",
            }

        # Add to Synology
        filename = f"{movie.title} ({movie.year}).torrent"
        result = await self.synology.add_torrent(torrent_data, filename)

        if not result:
            return {
                "success": False,
                "message": f"Failed to add torrent to Synology",
            }

        # Voice-friendly response (no size - not useful for voice)
        return {
            "success": True,
            "message": f"Downloading {movie.title} ({movie.year}), {quality_desc}.",
            "movie": {
                "title": movie.title,
                "year": movie.year,
                "quality": quality_desc,
            },
        }

    async def _download_multiple(
        self,
        targets: list[MovieTarget],
        collection_name: str,
        prefer_4k: bool,
    ) -> dict[str, Any]:
        """Download multiple movies with rate limiting.

        Returns voice-friendly summary.
        """
        successful = []
        failed = []
        not_found = []

        for i, target in enumerate(targets):
            # Rate limit between requests
            if i > 0:
                await asyncio.sleep(1.5)

            try:
                # Search PTP
                movie = await self.ptp.search_exact(target.title, target.year)

                if not movie:
                    not_found.append(target.title)
                    continue

                # Select best torrent
                torrent, quality_desc = self.torrent_selector.select_best_with_reason(movie)

                if not torrent:
                    failed.append((target.title, self.torrent_selector.get_rejection_summary(movie)))
                    continue

                # Download torrent file
                torrent_data = await self.ptp.download_torrent(torrent.torrent_id)
                if not torrent_data:
                    failed.append((target.title, "couldn't download torrent file"))
                    continue

                # Add to Synology
                filename = f"{movie.title} ({movie.year}).torrent"
                result = await self.synology.add_torrent(torrent_data, filename)

                if result:
                    successful.append({
                        "title": movie.title,
                        "year": movie.year,
                        "quality": quality_desc,
                    })
                else:
                    failed.append((target.title, "couldn't add to Synology"))

            except Exception as e:
                logger.warning(f"Failed to download {target.title}: {e}")
                failed.append((target.title, str(e)))

        # Build voice-friendly response
        return self._build_batch_response(
            collection_name, successful, failed, not_found
        )

    def _build_batch_response(
        self,
        collection_name: str,
        successful: list[dict],
        failed: list[tuple[str, str]],
        not_found: list[str],
    ) -> dict[str, Any]:
        """Build a voice-friendly batch response."""
        total_requested = len(successful) + len(failed) + len(not_found)

        if not successful and not failed:
            return {
                "success": False,
                "message": f"Couldn't find any {collection_name} movies on PTP",
            }

        if not successful:
            return {
                "success": False,
                "message": f"Found {total_requested} {collection_name} movies but none met quality requirements",
            }

        # Build success message
        if len(successful) == 1:
            m = successful[0]
            message = f"Downloading {m['title']} ({m['year']}), {m['quality']}"
        elif len(successful) <= 3:
            titles = [m["title"] for m in successful]
            message = f"Downloading {len(successful)} {collection_name} movies: {', '.join(titles)}"
        else:
            message = f"Downloading {len(successful)} {collection_name} movies"

        # Add failure info if partial success
        if not_found:
            if len(not_found) <= 2:
                message += f". Couldn't find {' or '.join(not_found)}"
            else:
                message += f". {len(not_found)} weren't found on PTP"

        if failed:
            quality_failures = [f[0] for f in failed if "quality" in f[1].lower() or "1080p" in f[1].lower()]
            if quality_failures:
                if len(quality_failures) <= 2:
                    message += f". {' and '.join(quality_failures)} only had low quality releases"
                else:
                    message += f". {len(quality_failures)} only had low quality releases"

        return {
            "success": True,
            "message": message,
            "downloaded": successful,
            "not_found": not_found,
            "failed": [{"title": f[0], "reason": f[1]} for f in failed],
            "summary": {
                "total_requested": total_requested,
                "downloaded": len(successful),
                "not_found": len(not_found),
                "failed": len(failed),
            },
        }

    async def download_status(self, args: dict[str, Any]) -> dict[str, Any]:
        """Check current download status on Synology.

        Returns:
            Voice-friendly status summary
        """
        if not self.synology.is_configured:
            return {"error": "Synology not configured"}

        try:
            tasks = await self.synology.get_active_downloads()

            if not tasks:
                # Check if there are any completed recent downloads
                all_tasks = await self.synology.list_tasks()
                completed = [
                    t for t in all_tasks
                    if t.status in (DownloadStatus.FINISHED, DownloadStatus.SEEDING)
                ]

                if completed:
                    return {
                        "success": True,
                        "message": f"Nothing downloading right now. {len(completed)} completed downloads seeding.",
                        "active_count": 0,
                        "seeding_count": len(completed),
                    }

                return {
                    "success": True,
                    "message": "Nothing downloading right now.",
                    "active_count": 0,
                }

            # Build voice-friendly status
            downloading = [t for t in tasks if t.status == DownloadStatus.DOWNLOADING]
            waiting = [t for t in tasks if t.status == DownloadStatus.WAITING]

            if len(downloading) == 1:
                d = downloading[0]
                eta_str = f", about {d.eta_formatted} left" if d.eta_formatted else ""
                message = f"{d.title} is {d.progress_percent:.0f}% done{eta_str}"
                if waiting:
                    message += f". {len(waiting)} more queued."
            elif downloading:
                # Multiple active
                summaries = []
                for d in downloading[:3]:  # Top 3
                    eta_str = f" ({d.eta_formatted} left)" if d.eta_formatted else ""
                    summaries.append(f"{d.title} at {d.progress_percent:.0f}%{eta_str}")
                message = f"{len(downloading)} movies downloading: " + ". ".join(summaries)
                if waiting:
                    message += f". {len(waiting)} more queued."
            else:
                # Only waiting
                message = f"{len(waiting)} movies queued, waiting to start"

            return {
                "success": True,
                "message": message,
                "active_count": len(downloading),
                "queued_count": len(waiting),
                "downloads": [t.to_dict() for t in tasks],
            }

        except SynologyAuthError:
            return {"error": "Synology authentication failed"}
        except CircuitBreakerOpen as e:
            return {"error": str(e)}
        except Exception as e:
            logger.exception(f"Status check failed: {e}")
            return {"error": f"Failed to check status: {str(e)}"}
