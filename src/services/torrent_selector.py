"""Torrent selection logic for PTP downloads.

Implements quality preferences with 1080p minimum requirement.
"""

import logging
from dataclasses import dataclass
from typing import Any

from services.ptp import PTPTorrent, PTPMovie

logger = logging.getLogger(__name__)


@dataclass
class QualityPreferences:
    """User quality preferences for torrent selection."""

    prefer_4k: bool = False
    max_size_gb: float = 30.0  # Hard limit for any movie
    min_seeders: int = 1

    # Resolution requirements - 1080p is the minimum
    min_resolution: int = 1080

    # Source priority (higher = better)
    source_priority: dict[str, int] | None = None

    # Codec priority (higher = better)
    codec_priority: dict[str, int] | None = None

    def __post_init__(self):
        if self.source_priority is None:
            self.source_priority = {
                "Blu-ray": 100,
                "HD-DVD": 90,
                "WEB": 80,
                "HDTV": 70,
                "DVD": 30,  # Usually SD, but might have upscales
                "VHS": 10,
                "TV": 10,
            }
        if self.codec_priority is None:
            # Prefer x264 for compatibility, x265 is fine too
            self.codec_priority = {
                "x264": 100,
                "H.264": 100,
                "x265": 90,
                "H.265": 90,
                "HEVC": 90,
                "VC-1": 70,
                "MPEG-2": 50,
                "XviD": 30,
                "DivX": 30,
            }


@dataclass
class TorrentScore:
    """Scoring breakdown for a torrent."""

    torrent: PTPTorrent
    total_score: float
    resolution_score: float
    source_score: float
    codec_score: float
    gp_score: float
    seeder_score: float
    size_score: float
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "torrent_id": self.torrent.torrent_id,
            "total_score": round(self.total_score, 2),
            "resolution": self.torrent.resolution,
            "source": self.torrent.source,
            "is_gp": self.torrent.is_golden_popcorn,
            "size_gb": round(self.torrent.size_gb, 2),
            "seeders": self.torrent.seeders,
            "rejection_reason": self.rejection_reason,
        }


class TorrentSelector:
    """Selects the best torrent based on quality preferences."""

    def __init__(self, preferences: QualityPreferences | None = None):
        """Initialize selector with preferences.

        Args:
            preferences: Quality preferences (uses defaults if None)
        """
        self.prefs = preferences or QualityPreferences()

    def _meets_minimum_requirements(self, torrent: PTPTorrent) -> tuple[bool, str | None]:
        """Check if torrent meets minimum requirements.

        Returns:
            (passes, rejection_reason)
        """
        # Check resolution minimum (1080p)
        if torrent.resolution_value < self.prefs.min_resolution:
            return False, f"Resolution {torrent.resolution} below minimum 1080p"

        # Check seeders
        if torrent.seeders < self.prefs.min_seeders:
            return False, "No seeders available"

        # Check size limit (30GB hard limit for any movie)
        if torrent.size_gb > self.prefs.max_size_gb:
            return False, f"Size {torrent.size_gb:.1f}GB exceeds {self.prefs.max_size_gb:.0f}GB limit"

        return True, None

    def _score_torrent(self, torrent: PTPTorrent) -> TorrentScore:
        """Score a torrent based on preferences.

        Higher score = better match.
        """
        # Check minimum requirements first
        passes, rejection = self._meets_minimum_requirements(torrent)
        if not passes:
            return TorrentScore(
                torrent=torrent,
                total_score=-1,
                resolution_score=0,
                source_score=0,
                codec_score=0,
                gp_score=0,
                seeder_score=0,
                size_score=0,
                rejection_reason=rejection,
            )

        # Resolution scoring
        # If prefer_4k: 2160p = 100, 1080p = 80
        # If not prefer_4k: 1080p = 100, 2160p = 90 (still good, just not preferred)
        if self.prefs.prefer_4k:
            if torrent.resolution_value >= 2160:
                resolution_score = 100
            elif torrent.resolution_value >= 1080:
                resolution_score = 80
            else:
                resolution_score = 50
        else:
            if torrent.resolution_value >= 2160:
                resolution_score = 90  # 4K is good but not preferred
            elif torrent.resolution_value >= 1080:
                resolution_score = 100  # 1080p is preferred
            else:
                resolution_score = 50

        # Source scoring
        source_score = self.prefs.source_priority.get(torrent.source, 50)

        # Codec scoring
        codec_score = self.prefs.codec_priority.get(torrent.codec, 50)

        # Golden Popcorn bonus (significant)
        gp_score = 50 if torrent.is_golden_popcorn else 0

        # Seeder scoring (more seeders = faster download, but diminishing returns)
        if torrent.seeders >= 50:
            seeder_score = 30
        elif torrent.seeders >= 20:
            seeder_score = 25
        elif torrent.seeders >= 10:
            seeder_score = 20
        elif torrent.seeders >= 5:
            seeder_score = 15
        else:
            seeder_score = 10

        # Size scoring (prefer reasonable sizes)
        if torrent.size_gb <= 15:
            size_score = 20  # Ideal size
        elif torrent.size_gb <= 25:
            size_score = 15  # Good size
        else:
            size_score = 10  # Large but within limit

        # Calculate total with weights
        # Resolution and GP are most important, followed by source, then others
        total_score = (
            resolution_score * 1.5 +  # Weight resolution highly
            gp_score * 1.2 +  # GP is a strong quality indicator
            source_score * 1.0 +
            codec_score * 0.5 +
            seeder_score * 0.3 +
            size_score * 0.3
        )

        return TorrentScore(
            torrent=torrent,
            total_score=total_score,
            resolution_score=resolution_score,
            source_score=source_score,
            codec_score=codec_score,
            gp_score=gp_score,
            seeder_score=seeder_score,
            size_score=size_score,
        )

    def select_best(self, movie: PTPMovie) -> PTPTorrent | None:
        """Select the best torrent for a movie.

        Args:
            movie: Movie with available torrents

        Returns:
            Best matching torrent or None if none meet requirements
        """
        if not movie.torrents:
            logger.warning(f"No torrents available for {movie.title}")
            return None

        # Score all torrents
        scores = [self._score_torrent(t) for t in movie.torrents]

        # Filter to those that pass requirements
        valid_scores = [s for s in scores if s.rejection_reason is None]

        if not valid_scores:
            # Log why all were rejected
            rejections = [s.rejection_reason for s in scores if s.rejection_reason]
            logger.warning(
                f"No valid torrents for {movie.title}. "
                f"Rejections: {set(rejections)}"
            )
            return None

        # Sort by score (highest first)
        valid_scores.sort(key=lambda s: s.total_score, reverse=True)

        best = valid_scores[0]
        logger.info(
            f"Selected torrent for {movie.title}: "
            f"{best.torrent.resolution} {best.torrent.source} "
            f"(GP={best.torrent.is_golden_popcorn}, score={best.total_score:.1f})"
        )

        return best.torrent

    def select_best_with_reason(
        self, movie: PTPMovie
    ) -> tuple[PTPTorrent | None, str]:
        """Select best torrent and return human-readable reason.

        Args:
            movie: Movie with available torrents

        Returns:
            (torrent, reason_string) - torrent may be None
        """
        if not movie.torrents:
            return None, "no torrents available"

        # Score all torrents
        scores = [self._score_torrent(t) for t in movie.torrents]
        valid_scores = [s for s in scores if s.rejection_reason is None]

        if not valid_scores:
            # Find the most common rejection reason
            rejections = [s.rejection_reason for s in scores if s.rejection_reason]
            if "below minimum 1080p" in str(rejections):
                return None, "only has torrents below 1080p quality"
            elif "No seeders" in str(rejections):
                return None, "no seeded torrents available"
            elif "exceeds" in str(rejections):
                return None, "available torrents exceed size limits"
            return None, "no torrents meet quality requirements"

        valid_scores.sort(key=lambda s: s.total_score, reverse=True)
        best = valid_scores[0]
        torrent = best.torrent

        # Build reason string
        parts = [torrent.resolution, torrent.source]
        if torrent.is_golden_popcorn:
            parts.append("Golden Popcorn")
        reason = ", ".join(parts)

        return torrent, reason

    def get_rejection_summary(self, movie: PTPMovie) -> str:
        """Get a summary of why torrents were rejected.

        Args:
            movie: Movie to analyze

        Returns:
            Human-readable summary
        """
        if not movie.torrents:
            return "No torrents available on PTP"

        scores = [self._score_torrent(t) for t in movie.torrents]
        rejections = {}

        for score in scores:
            if score.rejection_reason:
                key = score.rejection_reason.split()[0]  # First word as category
                rejections[key] = rejections.get(key, 0) + 1

        if not rejections:
            return "All torrents meet requirements"

        # Find primary rejection reason
        if any("Resolution" in r for r in rejections):
            return f"Only has releases below 1080p ({len(movie.torrents)} total)"
        if any("seeders" in str(r).lower() for r in rejections):
            return "No seeded releases available"
        if any("Size" in r for r in rejections):
            return "Available releases exceed size limits"

        return f"No releases meet quality requirements ({len(movie.torrents)} checked)"
