"""Music: the songs Geometry Dash can play on this PC and the analysis of their beat and structure."""
from .analysis import SongAnalysis, analyze_audio, analyze_file
from .library import Song, get_song, list_songs, song_file

__all__ = ['Song', 'SongAnalysis', 'analyze_audio', 'analyze_file', 'get_song', 'list_songs', 'song_file']
