"""Cube physics simulation over a level's objects: does a sequence of clicks get through, and with what margin."""
from .cube import CubeRun, check_clicks, simulate
from .world import World

__all__ = ['CubeRun', 'World', 'check_clicks', 'simulate']
