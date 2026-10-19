import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from gd_editor_mcp.game.bridge import agent_source
from gd_editor_mcp.versions import find_table, load_tables


class VersionTablesTest(unittest.TestCase):
    def test_tables_are_complete(self):
        tables = load_tables()
        self.assertTrue(tables)
        for t in tables:
            d = t.data
            for name, f in d['functions'].items():
                self.assertRegex(f['rva'], r'^0x[0-9a-f]+$', name)
                self.assertRegex(f['bytes'], r'^([0-9a-f]{2})+$', name)
            self.assertIn('GameObject::getSaveString', d['functions'])
            self.assertIn('GameObject', d['vtables'])

    def test_tables_cover_every_function_the_agent_uses(self):
        used = set(re.findall(r"^\s*\w+: \['([^']+)', '", agent_source(), re.M))   # SIGNATURES table
        offsets = set(re.findall(r"offset\('([^']+)'\)", agent_source()))
        for t in load_tables():
            self.assertGreater(len(used), 10)
            self.assertFalse(used - set(t.data['functions']), t.label)
            self.assertFalse(offsets - set(t.data['offsets']), t.label)

    def test_find_table_by_hash_prefix(self):
        t = load_tables()[0]
        self.assertEqual(find_table(t.exe_sha256 + '0' * 48).label, t.label)
        self.assertIsNone(find_table('ff' * 32))
        self.assertIsNone(find_table(None))


class AgentBundleTest(unittest.TestCase):
    def test_bundle_order_and_exports(self):
        src = agent_source()
        self.assertLess(src.index('const C = {'), src.index('const SIGNATURES'))
        self.assertLess(src.index('function onMain'), src.index('rpc.exports'))
        self.assertNotIn('eval(', src)   # the eval hook only exists in devtools

    def test_bundle_is_valid_javascript(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('node is not available')
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'agent.js'
            f.write_text(agent_source(), encoding='utf-8')
            r = subprocess.run([node, '--check', str(f)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == '__main__':
    unittest.main()
