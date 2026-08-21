"""Pytest configuration: make the ``app`` package importable.

Tests may be run from the repo root or from ``backend/``; adding ``backend/`` to
sys.path lets ``import app...`` resolve either way.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
