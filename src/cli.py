"""Command line: gd-editor-mcp [serve | install | uninstall | doctor | config]."""
import argparse
import asyncio
import sys

from . import SERVER_NAME, __version__
from .errors import GDError

NOT_FROM_TERMINAL = """\
gd-editor-mcp is an MCP server: you do not run it directly, your agent (Claude Code or another one) starts it.

  gd-editor-mcp install   registers the server in Claude Code
  gd-editor-mcp doctor    checks the prerequisites (agent, registration, game in an empty editor)
  gd-editor-mcp config    prints the configuration for other MCP agents
"""


def cmd_serve(args) -> int:
    if sys.stdin.isatty() and not args.force:
        print(NOT_FROM_TERMINAL, file=sys.stderr)
        return 2
    from .server import run
    run()
    return 0


def cmd_install(args) -> int:
    from .checks import format_checklist, registration_check
    from .install import install_claude_code
    try:
        reg = install_claude_code(args.scope)
    except GDError as e:
        print('Installation failed: %s' % e)
        return 1
    print('Registered "%s" in Claude Code (scope: %s).' % (SERVER_NAME, args.scope))
    print(format_checklist([registration_check(reg)]))
    print('\nNext step: open Geometry Dash, enter the editor with an empty level and ask your agent to check the '
          'editor (or use the /gd-editor:new_level command).')
    return 0 if reg.registered else 1


def cmd_uninstall(args) -> int:
    from .install import uninstall_claude_code
    try:
        removed = uninstall_claude_code(args.scope)
    except GDError as e:
        print(e)
        return 1
    print('Removed from Claude Code.' if removed else 'It was not registered in the "%s" scope.' % args.scope)
    return 0


def cmd_config(args) -> int:
    from .install import config_json
    print(config_json())
    return 0


def cmd_doctor(args) -> int:
    from .checks import Check, agent_installed_check, format_checklist, game_checks, registration_check
    from .game import EditorClient, GameBridge
    from .install import claude_registration, find_claude

    claude = find_claude()
    checks = [agent_installed_check(claude)]
    if claude:
        checks.append(registration_check(claude_registration()))
    else:
        checks.append(Check('Registered as MCP server', False, 'It cannot be checked without Claude Code.',
                            'With another agent, paste the output of `gd-editor-mcp config` into its MCP configuration.'))
    if not args.skip_game:
        bridge = GameBridge()
        try:
            game, _ = asyncio.run(game_checks(bridge, EditorClient(bridge)))
        finally:
            bridge.close()
        checks += game
    print(format_checklist(checks))
    ok = all(c.ok for c in checks)
    print('\nAll set.' if ok else '\nSome prerequisites are missing (see above).')
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='gd-editor-mcp', description='Live Geometry Dash editor for MCP agents.')
    parser.add_argument('--version', action='version', version=__version__)
    sub = parser.add_subparsers(dest='command')
    p = sub.add_parser('serve', help='starts the MCP server over stdio (used by the agent)')
    p.add_argument('--force', action='store_true', help='start even when run from a terminal')
    p.set_defaults(func=cmd_serve)
    for name, func, text in (('install', cmd_install, 'registers the server in Claude Code'),
                             ('uninstall', cmd_uninstall, 'removes the server from Claude Code')):
        p = sub.add_parser(name, help=text)
        p.add_argument('--scope', choices=('user', 'project', 'local'), default='user')
        p.set_defaults(func=func)
    p = sub.add_parser('doctor', help='checks the prerequisites')
    p.add_argument('--skip-game', action='store_true', help='skip the game checks')
    p.set_defaults(func=cmd_doctor)
    sub.add_parser('config', help='JSON configuration for other MCP agents').set_defaults(func=cmd_config)

    args = parser.parse_args(argv)
    if args.command is None:
        if sys.stdin.isatty():
            print(NOT_FROM_TERMINAL)
            return 0
        args = parser.parse_args(['serve'])
    if args.command != 'serve' and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(errors='replace')
    return args.func(args)
