"""Experiment helpers + one-call runner that builds from a ``RunConfig``.

This is the function the Streamlit worker and the CLI both call: given a
:class:`~pouch_cell.config.run.RunConfig` it builds the spec, runs the
requested analysis and returns ``(sim, sol, metrics)``.
"""
from __future__ import annotations

from ..config.design import PouchCellSpec
from ..config.run import RunConfig
from .simulation import PouchCellSimulation
from .solvers import make_solver


def build_experiment_steps(
    C_rate: float,
    duration_s: float | None = None,
    cutoff_V: float | None = None,
    lower_cutoff_V: float = 2.5,
) -> list[str]:
    """Return the experiment step string(s) for a constant-current discharge."""
    if cutoff_V is None:
        cutoff_V = lower_cutoff_V
    if duration_s is not None:
        return [f"Discharge at {C_rate}C for {duration_s} seconds"]
    return [f"Discharge at {C_rate}C until {cutoff_V} V"]


def collect_metrics(sim: PouchCellSimulation, sol, config: RunConfig) -> dict:
    """Extract the key numbers shown in the UI history / results table."""
    import numpy as np

    V = np.asarray(sol["Voltage [V]"].entries)
    metrics: dict = {
        "model": config.model_name,
        "dimensionality": config.dimensionality,
        "thermal": config.thermal,
        "mesh": config.mesh,
        "analysis": config.analysis,
        "C_rate": config.C_rate,
        "duration_s": config.duration_s,
        "final_V": float(V[-1]),
        "delivered_Ah": float(
            np.asarray(sol["Discharge capacity [A.h]"].entries)[-1]
        ),
    }
    # temperature -- the variable name depends on the model / thermal submodel
    for name in (
        "Volume-averaged cell temperature [K]",
        "X-averaged cell temperature [K]",
        "Cell temperature [K]",
    ):
        try:
            T = np.asarray(sol[name].entries)
        except KeyError:
            continue
        metrics["Tmax_K"] = float(T.max())
        metrics["T_final_K"] = float(T[..., -1].max())
        break
    metrics["final_capacity_Ah"] = metrics["delivered_Ah"]
    return metrics


def run(config: RunConfig, spec: PouchCellSpec | None = None, verbose: bool = True):
    """Run a :class:`RunConfig` and return ``(sim, sol, metrics)``.

    ``config.analysis == "tab"`` delegates to the tab-driven resistive-heating
    analysis; otherwise a plain constant-current discharge is run.
    """
    config.validate()
    spec = spec or config.spec()

    if config.analysis == "tab":
        from .analysis import tab_heating_analysis

        sim, sol, _fig = tab_heating_analysis(
            spec=spec,
            C_rate=config.C_rate,
            duration_s=config.duration_s or 5,
            mesh=config.mesh,
            particle=config.particle,
            model_name=config.model_name,
            cooling=config.cooling,
            parameter_set=config.parameter_set,
            initial_soc=config.initial_soc,
            size_to_capacity=config.size_to_capacity,
            solver=make_solver(config.solver),
            output_variables=config.output_variables,
            store_first_last=config.store_first_last,
        )
        metrics = collect_metrics(sim, sol, config)
        metrics["analysis"] = "tab"
        return sim, sol, metrics

    sim = PouchCellSimulation(
        spec=spec,
        model_name=config.model_name,
        dimensionality=config.dimensionality,
        thermal=config.thermal,
        parameter_set=config.parameter_set,
        initial_soc=config.initial_soc,
        mesh=config.mesh,
        solver=make_solver(config.solver),
        output_variables=config.output_variables,
        store_first_last=config.store_first_last,
        cooling=config.cooling,
        full_stack_3d=config.full_stack_3d,
        size_to_capacity=config.size_to_capacity,
    )
    if config.extra_overrides:
        sim.param.update(config.extra_overrides)
    sol = sim.discharge(
        C_rate=config.C_rate,
        duration_s=config.duration_s,
        cutoff_V=config.cutoff_V,
    )
    metrics = collect_metrics(sim, sol, config)
    return sim, sol, metrics
