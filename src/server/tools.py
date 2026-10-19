"""MCP tools. They only translate arguments and errors; the logic lives in session, game, levels and music."""
import asyncio
import functools
import io
from pathlib import Path
from typing import TYPE_CHECKING

from mcp.server.mcpserver import Context, Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from ..errors import GDError, LevelChanged
from ..levels import SPEED_PORTALS, Level, ObjectFilter, Timeline, read_gmd, shift_object, split_objects, write_gmd
from ..music import analyze_file, get_song, list_songs
from ..physics import World, check_clicks, check_layout

MAX_CONVERSIONS = 2000
MAX_CLICKS = 500
MAX_LEVEL_OBJECTS = 200000
LAYOUT_MARGIN = 60.0         # objects just outside the checked area, so its edges are judged in context

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

    # ------------------------------------------------------------ gameplay and layout checks
    @tool
    async def gd_check_jumps(clicks: list[float] | None = None, beats: list[float] | None = None,
                             bpm: float | None = None, first_beat: float | None = None, x_start: float = 0.0,
                             x_end: float | None = None, y_start: float = 0.0, objects: str | None = None,
                             include_level: bool = True, start_speed: str | None = None,
                             robustness: bool = True) -> dict:
        """Simulates the cube through the level with the planned clicks and checks that it gets through.

        clicks: x positions of the player's center when clicking; or beats with bpm/first_beat (song beats, as in
        gd_beat_to_x). The level's objects between x_start and x_end are read from the editor; objects adds planned
        objects that are not built yet (include_level=False checks them alone), so a section can be checked before
        building it. y_start is the height of the cube's bottom at x_start (0 = on the ground). start_speed
        ('0.5x'...'4x', default '1x') is the speed at x=0 when include_level=False; otherwise the level's is used.
        Returns the run (survived/died/stopped, where and why, wasted clicks), where the cube dies without clicking,
        and, if it survives, the timing window (how early/late every click can be, in ms) and the failures with a
        random error per click. Cube mode only (normal size and gravity): yellow pads, yellow orbs and speed portals
        are simulated; other portals, pads, orbs and slopes stop the simulation. Margins under ~20 ms are risky.
        """
        planned = split_objects(objects) if objects else []
        if include_level:
            state = await editor.song_state()
            portals = (await editor.get_objects(ObjectFilter(ids=list(SPEED_PORTALS)), 100000))['objects']
            timeline = Timeline.from_level(state['header'], portals + planned)
        else:
            codes = {'1x': 0, '0.5x': 1, '2x': 2, '3x': 3, '4x': 4}
            if (start_speed or '1x') not in codes:
                raise ToolError('start_speed must be one of %s.' % ', '.join(codes))
            timeline = Timeline.from_level('kA4,%d' % codes[start_speed or '1x'], planned)

        xs = list(clicks or [])
        if beats:
            if bpm is None or first_beat is None:
                raise ToolError('Converting beats needs bpm and first_beat (from gd_analyze_song).')
            xs += [timeline.song_time_to_x(first_beat + b * 60.0 / bpm)['x'] for b in beats]
        xs = sorted(x for x in xs if x >= x_start)
        if len(xs) > MAX_CLICKS:
            raise ToolError('At most %d clicks per check.' % MAX_CLICKS)
        if x_end is None:
            x_end = (xs[-1] if xs else x_start) + 600.0
        if x_end <= x_start:
            raise ToolError('x_end must be greater than x_start.')

        level_objects = []
        if include_level:
            flt = ObjectFilter(x_min=x_start - 200, x_max=x_end + 200)
            level_objects = (await editor.get_objects(flt, MAX_LEVEL_OBJECTS))['objects']
        world = World.from_objects(level_objects + planned)
        t0 = timeline.time_at(x_start)
        speed = timeline.x_at(t0)[1]
        times = [timeline.time_at(x) - t0 for x in xs]
        report = await asyncio.to_thread(check_clicks, world, times, x_start, x_end, y_start, speed, robustness)
        return {'clicks_x': [round(x, 1) for x in xs], 'x_start': x_start, 'x_end': round(x_end, 1),
                'start_speed': speed, 'collision_objects': len(world.bodies), **report}

    @tool
    async def gd_check_layout(objects: str | None = None, include_level: bool = True, x_min: float | None = None,
                              x_max: float | None = None, max_problems: int = 40) -> dict:
        """Checks how the layout looks (not how it plays) and lists the placement mistakes.

        Errors: spikes partly inside blocks. Warnings: spikes flush in a 1-block pit (their tips are level with the
        floor, so they look embedded between blocks), thin gaps and overlaps between blocks, duplicated objects and
        spikes sunk into the ground. It also counts blocks and spikes off the 30-unit grid.
        objects: planned objects not built yet, to check them before gd_add_objects; include_level also reads the
        level's objects from the editor (only between x_min and x_max if given). Only visible blocks, slopes and
        full-size spikes are checked. Fix every error and warning before moving on: `fixes` says how.
        """
        planned = split_objects(objects) if objects else []
        if not include_level and not planned:
            raise ToolError('Give objects, or include_level=True to check the level.')
        level_objects = []
        if include_level:
            flt = ObjectFilter(x_min=None if x_min is None else x_min - LAYOUT_MARGIN,
                               x_max=None if x_max is None else x_max + LAYOUT_MARGIN)
            level_objects = (await editor.get_objects(flt, MAX_LEVEL_OBJECTS))['objects']
        return await asyncio.to_thread(check_layout, level_objects + planned, max_problems, x_min, x_max)

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
