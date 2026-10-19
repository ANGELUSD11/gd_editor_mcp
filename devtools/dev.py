"""Development: runs JS inside the game (main thread) with the agent loaded.

Usage: python devtools/dev.py "<js code>"   (prints the value of the last expression, as JSON)
The production agent does not include this hook: it is added here as extra code.
"""
import asyncio
import sys

from gd_editor_mcp.game import GameBridge

DEV_EXPORT = 'rpc.exports.dev = function (code) { return onMain(() => JSON.stringify(eval(code))); };'


async def main(code: str) -> None:
    bridge = GameBridge(extra_source=DEV_EXPORT)
    try:
        print(await bridge.call('dev', code))
    finally:
        bridge.close()


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()))
