"""Registers the server in the user agent (Claude Code) and provides the config for other MCP clients."""
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

from . import SERVER_NAME
from .errors import PrerequisiteError

SCOPES = ('user', 'project', 'local')


@dataclass
class Registration:
    registered: bool
    connected: bool
    status: str
    scope: str | None = None


def server_command() -> list[str]:
    """Command the agent runs to start the server (the Python interpreter where this package is installed)."""
    return [sys.executable, '-m', 'gd_editor_mcp', 'serve']


def client_config() -> dict:
    """The "mcpServers" block for any MCP client configured through JSON."""
    cmd = server_command()
    return {'mcpServers': {SERVER_NAME: {'command': cmd[0], 'args': cmd[1:]}}}


def find_claude() -> str | None:
    return shutil.which('claude')


def _run(args: list[str], timeout: float = 120) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)


def parse_mcp_get(returncode: int, output: str) -> Registration:
    """Parses the output of `claude mcp get <name>`."""
    if returncode != 0:
        return Registration(False, False, 'not registered')
    status = re.search(r'Status:\s*(.+)', output)
    scope = re.search(r'Scope:\s*(.+)', output)
    status_text = status.group(1).strip() if status else 'unknown'
    return Registration(True, 'Connected' in status_text, status_text, scope.group(1).strip() if scope else None)


def require_claude() -> str:
    claude = find_claude()
    if claude is None:
        raise PrerequisiteError('Claude Code (the `claude` command) was not found. Install it from '
                                'https://claude.com/claude-code or, for another MCP agent, run `gd-editor-mcp config` '
                                'and paste the configuration.')
    return claude


def claude_registration() -> Registration:
    r = _run([require_claude(), 'mcp', 'get', SERVER_NAME])
    return parse_mcp_get(r.returncode, r.stdout + r.stderr)


def install_claude_code(scope: str = 'user') -> Registration:
    claude = require_claude()
    _run([claude, 'mcp', 'remove', SERVER_NAME, '-s', scope])
    r = _run([claude, 'mcp', 'add', '-s', scope, SERVER_NAME, '--', *server_command()])
    if r.returncode != 0:
        raise PrerequisiteError('Claude Code rejected the registration: %s' % (r.stderr or r.stdout).strip())
    return claude_registration()


def uninstall_claude_code(scope: str = 'user') -> bool:
    return _run([require_claude(), 'mcp', 'remove', SERVER_NAME, '-s', scope]).returncode == 0


def config_json() -> str:
    return json.dumps(client_config(), indent=2)
