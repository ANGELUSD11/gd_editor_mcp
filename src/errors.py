"""Expected errors. Their messages are meant to be relayed by the agent to the user."""
import re


class GDError(Exception):
    code = 'GD_ERROR'


class PrerequisiteError(GDError):
    code = 'PREREQUISITE'


class GameNotRunning(GDError):
    code = 'GAME_NOT_RUNNING'


class UnsupportedVersion(GDError):
    code = 'UNSUPPORTED'


class NotInEditor(GDError):
    code = 'NOT_IN_EDITOR'


class EmptyLevel(GDError):
    code = 'EMPTY_LEVEL'


class NotArmed(GDError):
    code = 'NOT_ARMED'


class LevelChanged(GDError):
    code = 'LEVEL_CHANGED'


class GameTimeout(GDError):
    code = 'TIMEOUT'


class ConnectionLost(GDError):
    code = 'CONNECTION_LOST'


_BY_CODE = {cls.code: cls for cls in (UnsupportedVersion, NotInEditor, EmptyLevel, NotArmed, LevelChanged)}
_AGENT_MSG = re.compile(r'\[([A-Z_]+)\]\s*(.*)')


def from_agent_message(message: str) -> GDError:
    """Turns an in-game agent error ("Error: [NOT_IN_EDITOR] text") into the matching typed exception."""
    first = message.split('\n')[0]
    m = _AGENT_MSG.search(first)
    if m:
        return _BY_CODE.get(m.group(1), GDError)(m.group(2))
    return GDError('Error inside the game: %s' % first)
