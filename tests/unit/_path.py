"""Put the pure-Python engine package (src/common) on sys.path for the unit tests."""
import os
import sys

_ENGINE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "src", "common")
)
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)
