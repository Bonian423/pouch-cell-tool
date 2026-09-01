"""Backwards-compatible shim -- the heat pipe is now the "top-edge band"
cooling-geometry preset in :mod:`pouch_cell.thermal.cooling_geometry`.

Imports are re-exported so existing code (``simulation.py`` shims, notebooks,
CLI) keeps working unchanged.
"""
from __future__ import annotations

from .cooling_geometry import (  # noqa: F401
    _heat_pipe_overrides,
    heat_pipe_overrides,
    preset_regions,
    region_overrides,
)
