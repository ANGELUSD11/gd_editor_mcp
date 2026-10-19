"""Test MCP client: starts the server over stdio the way an agent would.

Usage: python devtools/test_client.py                  lists tools and prompts
       python devtools/test_client.py <tool> '<json>'  calls a tool (images are saved to devtools/out/)
"""
import asyncio
import base64
import json
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

OUT = Path(__file__).resolve().parent / 'out'


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
                return
            res = await s.call_tool(sys.argv[1], json.loads(sys.argv[2]) if len(sys.argv) > 2 else {})
            for c in res.content:
                if c.type == 'text':
                    print(c.text[:4000])
                elif c.type == 'image':
                    OUT.mkdir(exist_ok=True)
                    out = OUT / ('%s.png' % sys.argv[1])
                    out.write_bytes(base64.b64decode(c.data))
                    print('image:', out)
            if res.is_error:
                print('(error)')


if __name__ == '__main__':
    asyncio.run(main())
