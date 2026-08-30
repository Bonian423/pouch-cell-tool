"""pouch_cell -- a 3D PyBaMM modelling tool for an NCM811/graphite pouch cell.

Modular layout
--------------
- :mod:`pouch_cell.config` -- single source of truth for every knob
  (:class:`PouchCellSpec`, :class:`RunConfig`, :class:`ThermalConfig`, presets).
- :mod:`pouch_cell.core` -- pure PyBaMM engine (model / parameters / sizing /
  simulation / experiment / sweep / analysis).
- :mod:`pouch_cell.thermal` -- cooling presets + heat-pipe localization.
- :mod:`pouch_cell.registry` -- pluggable option registries.
- :mod:`pouch_cell.cli` -- ``python -m pouch_cell``.
- :mod:`pouch_cell.ui` -- Streamlit UI (``python -m pouch_cell --ui``).

Legacy module paths (``pouch_cell.cell_spec``, ``pouch_cell.simulation``, ...)
remain as thin re-export shims so the notebook keeps working unchanged.
"""
from .config import PouchCellSpec, RunConfig, ThermalConfig
from .config import io as config_io
from .core.model import MODEL_NAMES, build_geometry_3d_stack, build_model
from .core.parameters import AVAILABLE_SETS, build_parameter_values
from .core.sizing import size_electrodes_to_capacity
from .core.simulation import PouchCellSimulation
from . import plotting, registry

__all__ = [
    "PouchCellSpec",
    "RunConfig",
    "ThermalConfig",
    "build_model",
    "build_geometry_3d_stack",
    "build_parameter_values",
    "size_electrodes_to_capacity",
    "PouchCellSimulation",
    "plotting",
    "registry",
    "config_io",
    "MODEL_NAMES",
    "AVAILABLE_SETS",
]
__version__ = "0.2.0"
