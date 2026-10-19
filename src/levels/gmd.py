"""Complete levels and .gmd files (GDShare format)."""
import base64
import gzip
import re
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

from .objects import join_objects, split_objects


@dataclass
class Level:
    header: str                       # "kS38,...,kA13,...": level colors and settings
    objects: list[str] = field(default_factory=list)
    name: str = 'Level'
    description: str = ''
    song_id: int | None = None        # Newgrounds song (not part of the level string)
    creator: str = 'Player'

    @property
    def level_string(self) -> str:
        return self.header + ';' + join_objects(self.objects)

    @classmethod
    def from_level_string(cls, level_string: str, **meta) -> 'Level':
        header, _, body = level_string.partition(';')
        if not header.startswith('kS38') and not header.startswith('kA'):
            raise ValueError('The level string must start with the header (kS38,...).')
        return cls(header=header, objects=split_objects(body), **meta)


def compress_level_string(level_string: str) -> str:
    return base64.urlsafe_b64encode(gzip.compress(level_string.encode(), 9, mtime=0)).decode()


def decompress_level_string(data: str) -> str:
    if not data.startswith('H4sI'):
        return data
    return gzip.decompress(base64.urlsafe_b64decode(data + '=' * (-len(data) % 4))).decode()


def _key(xml: str, key: str, kind: str) -> str | None:
    m = re.search(r'<k>%s</k><%s>(.*?)</%s>' % (key, kind, kind), xml, re.S)
    return m.group(1) if m else None


def read_gmd(path: str | Path) -> Level:
    xml = Path(path).read_text(encoding='utf-8')
    k4 = _key(xml, 'k4', 's')
    if k4 is None:
        raise ValueError('%s does not contain a level (k4 is missing).' % path)
    desc = _key(xml, 'k3', 's') or ''
    try:
        desc = base64.urlsafe_b64decode(desc + '=' * (-len(desc) % 4)).decode()
    except ValueError:
        pass
    song = _key(xml, 'k45', 'i')
    return Level.from_level_string(decompress_level_string(k4), name=_key(xml, 'k2', 's') or Path(path).stem,
                                   description=desc, song_id=int(song) if song else None,
                                   creator=_key(xml, 'k5', 's') or 'Player')


def write_gmd(path: str | Path, level: Level) -> Path:
    """Writes a .gmd importable with GDShare (a plist with the level keys in the root dict)."""
    parts = [
        '<k>kCEK</k><i>4</i>',
        '<k>k2</k><s>%s</s>' % escape(level.name),
        '<k>k3</k><s>%s</s>' % base64.urlsafe_b64encode(level.description.encode()).decode(),
        '<k>k4</k><s>%s</s>' % compress_level_string(level.level_string),
        '<k>k5</k><s>%s</s>' % escape(level.creator),
        '<k>k13</k><t /><k>k21</k><i>2</i><k>k16</k><i>1</i>',
        '<k>k45</k><i>%d</i>' % level.song_id if level.song_id else '',
        '<k>k50</k><i>47</i><k>k47</k><t /><k>k48</k><i>%d</i>' % len(level.objects),
    ]
    path = Path(path)
    path.write_text('<?xml version="1.0"?><plist version="1.0" gjver="2.0"><dict>%s</dict></plist>' % ''.join(parts),
                    encoding='utf-8', newline='')
    return path
