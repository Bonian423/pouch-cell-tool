"""Solver factory -- map a solver name to a PyBaMM solver object.

Names come from the registry ``solver`` category and are used by the CLI and
the UI.  ``"default"`` (or ``None``) lets ``PouchCellSimulation`` pick its
default IDAKLUSolver.
"""
from __future__ import annotations

import pybamm


def make_solver(name: str | None):
    """Return a PyBaMM solver for ``name`` (``None``/``'default'`` -> model default)."""
    name = (name or "default").lower()
    if name == "default":
        return None
    if name == "idaklu":
        return pybamm.IDAKLUSolver()
    if name == "casadi-fast":
        return pybamm.CasadiSolver(mode="fast")
    if name == "casadi-safe":
        return pybamm.CasadiSolver(mode="safe")
    raise ValueError(f"unknown solver '{name}'")
