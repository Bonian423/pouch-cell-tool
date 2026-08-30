"""Legacy re-export shim (keeps ``pouch_cell.simulation`` import paths working).

The implementation now lives in :mod:`pouch_cell.core.simulation`,
:mod:`pouch_cell.core.sweep` and :mod:`pouch_cell.thermal`.
"""
from .core.simulation import (  # noqa: F401
    PouchCellSimulation,
    _MESH_PRESETS,
    resolve_mesh_21d,
    resolve_mesh_3d,
)
from .core.sweep import _parallel_sweep_worker, parallel_sweep  # noqa: F401
from .thermal.cooling import (  # noqa: F401
    _COOLING_PRESETS,
    _FACE_ALIASES,
    _resolve_cooling,
    resolve_cooling,
)
from .thermal.heat_pipe import _heat_pipe_overrides, heat_pipe_overrides  # noqa: F401

__all__ = [
    "PouchCellSimulation",
    "parallel_sweep",
    "resolve_mesh_21d",
    "resolve_mesh_3d",
]
