"""Working session: which level was validated with gd_check_ready and can therefore be modified."""
from dataclasses import dataclass

from .checks import agent_connected_check, game_checks
from .errors import NotArmed
from .game import EditorClient, GameBridge


@dataclass
class ArmedLevel:
    id: str
    name: str | None


class Session:
    """Tools that modify the level require a validated level (empty when validated) that is still open.

    The in-game agent re-checks the level id on every operation, so if the user switches levels or closes the
    game, the session is invalidated and the level must be validated again.
    """

    def __init__(self, bridge: GameBridge, editor: EditorClient):
        self.bridge = bridge
        self.editor = editor
        self.armed: ArmedLevel | None = None
        bridge.on_disconnect(lambda _reason: self.disarm())

    async def check_ready(self, client_name: str | None = None, continue_existing: bool = False) -> dict:
        checks = [agent_connected_check(client_name)]
        game, status = await game_checks(self.bridge, self.editor, require_empty=not continue_existing)
        checks += game
        ready = all(c.ok for c in checks)
        level = (status or {}).get('level') or {}
        self.armed = ArmedLevel(level['id'], level.get('name')) if ready and level.get('id') else None
        failed = next((c for c in checks if not c.ok), None)
        return {
            'ready': self.armed is not None,
            'level': level.get('name'),
            'checks': [c.as_dict() for c in checks],
            'next_step': 'Ready: you can build in the level now.' if self.armed else
                         'Ask the user to: %s' % (failed.fix or failed.detail if failed else 'check the game'),
        }

    def guard(self) -> str:
        if self.armed is None:
            raise NotArmed('The editor must be validated with gd_check_ready before modifying the level '
                           '(game open and an empty level in the editor).')
        return self.armed.id

    def disarm(self) -> None:
        self.armed = None
