"""Tab-driven resistive-heating analysis (2+1D, ``x-lumped`` thermal).

The two tabs draw current from the surrounding current collector,
concentrating the current density and its Ohmic (resistive) heating around
each tab.  This module builds a 2+1D model, runs a short discharge and returns
the tab-heating figure together with the simulation and solution.
"""
from __future__ import annotations

from ..config.design import PouchCellSpec
from .simulation import PouchCellSimulation


def tab_heating_analysis(
    cls=None,
    spec: PouchCellSpec | None = None,
    C_rate: float = 1.0,
    duration_s: float = 5,
    mesh: str | dict = "micro_21d",
    particle: str = "uniform profile",
    model_name: str = "DFN",
    cooling: str | dict | None = None,
    size_to_capacity: bool = False,
    **kwargs,
):
    """Run a 2+1D discharge and analyse tab-driven resistive heating.

    ``cls`` is the simulation class to use (default
    :class:`PouchCellSimulation`); the classmethod on
    :class:`PouchCellSimulation` delegates here so the API is unchanged.

    ``cooling`` controls the thermal dissipation (preset name or dict) --
    see :func:`pouch_cell.thermal.cooling.resolve_cooling`.

    Runtime notes (PyBaMM 26.8):

    * The DAE solver choice barely matters; the mesh and duration are the
      levers.  The 2+1D DAE models complete for 1-5 s but hit
      ``SolverError: IDA_ERR_FAIL`` beyond ~5-10 s of 1C discharge.
    * To see more than a few seconds of tab heating, keep ``duration_s``
      short (the current-concentration is a transient visible within the
      first seconds) or switch to ``model_name="SPM"`` (fast, ~1 s per 60 s;
      temperature magnitudes inflated but hot-spot locations correct).

    Returns
    -------
    (sim, sol, fig)
        The simulation, its solution and the matplotlib figure.
    """
    from .. import plotting

    cls = cls or PouchCellSimulation
    sim = cls(
        spec=spec,
        model_name=model_name,
        dimensionality=2,
        thermal="x-lumped",
        mesh=mesh,
        particle=particle,
        size_to_capacity=size_to_capacity,
        cooling=cooling,
        **kwargs,
    )
    sol = sim.discharge(C_rate=C_rate, duration_s=duration_s)
    fig = plotting.plot_tab_heating(sol, sim.spec, param=sim.param)
    return sim, sol, fig
