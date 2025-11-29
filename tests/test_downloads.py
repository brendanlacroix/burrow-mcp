"""Tests for PTP-Synology download integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.ptp import PTPTorrent, PTPMovie
from services.torrent_selector import TorrentSelector, QualityPreferences, TorrentScore
from services.movie_query import MovieQueryInterpreter, QueryInterpretation, MovieTarget


class TestTorrentSelector:
    """Tests for torrent quality selection logic."""

    def make_torrent(
        self,
        resolution: str = "1080p",
        source: str = "Blu-ray",
        codec: str = "x264",
        size_gb: float = 10.0,
        seeders: int = 10,
        is_gp: bool = False,
    ) -> PTPTorrent:
        """Helper to create test torrents."""
        return PTPTorrent(
            torrent_id=1,
            quality="High Definition",
            resolution=resolution,
            source=source,
            codec=codec,
            container="MKV",
            size_bytes=int(size_gb * 1024 ** 3),
            seeders=seeders,
            leechers=5,
            snatched=100,
            is_golden_popcorn=is_gp,
            is_scene=False,
            release_name=f"Movie.{resolution}.{source}.{codec}",
        )

    def make_movie(self, torrents: list[PTPTorrent]) -> PTPMovie:
        """Helper to create test movies."""
        return PTPMovie(
            movie_id=12345,
            title="Test Movie",
            year=2023,
            torrents=torrents,
        )

    def test_rejects_720p(self):
        """Should reject 720p torrents (below 1080p minimum)."""
        selector = TorrentSelector()
        torrents = [self.make_torrent(resolution="720p")]
        movie = self.make_movie(torrents)

        result = selector.select_best(movie)
        assert result is None

    def test_rejects_sd(self):
        """Should reject SD torrents."""
        selector = TorrentSelector()
        torrents = [self.make_torrent(resolution="SD")]
        movie = self.make_movie(torrents)

        result = selector.select_best(movie)
        assert result is None

    def test_accepts_1080p(self):
        """Should accept 1080p torrents."""
        selector = TorrentSelector()
        torrents = [self.make_torrent(resolution="1080p")]
        movie = self.make_movie(torrents)

        result = selector.select_best(movie)
        assert result is not None
        assert result.resolution == "1080p"

    def test_accepts_2160p(self):
        """Should accept 4K torrents."""
        selector = TorrentSelector()
        torrents = [self.make_torrent(resolution="2160p")]
        movie = self.make_movie(torrents)

        result = selector.select_best(movie)
        assert result is not None
        assert result.resolution == "2160p"

    def test_prefers_1080p_by_default(self):
        """Without prefer_4k, should prefer 1080p over 4K."""
        selector = TorrentSelector()
        torrents = [
            self.make_torrent(resolution="2160p", size_gb=50),
            self.make_torrent(resolution="1080p", size_gb=10),
        ]
        movie = self.make_movie(torrents)

        result = selector.select_best(movie)
        assert result is not None
        assert result.resolution == "1080p"

    def test_prefers_4k_when_requested(self):
        """With prefer_4k=True, should prefer 4K."""
        prefs = QualityPreferences(prefer_4k=True)
        selector = TorrentSelector(prefs)
        torrents = [
            self.make_torrent(resolution="2160p", size_gb=50),
            self.make_torrent(resolution="1080p", size_gb=10),
        ]
        movie = self.make_movie(torrents)

        result = selector.select_best(movie)
        assert result is not None
        assert result.resolution == "2160p"

    def test_prefers_golden_popcorn(self):
        """Should prefer Golden Popcorn releases."""
        selector = TorrentSelector()
        torrents = [
            self.make_torrent(resolution="1080p", is_gp=False, seeders=50),
            self.make_torrent(resolution="1080p", is_gp=True, seeders=10),
        ]
        movie = self.make_movie(torrents)

        result = selector.select_best(movie)
        assert result is not None
        assert result.is_golden_popcorn is True

    def test_prefers_bluray_over_web(self):
        """Should prefer Blu-ray source over WEB."""
        selector = TorrentSelector()
        torrents = [
            self.make_torrent(resolution="1080p", source="WEB"),
            self.make_torrent(resolution="1080p", source="Blu-ray"),
        ]
        movie = self.make_movie(torrents)

        result = selector.select_best(movie)
        assert result is not None
        assert result.source == "Blu-ray"

    def test_rejects_no_seeders(self):
        """Should reject torrents with no seeders."""
        selector = TorrentSelector()
        torrents = [self.make_torrent(resolution="1080p", seeders=0)]
        movie = self.make_movie(torrents)

        result = selector.select_best(movie)
        assert result is None

    def test_rejects_oversized_1080p(self):
        """Should reject 1080p torrents over size limit."""
        selector = TorrentSelector()
        torrents = [self.make_torrent(resolution="1080p", size_gb=25)]  # Over 20GB limit
        movie = self.make_movie(torrents)

        result = selector.select_best(movie)
        assert result is None

    def test_accepts_reasonable_size(self):
        """Should accept reasonably sized torrents."""
        selector = TorrentSelector()
        torrents = [self.make_torrent(resolution="1080p", size_gb=15)]
        movie = self.make_movie(torrents)

        result = selector.select_best(movie)
        assert result is not None

    def test_empty_movie_returns_none(self):
        """Should return None for movies with no torrents."""
        selector = TorrentSelector()
        movie = self.make_movie([])

        result = selector.select_best(movie)
        assert result is None

    def test_select_best_with_reason(self):
        """Should return human-readable quality description."""
        selector = TorrentSelector()
        torrents = [self.make_torrent(resolution="1080p", source="Blu-ray", is_gp=True)]
        movie = self.make_movie(torrents)

        torrent, reason = selector.select_best_with_reason(movie)
        assert torrent is not None
        assert "1080p" in reason
        assert "Blu-ray" in reason
        assert "Golden Popcorn" in reason

    def test_rejection_summary_resolution(self):
        """Should explain when only low-res torrents available."""
        selector = TorrentSelector()
        torrents = [self.make_torrent(resolution="720p")]
        movie = self.make_movie(torrents)

        summary = selector.get_rejection_summary(movie)
        assert "1080p" in summary.lower() or "below" in summary.lower()


class TestMovieQueryInterpreter:
    """Tests for natural language query interpretation."""

    @pytest.fixture
    def interpreter(self):
        """Create interpreter without TMDB key (will return empty for API calls)."""
        return MovieQueryInterpreter(tmdb_api_key=None)

    def test_is_franchise_query(self, interpreter):
        """Should detect franchise query patterns."""
        assert interpreter._is_franchise_query("the Mission Impossible movies")
        assert interpreter._is_franchise_query("all the Fast and Furious movies")
        assert interpreter._is_franchise_query("Harry Potter films")
        assert not interpreter._is_franchise_query("Jennifer's Body")

    def test_is_latest_query(self, interpreter):
        """Should detect newest/latest query patterns."""
        assert interpreter._is_latest_query("the new Dune movie")
        assert interpreter._is_latest_query("the newest Marvel movie")
        assert interpreter._is_latest_query("latest Fast and Furious")
        assert not interpreter._is_latest_query("Jennifer's Body")

    def test_extract_franchise_name(self, interpreter):
        """Should extract franchise name from query."""
        assert interpreter._extract_franchise_name("the Mission Impossible movies") == "mission impossible"
        assert interpreter._extract_franchise_name("all the Harry Potter films") == "harry potter"

    def test_extract_base_title(self, interpreter):
        """Should extract base title from 'newest X' queries."""
        assert interpreter._extract_base_title("the new Dune movie") == "dune"
        assert interpreter._extract_base_title("the newest Marvel") == "marvel"

    def test_known_collections_mapping(self, interpreter):
        """Should have mappings for common franchises."""
        from services.movie_query import KNOWN_COLLECTIONS

        assert "mission impossible" in KNOWN_COLLECTIONS
        assert "fast and furious" in KNOWN_COLLECTIONS
        assert "harry potter" in KNOWN_COLLECTIONS
        assert "james bond" in KNOWN_COLLECTIONS
        assert "star wars" in KNOWN_COLLECTIONS


class TestPTPTorrent:
    """Tests for PTPTorrent data class."""

    def test_size_gb_calculation(self):
        """Should calculate size in GB correctly."""
        torrent = PTPTorrent(
            torrent_id=1,
            quality="HD",
            resolution="1080p",
            source="Blu-ray",
            codec="x264",
            container="MKV",
            size_bytes=10 * 1024 * 1024 * 1024,  # 10 GB
            seeders=10,
            leechers=5,
            snatched=100,
            is_golden_popcorn=False,
            is_scene=False,
            release_name="Test",
        )
        assert abs(torrent.size_gb - 10.0) < 0.01

    def test_resolution_value(self):
        """Should return correct numeric resolution."""
        torrent_4k = PTPTorrent(
            torrent_id=1, quality="HD", resolution="2160p", source="Blu-ray",
            codec="x264", container="MKV", size_bytes=0, seeders=1, leechers=0,
            snatched=0, is_golden_popcorn=False, is_scene=False, release_name="Test"
        )
        torrent_1080 = PTPTorrent(
            torrent_id=2, quality="HD", resolution="1080p", source="Blu-ray",
            codec="x264", container="MKV", size_bytes=0, seeders=1, leechers=0,
            snatched=0, is_golden_popcorn=False, is_scene=False, release_name="Test"
        )
        torrent_720 = PTPTorrent(
            torrent_id=3, quality="HD", resolution="720p", source="Blu-ray",
            codec="x264", container="MKV", size_bytes=0, seeders=1, leechers=0,
            snatched=0, is_golden_popcorn=False, is_scene=False, release_name="Test"
        )

        assert torrent_4k.resolution_value == 2160
        assert torrent_1080.resolution_value == 1080
        assert torrent_720.resolution_value == 720
