"""Frida bridge: injects the agent into the game and exposes its RPC methods as coroutines."""
import asyncio
import logging
import threading
from importlib import resources
from typing import Callable

import frida

from ..errors import ConnectionLost, GameNotRunning, GameTimeout, UnsupportedVersion, from_agent_message
from ..versions import VersionTable, find_table, supported_versions
from .process import GameProcess, find_game_process

log = logging.getLogger(__name__)
DEFAULT_TIMEOUT = 30.0


def agent_source() -> str:
    """The agent/ modules concatenated in order (they share the global scope of the script)."""
    folder = resources.files(__package__) / 'agent'
    files = sorted((f for f in folder.iterdir() if f.name.endswith('.js')), key=lambda f: f.name)
    return '\n'.join(f.read_text(encoding='utf-8') for f in files)


class GameBridge:
    def __init__(self, timeout: float = DEFAULT_TIMEOUT, extra_source: str = ''):
        self.timeout = timeout
        self.extra_source = extra_source          # devtools only: extra code for the agent
        self.process: GameProcess | None = None
        self.table: VersionTable | None = None
        self._lock = threading.Lock()
        self._session = None
        self._script = None
        self._frame = None
        self._on_disconnect: list[Callable[[str], None]] = []

    # ---------------------------------------------------------------- connection
    @property
    def connected(self) -> bool:
        return self._script is not None

    def on_disconnect(self, callback: Callable[[str], None]) -> None:
        self._on_disconnect.append(callback)

    def _reset(self, reason: str) -> None:
        self._session = self._script = None
        self.process = self.table = None
        for cb in self._on_disconnect:
            cb(reason)

    def _on_detached(self, reason, *_):
        log.info('disconnected from the game: %s', reason)
        self._reset(str(reason))

    def _on_message(self, msg, data):
        payload = msg.get('payload')
        if msg.get('type') == 'send' and isinstance(payload, dict) and payload.get('type') == 'frame':
            self._frame = (payload['w'], payload['h'], data)
        elif msg.get('type') == 'error':
            log.error('agent error: %s', msg.get('stack') or msg.get('description'))

    def _connect_sync(self) -> None:
        with self._lock:
            if self._script is not None:
                return
            proc = find_game_process()
            if proc is None:
                raise GameNotRunning('Geometry Dash is not open.')
            table = find_table(proc.sha256)
            if table is None:
                raise UnsupportedVersion('This Geometry Dash version is not supported (sha256 %s...). Supported: %s.'
                                         % ((proc.sha256 or '?')[:16], ', '.join(supported_versions())))
            session = frida.attach(proc.pid)
            script = session.create_script(agent_source() + '\n' + self.extra_source)
            script.on('message', self._on_message)
            script.load()
            report = script.exports_sync.init(table.data)
            if not report['ok']:
                script.unload()
                session.detach()
                raise UnsupportedVersion('The %s table does not match this executable: %s'
                                         % (table.label, report['problems'][:3]))
            session.on('detached', self._on_detached)
            self._session, self._script, self.process, self.table = session, script, proc, table
            log.info('conectado a GD %s (pid %d)', table.label, proc.pid)

    async def connect(self) -> None:
        if not self.connected:
            await asyncio.to_thread(self._connect_sync)

    def close(self) -> None:
        with self._lock:
            if self._session is not None:
                try:
                    self._session.detach()
                except frida.InvalidOperationError:
                    pass
            self._session = self._script = None

    # ---------------------------------------------------------------- calls
    def _call_sync(self, method: str, args: tuple):
        script = self._script
        if script is None:
            raise ConnectionLost('There is no connection with the game.')
        return getattr(script.exports_sync, method)(*args)

    async def call(self, method: str, *args, timeout: float | None = None):
        """Calls an agent RPC method (snake_case name) and translates its errors."""
        await self.connect()
        try:
            return await asyncio.wait_for(asyncio.to_thread(self._call_sync, method, args), timeout or self.timeout)
        except asyncio.TimeoutError:
            raise GameTimeout('The game did not answer in time (is it loading or frozen?).') from None
        except frida.core.RPCException as e:
            raise from_agent_message(str(e)) from None
        except (frida.InvalidOperationError, frida.ProcessNotFoundError, frida.TransportError) as e:
            self._reset(str(e))
            raise ConnectionLost('The connection with the game was lost: %s' % e) from None

    def take_frame(self):
        frame, self._frame = self._frame, None
        return frame
