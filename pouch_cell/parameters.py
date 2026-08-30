"""Legacy re-export shim (keeps ``pouch_cell.parameters`` import paths working).

The implementation now lives in :mod:`pouch_cell.core.parameters`.
"""
from .core.parameters import (  # noqa: F401
    AVAILABLE_SETS,
    PARAMETER_SETS,
    build_parameter_values,
)

__all__ = ["AVAILABLE_SETS", "PARAMETER_SETS", "build_parameter_values"]
