"""Runs the unit tests: python tests/run.py [unittest options]

Importing the package first keeps the test modules out of the bytecode cache (see src/__init__.py), so the project
keeps a single __pycache__ folder.
"""
import sys
import unittest
from pathlib import Path

import gd_editor_mcp  # noqa: F401  (configures bytecode caching before the tests are imported)

HERE = Path(__file__).resolve().parent
result = unittest.main(module=None, argv=[sys.argv[0], 'discover', '-s', str(HERE), '-t', str(HERE)] + sys.argv[1:],
                       exit=False)
sys.exit(not result.result.wasSuccessful())
