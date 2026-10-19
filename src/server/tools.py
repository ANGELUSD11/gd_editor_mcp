"""MCP tools. They only translate arguments and errors; the logic lives in session, game, levels and music."""
import asyncio
import functools
import io
from pathlib import Path
from typing import TYPE_CHECKING

from mcp.server.mcpserver import Context, Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from ..errors import GDError, LevelChanged
from ..levels import Level, ObjectFilter, read_gmd, shift_object, split_objects, write_gmd
from ..music import analyze_file, get_song, list_songs

MAX_CONVERSIONS = 2000

if TYPE_CHECKING:
    from .app import AppContext


def _client_name(ctx: Context) -> str | None:
    try:
        info = ctx.session.client_params.client_info
        return ('%s %s' % (info.name, info.version or '')).strip()
    except AttributeError:
        return None


def register_tools(mcp: MCPServer, app: 'AppContext') -> None:
    session, editor = app.session, app.editor

    def tool(fn):
        """Registers the tool, turning expected errors into messages for the agent."""
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except LevelChanged as e:
                session.disarm()
                raise ToolError('%s Run gd_check_ready again.' % e) from None
            except (GDError, ValueError, OSError) as e:
                raise ToolError(str(e)) from None
        return mcp.tool()(wrapper)

    # ------------------------------------------------------------ prerequisites and status
    @tool
    async def gd_check_ready(ctx: Context, continue_existing: bool = False) -> dict:
        """Validates the prerequisites and enables editing: game open, supported version and an EMPTY level in the editor.

        Call it at the start and whenever a tool says the level has not been validated.
        continue_existing=True accepts a level that already has objects: use it ONLY if the user explicitly asks
        to keep working on the level they have open.
        """
        return await session.check_ready(_client_name(ctx), continue_existing)

    @tool
    async def gd_status() -> dict:
        """Current state: scene, open level, object count, selection and whether editing is enabled."""
        st = await editor.status()
        st['editing_enabled'] = session.armed is not None
        return st

    # ------------------------------------------------------------ build
    @tool
    async def gd_add_objects(objects: str, select: bool = True, undoable: bool = True, dx: float = 0.0,
                             dy: float = 0.0) -> dict:
        """Creates objects in the level from their object string ("1,1,2,15,3,15;1,8,2,45,3,15").

        select: leaves the new objects selected. undoable: they can be undone with Ctrl+Z.
        dx/dy: offset added to every position.
        """
        objs = [shift_object(o, dx, dy) for o in split_objects(objects)]
        return await editor.add_objects(objs, session.guard(), select, undoable)

    @tool
    async def gd_delete_objects(x_min: float | None = None, x_max: float | None = None, y_min: float | None = None,
                                y_max: float | None = None, ids: list[int] | None = None,
                                delete_all: bool = False) -> dict:
        """Deletes objects by area and/or IDs (undoable with Ctrl+Z). Without filters it requires delete_all=True."""
        flt = ObjectFilter(x_min, x_max, y_min, y_max, ids)
        if flt.is_empty() and not delete_all:
            raise ToolError('Give an area or IDs, or delete_all=True to empty the level.')
        return await editor.delete_objects(None if delete_all else flt, session.guard())

    @tool
    async def gd_load_level(gmd_path: str | None = None, level_string: str | None = None, song_id: int | None = None,
                            replace: bool = True) -> dict:
        """Loads a COMPLETE level with its header (colors, background, ground, song offset...).

        Pass gmd_path (a .gmd file) or level_string ("kS38,...;1,1,2,15,3,15;..."). song_id: Newgrounds ID
        (defaults to the one in the .gmd). replace=True deletes the current objects first. Loaded objects cannot
        be undone with Ctrl+Z.
        """
        if gmd_path:
            level = read_gmd(gmd_path)
        elif level_string:
            level = Level.from_level_string(level_string)
        else:
            raise ToolError('Give gmd_path or level_string.')
        if song_id:
            level.song_id = song_id
        return await editor.load_level(level, session.guard(), replace)

    @tool
    async def gd_import_gmd(path: str, dx: float = 0.0, dy: float = 0.0) -> dict:
        """Pastes the objects of a .gmd file into the level, without its header (to combine pieces of levels)."""
        level = read_gmd(path)
        objs = [shift_object(o, dx, dy) for o in level.objects]
        return await editor.add_objects(objs, session.guard(), select=False)

    # ------------------------------------------------------------ read and select
    @tool
    async def gd_get_objects(x_min: float | None = None, x_max: float | None = None, y_min: float | None = None,
                             y_max: float | None = None, ids: list[int] | None = None, limit: int = 200) -> dict:
        """Reads level objects (full object strings, triggers included), filtered by area and/or IDs."""
        return await editor.get_objects(ObjectFilter(x_min, x_max, y_min, y_max, ids), limit)

    @tool
    async def gd_select_objects(x_min: float | None = None, x_max: float | None = None, y_min: float | None = None,
                                y_max: float | None = None, ids: list[int] | None = None) -> dict:
        """Selects the filtered objects in the editor, so the user can see or edit them."""
        return await editor.select_objects(ObjectFilter(x_min, x_max, y_min, y_max, ids))

    @tool
    async def gd_export_level(path: str | None = None) -> dict:
        """Saves the open level as a .gmd file (default: <level name>.gmd in the current folder)."""
        level = await editor.read_level()
        out = write_gmd(Path(path) if path else Path.cwd() / ('%s.gmd' % level.name), level)
        return {'path': str(out.resolve()), 'objects': len(level.objects)}

    # ------------------------------------------------------------ music
    @tool
    async def gd_list_songs(query: str | None = None, limit: int = 30) -> dict:
        """Lists the songs downloaded on this PC (Newgrounds and music library), with name and artist when known.

        Use it to find the ID of a song the user mentions (query matches name, artist or ID). Only downloaded
        songs can be analyzed.
        """
        songs = await asyncio.to_thread(list_songs, query, limit)
        return {'count': len(songs), 'songs': [s.as_dict() for s in songs]}

    @tool
    async def gd_set_song(song_id: int | None = None, official_track: int | None = None,
                          offset: float | None = None) -> dict:
        """Sets the level's song and/or song offset, keeping the objects.

        song_id: Newgrounds or music library song ID. official_track: official song index (0 = Stereo Madness...).
        offset: song time in seconds at which the level starts (the player is at x=0 then).
        Reports whether the audio file is downloaded on this PC.
        """
        if song_id is not None and official_track is not None:
            raise ToolError('Give song_id or official_track, not both.')
        if song_id is None and official_track is None and offset is None:
            raise ToolError('Give song_id, official_track or offset.')
        if offset is not None and offset < 0:
            raise ToolError('The offset cannot be negative.')
        state = await editor.set_song(session.guard(), song_id, official_track, offset)
        state.pop('header', None)
        if state.get('song_id'):
            song = await asyncio.to_thread(get_song, state['song_id'])
            state['song'] = song.as_dict()
            if not song.downloaded:
                state['warning'] = ("The song is not downloaded on this PC: download it from the level's song menu "
                                    'in GD to hear it and analyze it.')
        return state

    @tool
    async def gd_analyze_song(song_id: int | None = None, path: str | None = None) -> dict:
        """Analyzes a song's beat and structure. Without arguments, it analyzes the open level's song.

        Returns bpm, the beat grid (beat n is at song time first_beat + n * beat_period), the first bar start,
        sections (intro/build/drop/break/steady/outro with their relative energy), drops and short cuts (near
        silences). Times are in song seconds. It is signal analysis and assumes a steady tempo: if a half or
        double tempo in `alternatives` fits the song better, use it. grid_fit below ~1.3 means a weak beat.
        """
        if path:
            file, song = Path(path), None
        else:
            if song_id is None:
                state = await editor.song_state()
                song_id = state['song_id']
                if not song_id:
                    resources = Path(app.bridge.process.path).parent / 'Resources' if app.bridge.process else None
                    file = Path(state['audio_file'])
                    if not file.is_absolute() and resources:
                        file = resources / file
                    song = None
            if song_id:
                song = await asyncio.to_thread(get_song, song_id)
                if not song.downloaded:
                    raise ToolError('Song %d is not downloaded on this PC.' % song_id)
                file = Path(song.file)
        if not file.exists():
            raise ToolError('Audio file not found: %s' % file)
        analysis = await asyncio.to_thread(analyze_file, file)
        return {'song': song.as_dict() if song else {'file': str(file)}, **analysis.as_dict()}

    @tool
    async def gd_beat_to_x(beats: list[float] | None = None, song_times: list[float] | None = None,
                           bpm: float | None = None, first_beat: float | None = None) -> dict:
        """Converts song beats or song times (s) into level x positions for the open level.

        It uses the level's song offset, start speed and speed portals, so place speed portals before
        converting. beats needs bpm and first_beat (from gd_analyze_song). The returned x is where the player's
        center is at that moment: put an object's center there, or start a jump there.
        """
        times = list(song_times or [])
        if beats:
            if bpm is None or first_beat is None:
                raise ToolError('Converting beats needs bpm and first_beat (from gd_analyze_song).')
            times += [first_beat + b * 60.0 / bpm for b in beats]
        if not times:
            raise ToolError('Give beats or song_times.')
        if len(times) > MAX_CONVERSIONS:
            raise ToolError('At most %d conversions per call.' % MAX_CONVERSIONS)
        timeline = await editor.timeline()
        rows = [timeline.song_time_to_x(t) for t in times]
        for row, b in zip(rows[len(song_times or []):], beats or []):
            row['beat'] = b
        return {'song_offset': timeline.song_offset, 'speed_changes': [vars(s) for s in timeline.segments],
                'positions': rows}

    # ------------------------------------------------------------ view and test
    @tool
    async def gd_view(x: float | None = None, y: float | None = None, zoom: float | None = None) -> dict:
        """Centers the editor camera on (x, y), in level units, and optionally changes the zoom."""
        return await editor.view(x, y, zoom)

    @tool
    async def gd_screenshot(max_width: int = 1100, hide_ui: bool = True) -> Image:
        """Captures the frame the game is showing (works if the window is covered, not if it is minimized).

        hide_ui: hides the editor buttons in the captured frame only.
        """
        im = await editor.capture(hide_ui)
        if im.width > max_width:
            im = im.resize((max_width, round(im.height * max_width / im.width)))
        buf = io.BytesIO()
        im.save(buf, 'PNG')
        return Image(data=buf.getvalue(), format='png')

    @tool
    async def gd_playtest(start: bool = True) -> dict:
        """Starts (start=True) or stops (start=False) the editor playtest."""
        return await editor.playtest(start)

    @tool
    async def gd_debug_tree(depth: int = 2, max_children: int = 12) -> dict:
        """Node tree of the current scene (classes and positions). Only for diagnosing problems."""
        return await editor.scene_tree(depth, max_children)
