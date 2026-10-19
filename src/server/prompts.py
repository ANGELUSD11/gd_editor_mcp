"""MCP prompts: they show up as "/" commands in the agent's chat (in Claude Code, /gd-editor:<name>)."""
from mcp.server.mcpserver import MCPServer

NEW_LEVEL = """\
I want to create a Geometry Dash level in the editor I have open: {idea}

Do it like this:
1. Run gd_check_ready. If anything fails, tell me exactly what I have to do and wait until I have done it.
2. Briefly outline the plan (sections, game modes, speed, decoration style, song if any) and start without
   waiting for confirmation unless something essential is missing.
   If there is a song: find it with gd_list_songs, set it with gd_set_song, analyze it with gd_analyze_song,
   match the level sections to the song sections, and get every jump, orb, portal and effect position from
   gd_beat_to_x (after placing the speed portals).
3. Build section by section with gd_add_objects. After each section, center the camera with gd_view and
   check it with gd_screenshot; fix anything that does not look right.
4. When you finish, run gd_playtest and take a screenshot, then summarize what you built and how to try it.
"""

REVIEW_LEVEL = """\
Review the level I have open in the editor.

1. Run gd_check_ready with continue_existing=true (I want to keep what is there).
2. Go through the level from left to right with gd_view + gd_screenshot (and gd_get_objects when you need details).
3. Tell me the problems you see (impossible jumps, decoration covering the gameplay, empty areas, colors) and
   suggest concrete fixes. Do not change anything until I confirm.
"""

LOAD_GMD = """\
Load the level from the file {path} into the editor.

1. Run gd_check_ready.
2. Use gd_load_level with gmd_path={path}.
3. Center the camera at the start of the level, take a screenshot and tell me what was loaded (objects, song,
   colors).
"""


def register_prompts(mcp: MCPServer) -> None:
    @mcp.prompt(name='new_level', description='Create a new level in the open editor from an idea')
    def new_level(idea: str) -> str:
        return NEW_LEVEL.format(idea=idea)

    @mcp.prompt(name='review_level', description='Review the open level and suggest improvements without changing it')
    def review_level() -> str:
        return REVIEW_LEVEL

    @mcp.prompt(name='load_gmd', description='Load a complete .gmd file into the open editor')
    def load_gmd(path: str) -> str:
        return LOAD_GMD.format(path=path)
