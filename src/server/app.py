"""MCP server assembly."""
import logging
from dataclasses import dataclass

from mcp.server.mcpserver import MCPServer

from .. import SERVER_NAME, __version__
from ..game import EditorClient, GameBridge
from ..session import Session
from .prompts import register_prompts
from .tools import register_tools

INSTRUCTIONS = """\
Controls, live, the Geometry Dash level editor open on the user's PC.
Always reply to the user in their own language.

Required workflow:
1. Call gd_check_ready before anything else. It checks that the game is open, on a supported version, with an
   EMPTY level in the editor. If it fails, tell the user what to do (next_step field) and call it again.
   Tools that modify the level do not work until it passes.
2. Build section by section with gd_add_objects (or load a complete level with gd_load_level).
3. Review what you built with gd_view + gd_screenshot and fix it with gd_get_objects / gd_delete_objects.

Music sync: find the song with gd_list_songs, set it (and the offset where the level starts) with gd_set_song,
get its beat grid and sections with gd_analyze_song, place the speed portals, then turn beats into x positions
with gd_beat_to_x and build the gameplay on those positions (drops are good places for mode or speed changes).

Object format (GD level string): "1,<id>,2,<x>,3,<y>,<key>,<value>,..." separated by ";".
1 block = 30 units; the center of the first row above the ground is y=15. Useful keys: 6 rotation,
21 color channel, 24 Z layer, 25 Z order, 57 groups ("1.2"), 128/129 X/Y scale.
Basic IDs: 1 block, 8 spike, 35 yellow pad, 36 yellow orb, 12 cube portal, 13 ship portal,
201/202/203 speed 1x/2x/3x, 899 color trigger, 901 move trigger.
"""


@dataclass
class AppContext:
    bridge: GameBridge
    editor: EditorClient
    session: Session


def create_server() -> MCPServer:
    bridge = GameBridge()
    editor = EditorClient(bridge)
    app = AppContext(bridge, editor, Session(bridge, editor))
    mcp = MCPServer(SERVER_NAME, instructions=INSTRUCTIONS, version=__version__)
    register_tools(mcp, app)
    register_prompts(mcp)
    return mcp


def run() -> None:
    logging.basicConfig(level=logging.INFO, format='[gd-editor] %(message)s')   # stderr: stdout carries the protocol
    create_server().run()
