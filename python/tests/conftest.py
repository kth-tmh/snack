"""pytest configuration for snack Python tests.

Sets up the test environment so that snack.interop can be loaded
without the compiled C extension, enabling unit tests of the pure-Python
conversion logic via MockSound objects.
"""

import sys
import os
import types
import importlib.util

# Ensure test helpers are importable as a regular module.
sys.path.insert(0, os.path.dirname(__file__))

# -----------------------------------------------------------------------
# Bootstrap a minimal "snack" package in sys.modules so that relative
# imports inside interop.py (e.g. `from . import Sound`) resolve correctly
# even when the compiled _snack extension is absent.
# -----------------------------------------------------------------------

if "snack" not in sys.modules:
    # Create a lightweight stub for the snack package.  Individual tests
    # that call from_numpy / from_librosa / from_tensor will temporarily
    # replace the `Sound` attribute with a MockSound factory.
    _stub = types.ModuleType("snack")
    _stub.Sound = None
    sys.modules["snack"] = _stub

# Load interop.py as "snack.interop" so its relative imports work.
_INTEROP_PATH = os.path.join(
    os.path.dirname(__file__), "..", "snack", "interop.py"
)
_spec = importlib.util.spec_from_file_location("snack.interop", _INTEROP_PATH)
interop = importlib.util.module_from_spec(_spec)
interop.__package__ = "snack"
sys.modules["snack.interop"] = interop
_spec.loader.exec_module(interop)
