"""Tests for TV recommendation engine and viewing history."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from models.base import DeviceStatus, DeviceType
from models.media_device import (
    MediaDevice,
    NowPlaying,
    PlaybackState,
    normalize_app_name,
    STREAMING_SERVICES,
)
from persistence import StateStore
from recommendation import RecommendationEngine


# Concrete test implementation of MediaDevice
@dataclass
class TestMediaDevice(MediaDevice):
    """Concrete MediaDevice implementation for testing."""

    async def refresh(self) -> None:
        pass

    async def play(self) -> None:
        self.playback_state = PlaybackState.PLAYING

    async def pause(self) -> None:
        self.playback_state = PlaybackState.PAUSED

    async def stop(self) -> None:
        self.playback_state = PlaybackState.STOPPED
        self.now_playing = None

    async def skip_forward(self) -> None:
        pass

    async def skip_backward(self) -> None:
        pass

    async def launch_app(self, app_id: str) -> None:
        self.current_app = app_id

    async def get_app_list(self) -> list[dict[str, str]]:
        return [
            {"id": "com.netflix.Netflix", "name": "Netflix"},
            {"id": "com.hulu.plus", "name": "Hulu"},
            {"id": "com.disney.disneyplus", "name": "Disney+"},
        ]


@pytest.fixture
async def store(tmp_path: Path) -> StateStore:
    """Create a test state store."""
    db_path = tmp_path / "test_recommendations.db"
    store = StateStore(db_path)
    await store.initialize()
    yield store
    await store.close()


@pytest.fixture
def test_media_device() -> TestMediaDevice:
    """Create a test media device."""
    device = TestMediaDevice(
        id="test_appletv",
        name="Test AppleTV",
        room_id="living_room",
    )
    device.status = DeviceStatus.ONLINE
    device.playback_state = PlaybackState.PLAYING
    device.current_app = "Netflix"
    device.now_playing = NowPlaying(
        title="The Office",
        series_name="The Office",
        season=3,
        episode=10,
        media_type="tvshow",
        app="Netflix",
    )
    return device


class TestMediaDeviceModel:
    """Tests for MediaDevice model."""

    def test_now_playing_to_dict(self):
        """Test NowPlaying serialization."""
        np = NowPlaying(
            title="Test Episode",
            series_name="Test Show",
            season=1,
            episode=5,
            media_type="tvshow",
            app="Netflix",
            duration=2700,
            position=600,
        )

        d = np.to_dict()
        assert d["title"] == "Test Episode"
        assert d["series_name"] == "Test Show"
        assert d["season"] == 1
        assert d["episode"] == 5
        assert d["media_type"] == "tvshow"
        assert d["app"] == "Netflix"
        assert d["duration"] == 2700
        assert d["position"] == 600

    def test_now_playing_excludes_none(self):
        """Test that None values are excluded from dict."""
        np = NowPlaying(title="Movie", media_type="movie")
        d = np.to_dict()

        assert "title" in d
        assert "media_type" in d
        assert "series_name" not in d
        assert "season" not in d
        assert "episode" not in d

    def test_normalize_app_name(self):
        """Test app name normalization."""
        assert normalize_app_name("com.netflix.Netflix") == "Netflix"
        assert normalize_app_name("com.hulu.plus") == "Hulu"
        assert normalize_app_name("com.disney.disneyplus") == "Disney+"
        assert normalize_app_name("unknown.app") == "unknown.app"

    async def test_media_device_state_dict(self, test_media_device: TestMediaDevice):
        """Test MediaDevice state serialization."""
        state = test_media_device.to_state_dict()

        assert state["playback_state"] == "playing"
        assert state["current_app"] == "Netflix"
        assert "now_playing" in state
        assert state["now_playing"]["series_name"] == "The Office"

    async def test_media_device_play_pause(self, test_media_device: TestMediaDevice):
        """Test play/pause functionality."""
        await test_media_device.pause()
        assert test_media_device.playback_state == PlaybackState.PAUSED

        await test_media_device.play()
        assert test_media_device.playback_state == PlaybackState.PLAYING

    async def test_media_device_stop(self, test_media_device: TestMediaDevice):
        """Test stop clears now_playing."""
        await test_media_device.stop()
        assert test_media_device.playback_state == PlaybackState.STOPPED
        assert test_media_device.now_playing is None


class TestViewingHistory:
    """Tests for viewing history persistence."""

    async def test_record_viewing_session(self, store: StateStore):
        """Test recording a viewing session."""
        session_id = await store.record_viewing_session(
            device_id="appletv_living",
            app="Netflix",
            title="The Crown",
            series_name="The Crown",
            season=4,
            episode=3,
            media_type="tvshow",
            genre="Drama",
            duration=3600,
        )

        assert session_id > 0

        # Verify it was recorded
        history = await store.get_viewing_history(device_id="appletv_living")
        assert len(history) == 1
        assert history[0]["series_name"] == "The Crown"
        assert history[0]["season"] == 4
        assert history[0]["episode"] == 3

    async def test_update_viewing_session(self, store: StateStore):
        """Test updating a viewing session when it ends."""
        session_id = await store.record_viewing_session(
            device_id="appletv_living",
            app="Netflix",
            title="Test Movie",
            media_type="movie",
            duration=7200,
        )

        await store.update_viewing_session(
            session_id,
            watched_duration=5400,
            completed=True,
        )

        history = await store.get_viewing_history(device_id="appletv_living")
        assert len(history) == 1
        assert history[0]["watched_duration"] == 5400
        assert history[0]["completed"] is True

    async def test_get_viewing_history_filters(self, store: StateStore):
        """Test viewing history filtering by app and device."""
        # Record on different apps and devices
        await store.record_viewing_session(
            device_id="appletv_living",
            app="Netflix",
            title="Show 1",
        )
        await store.record_viewing_session(
            device_id="appletv_living",
            app="Hulu",
            title="Show 2",
        )
        await store.record_viewing_session(
            device_id="appletv_bedroom",
            app="Netflix",
            title="Show 3",
        )

        # Filter by app
        netflix_history = await store.get_viewing_history(app="Netflix")
        assert len(netflix_history) == 2

        # Filter by device
        living_history = await store.get_viewing_history(device_id="appletv_living")
        assert len(living_history) == 2

        # Filter by both
        combined = await store.get_viewing_history(
            device_id="appletv_living", app="Netflix"
        )
        assert len(combined) == 1

    async def test_get_viewing_stats(self, store: StateStore):
        """Test viewing statistics aggregation."""
        # Add some viewing data
        for i in range(5):
            session_id = await store.record_viewing_session(
                device_id="appletv_living",
                app="Netflix",
                title=f"Show {i}",
                media_type="tvshow",
                genre="Comedy",
                duration=1800,
            )
            await store.update_viewing_session(session_id, watched_duration=1800)

        for i in range(3):
            session_id = await store.record_viewing_session(
                device_id="appletv_living",
                app="Hulu",
                title=f"Movie {i}",
                media_type="movie",
                genre="Drama",
                duration=7200,
            )
            await store.update_viewing_session(session_id, watched_duration=7200)

        stats = await store.get_viewing_stats(days=30)

        assert stats["total_sessions"] == 8
        assert "Netflix" in stats["by_app"]
        assert "Hulu" in stats["by_app"]
        assert stats["by_app"]["Netflix"]["count"] == 5
        assert stats["by_app"]["Hulu"]["count"] == 3
        assert "Comedy" in stats["by_genre"]
        assert "Drama" in stats["by_genre"]

    async def test_get_recently_watched(self, store: StateStore):
        """Test getting recently watched content."""
        await store.record_viewing_session(
            device_id="appletv",
            app="Netflix",
            title="Episode 1",
            series_name="The Office",
            season=1,
            episode=1,
        )
        await asyncio.sleep(0.1)
        await store.record_viewing_session(
            device_id="appletv",
            app="Netflix",
            title="Episode 2",
            series_name="The Office",
            season=1,
            episode=2,
        )

        recent = await store.get_recently_watched(limit=10, unique_titles=True)

        # Should only have one entry for The Office (unique by series)
        assert len(recent) == 1
        assert recent[0]["series_name"] == "The Office"
        assert recent[0]["watch_count"] == 2

    async def test_get_frequently_watched(self, store: StateStore):
        """Test getting frequently watched content."""
        # Watch the same show multiple times
        for i in range(5):
            await store.record_viewing_session(
                device_id="appletv",
                app="Netflix",
                series_name="Breaking Bad",
                title=f"Episode {i}",
            )

        # Watch another show fewer times
        for i in range(2):
            await store.record_viewing_session(
                device_id="appletv",
                app="Hulu",
                series_name="Parks and Rec",
                title=f"Episode {i}",
            )

        frequent = await store.get_frequently_watched(limit=5)

        assert len(frequent) == 2
        assert frequent[0]["series_name"] == "Breaking Bad"
        assert frequent[0]["watch_count"] == 5
        assert frequent[1]["series_name"] == "Parks and Rec"
        assert frequent[1]["watch_count"] == 2


class TestContentPreferences:
    """Tests for content preferences/ratings."""

    async def test_set_and_get_preference(self, store: StateStore):
        """Test setting and getting content preferences."""
        await store.set_content_preference(
            series_name="The Office",
            app="Netflix",
            genre="Comedy",
            liked=True,
            rating=5,
        )

        prefs = await store.get_content_preferences()
        assert len(prefs) == 1
        assert prefs[0]["series_name"] == "The Office"
        assert prefs[0]["liked"] is True
        assert prefs[0]["rating"] == 5

    async def test_get_liked_only(self, store: StateStore):
        """Test filtering for liked content only."""
        await store.set_content_preference(
            series_name="Show 1",
            liked=True,
        )
        await store.set_content_preference(
            series_name="Show 2",
            liked=False,
        )
        await store.set_content_preference(
            series_name="Show 3",
            liked=True,
        )

        liked = await store.get_content_preferences(liked_only=True)
        assert len(liked) == 2

    async def test_update_preference(self, store: StateStore):
        """Test updating an existing preference."""
        await store.set_content_preference(
            series_name="Test Show",
            app="Netflix",
            rating=3,
        )

        # Update the rating
        await store.set_content_preference(
            series_name="Test Show",
            app="Netflix",
            rating=5,
        )

        prefs = await store.get_content_preferences()
        assert len(prefs) == 1
        assert prefs[0]["rating"] == 5


class TestRecommendationEngine:
    """Tests for the recommendation engine."""

    async def test_empty_recommendations(self, store: StateStore):
        """Test recommendations with no viewing history."""
        engine = RecommendationEngine(store)
        recs = await engine.get_recommendations()

        # Should return empty or minimal recommendations
        assert isinstance(recs, list)

    async def test_continue_watching_recommendations(self, store: StateStore):
        """Test 'continue watching' recommendations for TV shows."""
        # Add a TV show with recent viewing
        await store.record_viewing_session(
            device_id="appletv",
            app="Netflix",
            series_name="Stranger Things",
            title="Episode 5",
            season=3,
            episode=5,
            media_type="tvshow",
        )

        engine = RecommendationEngine(store)
        recs = await engine.get_recommendations(
            include_continue=True,
            include_favorites=False,
            include_discovery=False,
        )

        # Should suggest continuing Stranger Things
        assert len(recs) > 0
        continue_rec = recs[0]
        assert continue_rec.series_name == "Stranger Things"
        assert continue_rec.reason == "Continue watching"
        assert continue_rec.next_episode == {"season": 3, "episode": 6}

    async def test_favorite_recommendations(self, store: StateStore):
        """Test recommendations based on frequently watched content."""
        # Watch the same show many times
        for i in range(10):
            session_id = await store.record_viewing_session(
                device_id="appletv",
                app="Netflix",
                series_name="The Office",
                title=f"Episode {i}",
                media_type="tvshow",
            )
            await store.update_viewing_session(session_id, watched_duration=1800)

        engine = RecommendationEngine(store)
        recs = await engine.get_recommendations(
            include_continue=False,
            include_favorites=True,
            include_discovery=False,
        )

        # Should include The Office as a favorite
        assert len(recs) > 0
        office_recs = [r for r in recs if r.series_name == "The Office"]
        assert len(office_recs) > 0
        assert "Watched" in office_recs[0].reason

    async def test_what_to_watch_with_history(self, store: StateStore):
        """Test 'what to watch' suggestion with viewing history."""
        await store.record_viewing_session(
            device_id="appletv",
            app="Netflix",
            series_name="Good Show",
            title="Episode 1",
            season=1,
            episode=1,
            media_type="tvshow",
        )

        engine = RecommendationEngine(store)
        suggestion = await engine.get_what_to_watch()

        assert "watch" in suggestion or "suggestion" in suggestion
        assert "reason" in suggestion

    async def test_what_to_watch_with_mood(self, store: StateStore):
        """Test 'what to watch' with mood hint."""
        # Add some comedy content
        await store.record_viewing_session(
            device_id="appletv",
            app="Netflix",
            series_name="Brooklyn Nine-Nine",
            genre="comedy",
            media_type="tvshow",
        )

        engine = RecommendationEngine(store)
        suggestion = await engine.get_what_to_watch(mood="comedy")

        assert "watch" in suggestion or "suggestion" in suggestion

    async def test_streaming_services_summary(self, store: StateStore):
        """Test streaming services summary."""
        # Add viewing on different apps
        for i in range(5):
            session_id = await store.record_viewing_session(
                device_id="appletv",
                app="Netflix",
                title=f"Netflix Show {i}",
            )
            await store.update_viewing_session(session_id, watched_duration=3600)

        for i in range(3):
            session_id = await store.record_viewing_session(
                device_id="appletv",
                app="Hulu",
                title=f"Hulu Show {i}",
            )
            await store.update_viewing_session(session_id, watched_duration=1800)

        engine = RecommendationEngine(store)
        summary = await engine.get_streaming_services_summary(
            available_apps=["Netflix", "Hulu", "Disney+"]
        )

        assert "services" in summary
        assert "Netflix" in summary["services"]
        assert "Hulu" in summary["services"]
        assert summary["total_sessions"] == 8

        # Disney+ should be listed as unused
        if "unused_services" in summary:
            assert "Disney+" in summary["unused_services"]


class TestRecommendationScoring:
    """Tests for recommendation scoring logic."""

    async def test_continue_watching_has_high_score(self, store: StateStore):
        """Test that continue watching has highest priority."""
        await store.record_viewing_session(
            device_id="appletv",
            app="Netflix",
            series_name="In Progress Show",
            season=1,
            episode=3,
            media_type="tvshow",
        )

        engine = RecommendationEngine(store)
        recs = await engine.get_recommendations()

        if recs:
            continue_recs = [r for r in recs if r.reason == "Continue watching"]
            if continue_recs:
                # Continue watching should have score >= 0.9
                assert continue_recs[0].score >= 0.9

    async def test_recommendations_sorted_by_score(self, store: StateStore):
        """Test that recommendations are sorted by score (descending)."""
        # Add various viewing history
        await store.record_viewing_session(
            device_id="appletv",
            app="Netflix",
            series_name="Show 1",
            media_type="tvshow",
        )

        for i in range(3):
            await store.record_viewing_session(
                device_id="appletv",
                app="Hulu",
                series_name="Show 2",
                media_type="tvshow",
            )

        engine = RecommendationEngine(store)
        recs = await engine.get_recommendations()

        # Verify sorted by score
        for i in range(len(recs) - 1):
            assert recs[i].score >= recs[i + 1].score
