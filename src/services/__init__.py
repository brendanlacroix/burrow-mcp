"""External service clients for Burrow MCP.

Services are external APIs that are not physical devices in the home.
"""

from services.ptp import PTPClient
from services.synology import SynologyClient
from services.torrent_selector import TorrentSelector, QualityPreferences
from services.movie_query import MovieQueryInterpreter

__all__ = [
    "PTPClient",
    "SynologyClient",
    "TorrentSelector",
    "QualityPreferences",
    "MovieQueryInterpreter",
]
