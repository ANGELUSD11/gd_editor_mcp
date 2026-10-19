"""Prerequisite checks, shared by the gd_check_ready tool and by `gd-editor-mcp doctor`.

1. An MCP agent (Claude Code or another one) is using this server.
2. The server is registered in that agent.
3. Geometry Dash is open, on a supported version, with an empty level in the editor.
"""
import asyncio
from dataclasses import asdict, dataclass

from .errors import GDError
from .game import EditorClient, GameBridge, find_game_process
from .install import Registration
from .versions import find_table, supported_versions


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ''
    fix: str = ''

    def as_dict(self) -> dict:
        return asdict(self)


def agent_connected_check(client_name: str | None) -> Check:
    if client_name:
        return Check('Agent connected', True, 'This server is being used by %s.' % client_name)
    return Check('Agent connected', True, 'Server started by an MCP client.')


def agent_installed_check(claude_path: str | None) -> Check:
    if claude_path:
        return Check('Agent installed', True, 'Claude Code: %s' % claude_path)
    return Check('Agent installed', False, 'Claude Code (the `claude` command) was not found.',
                 'Install Claude Code, or with another agent run `gd-editor-mcp config` and paste the configuration.')


def registration_check(reg: Registration | None) -> Check:
    if reg is None:
        return Check('Registered as MCP server', False, 'The agent could not be queried.')
    if not reg.registered:
        return Check('Registered as MCP server', False, 'gd-editor is not registered in Claude Code.',
                     'Run `gd-editor-mcp install`.')
    if reg.connected:
        return Check('Registered as MCP server', True, 'Status: %s (scope: %s)' % (reg.status, reg.scope))
    if 'Pending' in reg.status:
        return Check('Registered as MCP server', False, 'Registered but pending approval (%s).' % reg.scope,
                     'Open `claude` in that folder and approve gd-editor, or register it for all your projects with '
                     '`gd-editor-mcp install`.')
    return Check('Registered as MCP server', False, 'Registered but not connecting: %s' % reg.status,
                 'Register it again with `gd-editor-mcp install`; if it keeps failing, run '
                 '`gd-editor-mcp serve --force` in a terminal to see the error.')


async def game_checks(bridge: GameBridge, editor: EditorClient, require_empty: bool = True) -> tuple[list[Check], dict | None]:
    """Prerequisite 3. Returns the checks and, if it reaches the editor, the editor status."""
    checks: list[Check] = []
    proc = await asyncio.to_thread(find_game_process)
    if proc is None:
        checks.append(Check('Game open', False, 'GeometryDash.exe is not running.', 'Open Geometry Dash.'))
        return checks, None
    checks.append(Check('Game open', True, 'PID %d' % proc.pid))

    table = find_table(proc.sha256)
    if table is None:
        checks.append(Check('Supported version', False, 'Unknown executable (sha256 %s...).' % (proc.sha256 or '?')[:16],
                            'Supported versions: %s. See docs/REVERSING.md.' % ', '.join(supported_versions())))
        return checks, None
    checks.append(Check('Supported version', True, 'Geometry Dash %s' % table.label))

    try:
        await bridge.connect()
        status = await editor.status()
    except GDError as e:
        checks.append(Check('Connection with the game', False, str(e)))
        return checks, None
    checks.append(Check('Connection with the game', True, 'Agent injected and addresses verified.'))

    if not status.get('in_editor'):
        checks.append(Check('Editor open', False, 'The game is not in the level editor.',
                            'Go to Create, make a new level and enter the editor.'))
        return checks, status
    level = status.get('level') or {}
    checks.append(Check('Editor open', True, 'Level: %s' % (level.get('name') or '?')))

    n = status.get('objects', 0)
    if n == 0:
        checks.append(Check('Empty level', True, 'The level has no objects.'))
    elif require_empty:
        checks.append(Check('Empty level', False, 'The open level already has %d objects.' % n,
                            'Open a new empty level so your work is not touched (or ask to continue this level).'))
    else:
        checks.append(Check('Empty level', True, 'It has %d objects: continuing this level as the user asked.' % n))
    return checks, status


def format_checklist(checks: list[Check]) -> str:
    lines = []
    for c in checks:
        lines.append('[%s] %s: %s' % ('OK' if c.ok else 'X ', c.name, c.detail))
        if not c.ok and c.fix:
            lines.append('      -> %s' % c.fix)
    return '\n'.join(lines)
