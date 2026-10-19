"""Level editor operations with Python types (on top of GameBridge)."""
from PIL import Image

from ..errors import GDError
from ..levels import SPEED_PORTALS, Level, ObjectFilter, Timeline, join_objects
from .bridge import GameBridge

CHUNK = 3000   # objects per call: each call runs within one frame


class EditorClient:
    def __init__(self, bridge: GameBridge):
        self.bridge = bridge

    async def status(self) -> dict:
        return await self.bridge.call('status')

    async def add_objects(self, objects: list[str], guard: str, select: bool = True, undoable: bool = True) -> dict:
        created = 0
        for i in range(0, len(objects), CHUNK):
            part = objects[i:i + CHUNK]
            r = await self.bridge.call('add_objects', join_objects(part), select and len(objects) <= CHUNK, undoable,
                                       guard)
            created += r['created']
        return {'sent': len(objects), 'created': created}

    async def get_objects(self, flt: ObjectFilter, limit: int) -> dict:
        return await self.bridge.call('get_objects', flt.to_agent(), limit)

    async def select_objects(self, flt: ObjectFilter) -> dict:
        return await self.bridge.call('select_objects', flt.to_agent())

    async def delete_objects(self, flt: ObjectFilter | None, guard: str) -> dict:
        return await self.bridge.call('delete_objects', None if flt is None else flt.to_agent(), guard, timeout=90)

    async def read_level(self) -> Level:
        r = await self.bridge.call('level_string', timeout=90)
        return Level(header=r['header'], objects=r['objects'], name=r['level'].get('name') or 'Level')

    async def load_level(self, level: Level, guard: str, replace: bool = True) -> dict:
        return await self.bridge.call('load_level', level.header, join_objects(level.objects), replace,
                                      level.song_id or 0, guard, timeout=120)

    async def song_state(self) -> dict:
        """Level header, song ID / official track, audio file the game would play and song offset."""
        return await self.bridge.call('song_state')

    async def set_song(self, guard: str, song_id: int | None = None, track: int | None = None,
                       offset: float | None = None) -> dict:
        return await self.bridge.call('set_song', song_id, track, offset, guard)

    async def timeline(self) -> Timeline:
        """Song time <-> x mapping of the open level (start speed, song offset and speed portals)."""
        state = await self.song_state()
        portals = await self.get_objects(ObjectFilter(ids=list(SPEED_PORTALS)), 100000)
        return Timeline.from_level(state['header'], portals['objects'])

    async def playtest(self, start: bool) -> dict:
        return await self.bridge.call('playtest', start)

    async def view(self, x: float | None, y: float | None, zoom: float | None) -> dict:
        return await self.bridge.call('view', x, y, zoom)

    async def capture(self, hide_ui: bool = True) -> Image.Image:
        self.bridge.take_frame()
        await self.bridge.call('capture_frame', hide_ui)
        frame = self.bridge.take_frame()
        if frame is None:
            raise GDError('The frame image did not arrive.')
        w, h, data = frame
        return Image.frombytes('RGBA', (w, h), data).transpose(Image.FLIP_TOP_BOTTOM).convert('RGB')

    async def scene_tree(self, depth: int, max_children: int) -> dict:
        return await self.bridge.call('scene_tree', depth, max_children)
