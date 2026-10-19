# gd-editor-mcp

An MCP server that lets your AI agent (Claude Code or any other MCP-compatible agent) **build Geometry Dash levels
live**, inside the game's editor: create and delete objects, load complete levels with their colors and song,
move the camera, take screenshots and run playtests. You type in your agent's chat and watch the level being
built in the game.

It does not need Geode: it attaches to the game process with [Frida](https://frida.re) and calls the editor's own
functions.

## Prerequisites

| | Prerequisite | How it is checked |
|---|---|---|
| 1 | An MCP agent up and running (for example [Claude Code](https://claude.com/claude-code)) | `gd-editor-mcp doctor` |
| 2 | The server registered in that agent | `gd-editor-mcp install` registers it and verifies that it connects |
| 3 | Geometry Dash open in the **editor, with an empty level** | the `gd_check_ready` tool (the agent runs it before touching anything) |

You also need Windows, Python 3.12 or newer and a supported Geometry Dash version (currently **2.2091**).

## Installation

```
git clone <repository-url> gd_editor_mcp
cd gd_editor_mcp
pip install -r requirements.txt   # exact, tested versions of every dependency
pip install --no-deps .           # or, with the newest compatible versions: pip install .   /   uv tool install .
gd-editor-mcp install             # registers the server in Claude Code (for all your projects)
gd-editor-mcp doctor              # checks the 3 prerequisites
```

`requirements.txt` pins every dependency (direct and transitive) to the latest version on PyPI at the time it was
generated, with platform markers so the same file works on Windows and Linux. To refresh it:
`uv pip compile pyproject.toml --universal --python-version 3.12 -o requirements.txt`.

Using another agent? `gd-editor-mcp config` prints the `mcpServers` block to paste into its configuration.
To remove it from Claude Code: `gd-editor-mcp uninstall`.

## Usage

1. Open Geometry Dash, go to *Create*, create a new level and enter the editor.
2. In your agent's chat, ask for anything or use one of the server's commands:
   - `/gd-editor:new_level` with an idea, for example *"easy cube and ship level, night-time pixel art style"*.
   - `/gd-editor:review_level` to review the open level and suggest improvements without changing it.
   - `/gd-editor:load_gmd` to load a complete `.gmd` file.

The first thing the agent does is validate the editor. If something is missing (the game is closed, the level
already has objects...), it tells you what to do and changes nothing until it is fixed.

## Tools

| Tool | What it does |
|---|---|
| `gd_check_ready` | Validates the prerequisites and enables editing of the open level |
| `gd_status` | Scene, level, object count, selection |
| `gd_add_objects` | Creates objects from their object string (undoable with Ctrl+Z) |
| `gd_delete_objects` | Deletes objects by area or by IDs (undoable with Ctrl+Z) |
| `gd_load_level` | Loads a complete level: header (colors, background, ground, song offset), objects and song |
| `gd_import_gmd` | Pastes the objects of a `.gmd` file without its header |
| `gd_get_objects` / `gd_select_objects` | Reads or selects objects by area or by IDs |
| `gd_export_level` | Saves the open level as a `.gmd` file |
| `gd_list_songs` | Lists the songs downloaded on this PC, with name and artist |
| `gd_set_song` | Sets the level's song (Newgrounds or official) and song offset, keeping the objects |
| `gd_analyze_song` | BPM, beat grid, bars, sections, drops and cuts of a song |
| `gd_beat_to_x` | Converts song beats or times into level x positions (song offset, start speed, speed portals) |
| `gd_check_jumps` | Simulates the cube with planned clicks: does it get through, where it dies, timing margin |
| `gd_view` / `gd_screenshot` | Moves the editor camera and captures the game's actual frame |
| `gd_playtest` | Starts or stops the playtest |
| `gd_debug_tree` | Diagnostics: the scene's node tree |

## Jump check

`gd_check_jumps` runs the cube's physics over the level (or over planned objects that are not built yet) with the
clicks the agent intends to make, given as x positions or as song beats. It reports whether the cube gets through,
where and why it dies, where it would die without clicking, and how early or late every click can be. The physics
were checked against the Pixel Sphere sample level (`tests/data`).

It covers cube mode with normal size and gravity: blocks, spikes, saws, yellow pads, yellow orbs and speed portals.
Other portals, pads, orbs and slopes stop the simulation with a message instead of giving a wrong answer, and moving
objects are simulated at their editor positions. Hitboxes come from `src/physics/hitboxes.json`, built with
`devtools/build_hitboxes.py`.

## Music sync

Ask for a song and the agent can fit the gameplay to it:

1. `gd_list_songs` finds the song among the ones downloaded on this PC, and `gd_set_song` sets it with an offset.
2. `gd_analyze_song` decodes the audio and finds the tempo, the beat grid, the bars, the sections (intro, build,
   drop, break, outro), the drops and the short cuts before them.
3. `gd_beat_to_x` turns beats into x positions, taking the level's speed and speed portals into account, so jumps,
   orbs, portals and effects land on the beat.

What it cannot do: listen (it judges energy and onsets, not melody or feel), follow songs whose tempo changes,
download songs, or play the level to check the timing. Songs must already be downloaded in GD.

## Docker

The image runs the test suite and the tools that do not touch the game: song listing and analysis, and `.gmd` files.
**The live editor tools do not work in a container**: they attach to `GeometryDash.exe` running natively on Windows,
and a container cannot see the host's processes. To build levels in the game, use the native installation above.

```
docker build -t gd-editor-mcp .
docker run --rm gd-editor-mcp python tests/run.py
docker run --rm -i -v "%LOCALAPPDATA%\GeometryDash:/data/GeometryDash:ro" -e LOCALAPPDATA=/data gd-editor-mcp
```

The last command starts the MCP server over stdio with your downloaded songs mounted read-only, so an agent can
use `gd_list_songs` and `gd_analyze_song` from the container.

## Safety

- **It only edits the validated level.** `gd_check_ready` requires an empty level and remembers its identity.
  Every operation that modifies the level checks it again inside the game: if you switch levels or close the game,
  editing is locked until the level is validated again. To keep working on a level that already has objects, ask
  the agent explicitly.
- **It only runs on verified versions.** Before calling anything, the in-game agent compares the bytes of every
  game function with its version table. If Geometry Dash updates, it refuses to act instead of risking a crash.

## Project structure

```
src/                   the gd_editor_mcp package (pyproject.toml maps the import name to this folder)
  cli.py               serve | install | uninstall | doctor | config
  install.py           registration in Claude Code and config for other agents          (prerequisites 1 and 2)
  checks.py            prerequisite checks, shared by `doctor` and gd_check_ready
  session.py           validated level and lock on the tools that modify it             (prerequisite 3)
  errors.py            expected errors, with user-facing messages
  server/              MCP layer: app (server), tools, prompts (chat commands)
  game/                connection with the game
    process.py         finds GeometryDash.exe and identifies its version
    bridge.py          injects the agent with Frida and calls its API
    editor.py          typed editor operations
    agent/             code that runs inside the game (JavaScript, split into modules)
  versions/            address tables per GD version (JSON)
  levels/              level format: level strings, .gmd files and song time <-> x (pure logic)
  music/               downloaded songs and beat/structure analysis (pure logic)
  physics/             cube simulator and object hitboxes (pure logic)
tests/                 unit tests (python tests/run.py); tests/data holds a sample level
devtools/              reverse engineering and debugging (see docs/REVERSING.md)
```

## Development

A source checkout keeps a single bytecode folder, `src/__pycache__`: `src/__init__.py` turns off bytecode
writing for the rest of the project, which is compiled in memory.

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt -e .[dev]
.venv\Scripts\python tests\run.py
.venv\Scripts\python devtools\test_client.py                  # lists tools and prompts
.venv\Scripts\python devtools\test_client.py gd_check_ready   # calls a tool the way an agent would
```

To support a new Geometry Dash version, follow [docs/REVERSING.md](docs/REVERSING.md).

## Limitations

- Windows (64-bit) only, and only versions with a table in `versions/`.
- Objects loaded with `gd_load_level` cannot be undone with Ctrl+Z (the preceding deletion can).
- Screenshots need the game window not to be minimized (it may be covered by other windows).
- The editor dims objects on editor layers other than the current one: that is normal GD behavior.
