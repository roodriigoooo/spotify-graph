"""Put the engine package on sys.path for the unit tests.

The shared code now lives in the Lambda layer at `layers/common/common/` (importable as the
`common` package; the engine is `common.taste`). Adding that dir lets the engine tests do
`import taste` / `from taste import ...` directly.
"""
import os
import sys

_LAYER_PKG = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "layers", "common", "common")
)
if _LAYER_PKG not in sys.path:
    sys.path.insert(0, _LAYER_PKG)
