"""Songs Geometry Dash can play on this PC: downloaded audio files and their names (from the game's save file)."""
import base64
import gzip
import html
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

AUDIO_EXTS = ('.mp3', '.ogg')
# Song entries in CCGameManager.dat: <d><k>kCEK</k><i>6</i><k>1</k><i>ID</i><k>2</k><s>NAME</s><k>4</k><s>ARTIST</s>...
_SONG_RE = re.compile(r'<d><k>kCEK</k><i>6</i><k>1</k><i>(\d+)</i><k>2</k><s>(.*?)</s><k>4</k><s>(.*?)</s>')
_metadata_cache: dict[tuple, dict[int, tuple[str, str]]] = {}


@dataclass
class Song:
    song_id: int
    name: str | None = None
    artist: str | None = None
    file: str | None = None        # downloaded audio file, if any

    @property
    def downloaded(self) -> bool:
        return self.file is not None

    def as_dict(self) -> dict:
        return {**asdict(self), 'downloaded': self.downloaded}


def data_dir() -> Path:
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'GeometryDash'


def decode_save(raw: bytes) -> str:
    """Decodes a GD save file (XOR 11 -> base64 -> gzip); plain XML is returned as is."""
    if raw.lstrip().startswith(b'<?xml'):
        return raw.decode('utf-8', 'replace')
    data = (np.frombuffer(raw, dtype=np.uint8) ^ 11).tobytes().rstrip(b'\x00')
    return gzip.decompress(base64.urlsafe_b64decode(data + b'=' * (-len(data) % 4))).decode('utf-8', 'replace')


def song_metadata(folder: Path | None = None) -> dict[int, tuple[str, str]]:
    """{song_id: (name, artist)} for every song the game knows about (cached until the save file changes)."""
    path = (folder or data_dir()) / 'CCGameManager.dat'
    if not path.exists():
        return {}
    st = path.stat()
    key = (str(path), st.st_size, st.st_mtime_ns)
    if key not in _metadata_cache:
        xml = decode_save(path.read_bytes())
        _metadata_cache.clear()
        _metadata_cache[key] = {int(i): (html.unescape(n), html.unescape(a)) for i, n, a in _SONG_RE.findall(xml)}
    return _metadata_cache[key]


def song_file(song_id: int, folder: Path | None = None) -> Path | None:
    folder = folder or data_dir()
    for ext in AUDIO_EXTS:
        p = folder / ('%d%s' % (song_id, ext))
        if p.exists():
            return p
    return None


def get_song(song_id: int, folder: Path | None = None) -> Song:
    name, artist = song_metadata(folder).get(song_id, (None, None))
    f = song_file(song_id, folder)
    return Song(song_id, name, artist, str(f) if f else None)


def list_songs(query: str | None = None, limit: int = 30, folder: Path | None = None) -> list[Song]:
    """Downloaded songs, optionally filtered by text in their name, artist or ID."""
    folder = folder or data_dir()
    meta = song_metadata(folder)
    songs = []
    for p in folder.iterdir() if folder.exists() else []:
        if p.suffix.lower() in AUDIO_EXTS and p.stem.isdigit():
            sid = int(p.stem)
            name, artist = meta.get(sid, (None, None))
            songs.append(Song(sid, name, artist, str(p)))
    if query:
        q = query.lower()
        songs = [s for s in songs if q in ('%s %s %d' % (s.name or '', s.artist or '', s.song_id)).lower()]
    songs.sort(key=lambda s: (s.name is None, (s.name or '').lower(), s.song_id))
    return songs[:limit]
