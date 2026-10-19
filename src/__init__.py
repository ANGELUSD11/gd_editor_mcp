"""gd-editor-mcp: live control of the Geometry Dash editor from an MCP agent (Claude Code, etc.)."""
import sys
from pathlib import Path

__version__ = '0.2.0'
SERVER_NAME = 'gd-editor'

# In a source checkout, keep a single bytecode folder (src/__pycache__, which only holds this __init__) instead of
# one __pycache__ per subfolder: the rest of the checkout is compiled in memory. Dependencies keep the bytecode pip
# compiled for them, and installed copies of this package are left alone.
if (Path(__file__).resolve().parent.parent / 'pyproject.toml').exists():
    sys.dont_write_bytecode = True
