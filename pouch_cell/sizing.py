"""Legacy re-export shim (keeps ``pouch_cell.sizing`` import paths working).

The implementation now lives in :mod:`pouch_cell.core.sizing`.
"""
from .core.sizing import (  # noqa: F401
    _FAST_VAR_PTS,
    _delivered_capacity,
    size_electrodes_to_capacity,
)

__all__ = ["size_electrodes_to_capacity"]
