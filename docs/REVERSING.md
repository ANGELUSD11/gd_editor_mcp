# Supporting a new Geometry Dash version

The server only calls game functions whose addresses are listed in a table in `src/versions/`.
Each table is selected by the SHA-256 of `GeometryDash.exe`, and the in-game agent verifies it by comparing the
first bytes of every function before using it. When GD updates, `gd_check_ready` and `gd-editor-mcp doctor`
report an unknown executable and the game is left untouched.

## Steps

The tools need the `dev` extra (`pip install -e .[dev]`, for capstone). No external disassembler is required.

1. **Candidate addresses and annotation data.** Generate the data for the new version:
   ```
   python devtools/build_data.py --version <version>     # [--exe PATH] [--bindings PATH_OR_URL]
   ```
   It downloads `bindings/<version>/GeometryDash.bro` from [geode-sdk/bindings](https://github.com/geode-sdk/bindings)
   (the `win 0x...` addresses are RVAs relative to the executable's base) and writes `devtools/data/iat_<version>.json`
   (the executable's import slots) and `devtools/data/names_<version>.json` (binding names by address).
2. **Check that they are function starts.** `build_data.py` reports how many binding addresses look like function
   starts (a `.pdata` entry, or an aligned leaf function after padding) and lists the ones that fall inside another
   function. A low percentage means the bindings do not match the executable.
3. **Check that they are the right function.** Freshly published bindings contain mistakes. Disassemble each one
   and look at what it calls:
   ```
   python devtools/disasm.py 0x1c7590 80     # annotates cocos2d imports and binding names
   python devtools/xref.py 0x1c8500          # who calls a function
   ```
   Both default to the Steam install path; use `--exe` (or the `GD_EXE` variable) for another copy, and
   `disasm.py --version` to pick the annotation data when the executable has no table yet.
4. **Create the table** `src/versions/<version>-win.json` by copying the previous one: `exe_sha256` (16-character
   prefix), the `rva` and `bytes` (first 6 bytes) of every function, the `GameObject` vtable with the
   `getSaveString` slot, and the field offsets.
5. **Test it live** on an empty level: `gd-editor-mcp doctor`, then `devtools/test_client.py` with
   `gd_check_ready`, `gd_add_objects`, `gd_screenshot`, `gd_load_level`... and `devtools/dev.py "<js>"` to inspect
   things inside the game.

`tests/test_versions_and_agent.py` checks that every table contains all the functions and offsets the agent uses.

## Findings for version 2.2091

| Item | Details |
|---|---|
| `EditorUI::selectObjects` | It is `0x1c7590`. The bindings say `0x1c8500`, which is the `canSelect(obj)` filter: it takes a single object and compares its ID, groups and colors with the selection filter. Found by noticing that `selectObject` (`0x1c7490`) calls the filter and then jumps to `0x1c7590` with a `CCArray` |
| `EditorUI::updateZoom(float)` | `0x1b4c00`, unknown in the bindings; called by `scrollWheel` |
| `EditorUI::moveGamelayer(CCPoint)` | The `CCPoint` is passed by pointer: it has a copy constructor, so the MSVC x64 ABI passes it by reference |
| `LevelEditorLayer::createObjectsFromSetup(std::string&)` | `0x3ef940`, missing from the bindings. Only `LevelEditorLayer::init` calls it; it parses the header and the objects |
| `LevelEditorLayer::levelSettingsUpdated` | Belongs to the `LevelSettingsDelegate` interface: it must be called with `this = LEL + 0x3938` |
| `LevelEditorLayer::create` | The bindings label its constructor as `PlayerObject::PlayerObject` |
| Fields | `LevelEditorLayer::m_level` at `+0x878` and `m_levelSettings` at `+0xdc8`; `GJGameLevel::m_audioTrack` at `+0x2a4` and `m_songID` at `+0x2a8` |
| Coordinates | Object nodes are offset by +90 on Y relative to level coordinates |
| Strings | MSVC x64 `std::string`. When the game may free the buffer, it is allocated with the game's own `operator new` (`0x677540`), using the 32-byte alignment MSVC applies to blocks of 4 KB or more |
