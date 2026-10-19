"""Test MCP client: starts the server over stdio the way an agent would.

Usage: python devtools/test_client.py                       lists tools and prompts
       python devtools/test_client.py <tool> '<json>'       calls a tool
       python devtools/test_client.py --calls calls.json    runs a list of calls in one session:
           [{"tool": "gd_check_ready", "args": {}}, ...]    (stops at the first error)
           {"sleep": 1.5} waits between calls (e.g. to take screenshots during a playtest)
Images are saved to devtools/out/.
"""
import asyncio
import base64
import json
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

OUT = Path(__file__).resolve().parent / 'out'
MAX_TEXT = 4000


async def call(session: ClientSession, tool: str, args: dict, label: str) -> bool:
    res = await session.call_tool(tool, args)
    for c in res.content:
        if c.type == 'text':
            print(c.text[:MAX_TEXT])
        elif c.type == 'image':
            OUT.mkdir(exist_ok=True)
            out = OUT / ('%s.png' % label)
            out.write_bytes(base64.b64decode(c.data))
            print('image:', out)
    if res.is_error:
        print('(error)')
    return not res.is_error


async def main() -> None:
    params = StdioServerParameters(command=sys.executable, args=['-m', 'gd_editor_mcp', 'serve'])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            if len(sys.argv) < 2:
                for t in (await s.list_tools()).tools:
                    print('tool  ', t.name, '-', (t.description or '').split('\n')[0])
                for p in (await s.list_prompts()).prompts:
                    print('prompt', p.name, '-', p.description, [a.name for a in p.arguments or []])
            elif sys.argv[1] == '--calls':
                calls = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
                for i, c in enumerate(calls):
                    if 'sleep' in c:
                        await asyncio.sleep(float(c['sleep']))
                        continue
                    print('=== [%d] %s' % (i, c['tool']))
                    if not await call(s, c['tool'], c.get('args', {}), c.get('label', '%02d_%s' % (i, c['tool']))):
                        break
            else:
                await call(s, sys.argv[1], json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}, sys.argv[1])


if __name__ == '__main__':
    asyncio.run(main())
