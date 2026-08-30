"""Core engine -- pure PyBaMM (no UI / CLI coupling).

* :mod:`~pouch_cell.core.model` -- build PyBaMM models.
* :mod:`~pouch_cell.core.parameters` -- build parameter values.
* :mod:`~pouch_cell.core.sizing` -- auto-size electrodes to a target capacity.
* :mod:`~pouch_cell.core.simulation` -- :class:`PouchCellSimulation` (run).
* :mod:`~pouch_cell.core.experiment` -- experiment helpers / one-call run.
* :mod:`~pouch_cell.core.sweep` -- parallel C-rate sweeps.
* :mod:`~pouch_cell.core.analysis` -- tab-driven resistive-heating analysis.
"""
