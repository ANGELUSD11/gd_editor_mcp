"""Connection with the Geometry Dash process: find it, inject the agent and talk to the editor."""
from .bridge import GameBridge
from .editor import EditorClient
from .process import GameProcess, find_game_process

__all__ = ['EditorClient', 'GameBridge', 'GameProcess', 'find_game_process']
