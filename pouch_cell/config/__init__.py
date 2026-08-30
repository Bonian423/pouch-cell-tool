"""Configuration layer -- the single source of truth for every knob.

* :class:`~pouch_cell.config.design.PouchCellSpec` -- the cell design
  (geometry, stack, tabs, thermal operating points, heat pipe).
* :class:`~pouch_cell.config.run.RunConfig` -- how a simulation is run
  (model, mesh, SOC, C-rate, duration, cooling, analysis...).
* :class:`~pouch_cell.config.thermal.ThermalConfig` -- thermal/cooling knobs
  for the UI (assembled into the ``cooling=`` argument).
* :mod:`~pouch_cell.config.io` -- save/load named presets as JSON.

The UI, the CLI and the notebook all read and write these same objects, so a
new knob is added in exactly one place.
"""
from .design import PouchCellSpec
from .protocol import Protocol, Step
from .run import RunConfig
from .thermal import ThermalConfig
from . import io

__all__ = ["PouchCellSpec", "RunConfig", "ThermalConfig", "Protocol", "Step", "io"]
