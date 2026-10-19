import sys
import unittest

from gd_editor_mcp import SERVER_NAME
from gd_editor_mcp.checks import format_checklist, registration_check
from gd_editor_mcp.errors import GDError, LevelChanged, NotInEditor, from_agent_message
from gd_editor_mcp.install import client_config, parse_mcp_get, server_command

MCP_GET_OK = """gd-editor:
  Scope: User config (available in all your projects)
  Status: ✔ Connected
  Type: stdio
"""
MCP_GET_PENDING = """gd-editor:
  Scope: Project config (shared via .mcp.json)
  Status: ⏸ Pending approval (run `claude` to approve)
"""


class InstallTest(unittest.TestCase):
    def test_server_command_uses_current_interpreter(self):
        self.assertEqual(server_command(), [sys.executable, '-m', 'gd_editor_mcp', 'serve'])
        cfg = client_config()['mcpServers'][SERVER_NAME]
        self.assertEqual([cfg['command']] + cfg['args'], server_command())

    def test_parse_mcp_get(self):
        ok = parse_mcp_get(0, MCP_GET_OK)
        self.assertTrue(ok.registered and ok.connected)
        self.assertIn('User config', ok.scope)
        pending = parse_mcp_get(0, MCP_GET_PENDING)
        self.assertTrue(pending.registered)
        self.assertFalse(pending.connected)
        self.assertFalse(parse_mcp_get(1, 'No MCP server found').registered)

    def test_registration_check_messages(self):
        self.assertTrue(registration_check(parse_mcp_get(0, MCP_GET_OK)).ok)
        failing = registration_check(parse_mcp_get(1, ''))
        self.assertFalse(failing.ok)
        self.assertIn('gd-editor-mcp install', format_checklist([failing]))


class EntryPointsTest(unittest.TestCase):
    def test_cli_config_prints_server_block(self):
        import contextlib
        import io
        import json
        from gd_editor_mcp.cli import main
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(['config']), 0)
        self.assertIn(SERVER_NAME, json.loads(out.getvalue())['mcpServers'])

    def test_server_registers_tools_and_prompts(self):
        import asyncio
        from gd_editor_mcp.server import create_server

        async def listing():
            mcp = create_server()
            return [t.name for t in await mcp.list_tools()], [p.name for p in await mcp.list_prompts()]
        tools, prompts = asyncio.run(listing())
        self.assertIn('gd_check_ready', tools)
        self.assertEqual(len(tools), 17)
        self.assertEqual(sorted(prompts), ['load_gmd', 'new_level', 'review_level'])


class ErrorsTest(unittest.TestCase):
    def test_agent_codes_map_to_exceptions(self):
        e = from_agent_message('Error: [NOT_IN_EDITOR] No level is open in the editor.\n    at x')
        self.assertIsInstance(e, NotInEditor)
        self.assertEqual(str(e), 'No level is open in the editor.')
        self.assertIsInstance(from_agent_message('Error: [LEVEL_CHANGED] other'), LevelChanged)
        self.assertIs(type(from_agent_message('Error: access violation accessing 0x10')), GDError)


if __name__ == '__main__':
    unittest.main()
