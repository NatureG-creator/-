"""Local corrosion research workbench."""
from .native_runtime import load_configured_runtime

# Run before scientific libraries are imported; errors are recorded, not raised.
load_configured_runtime()
