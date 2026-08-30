"""Legacy re-export shim (keeps ``pouch_cell.model`` import paths working).

The implementation now lives in :mod:`pouch_cell.core.model`.
"""
from .core.model import (  # noqa: F401
    MODEL_NAMES,
    _check_thermal,
    build_geometry_3d_stack,
    build_model,
)

__all__ = ["MODEL_NAMES", "build_model", "build_geometry_3d_stack"]
