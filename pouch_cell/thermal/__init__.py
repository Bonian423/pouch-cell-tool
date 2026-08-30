"""Thermal subpackage -- cooling presets and heat-pipe localization.

* :func:`~pouch_cell.thermal.cooling.resolve_cooling` normalises the
  ``cooling=`` option (preset name or dict of parameter overrides).
* :func:`~pouch_cell.thermal.heat_pipe.heat_pipe_overrides` builds the
  space-varying ambient / edge-coefficient parameters that model a heat pipe
  on the top edge.

Both are applied to the parameter values inside
:class:`~pouch_cell.core.simulation.PouchCellSimulation`.
"""
from .cooling import resolve_cooling
from .heat_pipe import heat_pipe_overrides

__all__ = ["resolve_cooling", "heat_pipe_overrides"]
