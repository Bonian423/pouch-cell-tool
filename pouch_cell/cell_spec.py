"""Legacy re-export shim (keeps ``pouch_cell.cell_spec`` import paths working).

The implementation now lives in :mod:`pouch_cell.config.design`.
"""
from .config.design import (  # noqa: F401
    ALUMINIUM,
    COPPER,
    FARADAY,
    NEGATIVE_ELECTRODE,
    POSITIVE_ELECTRODE,
    SEPARATOR,
    PouchCellSpec,
)

__all__ = [
    "PouchCellSpec",
    "COPPER",
    "ALUMINIUM",
    "NEGATIVE_ELECTRODE",
    "POSITIVE_ELECTRODE",
    "SEPARATOR",
    "FARADAY",
]
