"""Experiment helpers + one-call runner that builds from a ``RunConfig``.

This is the function the Streamlit worker and the CLI both call: given a
:class:`~pouch_cell.config.run.RunConfig` it builds the spec, runs the
requested analysis / protocol and returns ``(sim, sol, metrics)``.
"""
from __future__ import annotations

import numpy as np
import pybamm

from ..config.design import PouchCellSpec
from ..config.protocol import Protocol
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


def _temp_metric(sol, metrics: dict) -> None:
    """Best-effort temperature metrics (variable name depends on the model)."""
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
        return


def collect_metrics(sim: PouchCellSimulation, sol, config: RunConfig) -> dict:
    """Extract the key numbers shown in the UI history / results table."""
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
    _temp_metric(sol, metrics)
    metrics["final_capacity_Ah"] = metrics["delivered_Ah"]
    return metrics


def collect_step_metrics(sol) -> list[dict]:
    """Per-step metrics for a multi-step solution (cycles -> steps).

    Each row carries the end-of-step time, voltage, discharge capacity and
    end-of-step temperature (best-effort) so the UI table shows how the
    electrochemical AND thermal state evolve step by step (the thermal state
    is inherited exactly across steps -- see the notebook verification).
    """
    rows: list[dict] = []
    cycles = getattr(sol, "cycles", None) or []
    for ci, cycle in enumerate(cycles):
        steps = getattr(cycle, "steps", None) or []
        for si, step in enumerate(steps):
            try:
                V = float(np.asarray(step["Voltage [V]"].entries)[-1])
                Ah = float(np.asarray(step["Discharge capacity [A.h]"].entries)[-1])
            except KeyError:
                V = Ah = float("nan")
            T_end = float("nan")
            for _tname in (
                "Volume-averaged cell temperature [K]",
                "X-averaged cell temperature [K]",
                "Cell temperature [K]",
            ):
                try:
                    # [..., -1] = end-of-step frame; .max() = hot spot (2+1D)
                    T_end = float(np.asarray(step[_tname].entries)[..., -1].max())
                    break
                except KeyError:
                    continue
            rows.append(
                {"cycle": ci + 1, "step": si + 1,
                 "t_end_s": float(step.t[-1]), "V_end": V, "Ah": Ah,
                 "T_end_K": T_end}
            )
    return rows


def _build_simulation(spec, config, model_name, dimensionality, thermal, mesh):
    sim = PouchCellSimulation(
        spec=spec,
        model_name=model_name,
        dimensionality=dimensionality,
        thermal=thermal,
        parameter_set=config.parameter_set,
        initial_soc=config.initial_soc,
        mesh=mesh,
        solver=make_solver(config.solver),
        output_variables=config.output_variables,
        store_first_last=config.store_first_last,
        cooling=config.cooling,
        full_stack_3d=config.full_stack_3d,
        size_to_capacity=config.size_to_capacity,
        particle=config.particle,   # "uniform profile" works with r_n=r_p=1 meshes
    )
    if config.extra_overrides:
        sim.param.update(config.extra_overrides)
    return sim


def _resolve_protocol_model(config: RunConfig, proto: Protocol) -> tuple:
    """Return ``(model_name, dimensionality, thermal, mesh)`` for a protocol.

    When per-step thermal maps are requested the protocol must run on a 2+1D
    ``x-lumped`` model (the only one with an in-plane temperature field).
    DFN/SPMe on the 2+1D mesh are DAE-limited to a few seconds
    (``IDA_ERR_FAIL``), so SPM is *always* used for thermal-map protocol runs;
    the user's model choice is honoured otherwise.
    """
    model, dim, thermal, mesh = (
        config.model_name, config.dimensionality, config.thermal, config.mesh,
    )
    if proto.thermal_maps:
        thermal = "x-lumped"
        dim = 2
        model = "SPM"  # 2+1D DFN/SPMe are DAE-limited; SPM is reliable
        if isinstance(mesh, str) and mesh.endswith("_3d"):
            mesh = "micro_21d"
    return model, dim, thermal, mesh


def run_protocol(
    config: RunConfig,
    spec: PouchCellSpec,
    proto: Protocol,
    note: str = "",
):
    """Run a multi-step :class:`Protocol` and return ``(sim, sol, metrics)``."""
    model, dim, thermal, mesh = _resolve_protocol_model(config, proto)
    sim = _build_simulation(spec, config, model, dim, thermal, mesh)
    experiment = pybamm.Experiment(
        proto.experiment_cycles(spec.capacity_Ah),
        period=proto.period,
        temperature=proto.temperature_K,
        termination=proto.termination or None,
    )
    sol = sim.run_experiment_obj(experiment)
    metrics = collect_metrics(sim, sol, config)
    # report the *actually resolved* model/dim/thermal/mesh (the protocol may
    # have forced SPM 2+1D x-lumped for thermal maps)
    metrics["model"] = model
    metrics["dimensionality"] = dim
    metrics["thermal"] = thermal
    metrics["mesh"] = mesh if isinstance(mesh, str) else str(mesh)
    metrics["analysis"] = "protocol"
    metrics["protocol_type"] = proto.type
    metrics["steps"] = collect_step_metrics(sol)
    if note:
        metrics["note"] = note
    return sim, sol, metrics


def run(config: RunConfig, spec: PouchCellSpec | None = None, verbose: bool = True):
    """Run a :class:`RunConfig` and return ``(sim, sol, metrics)``.

    Dispatch order: ``config.protocol`` (multi-step) -> ``tab`` analysis ->
    ``charge`` analysis -> plain constant-current discharge.
    """
    config.validate()
    spec = spec or config.spec()

    # --- multi-step protocol (takes precedence) --------------------------
    if config.protocol:
        proto = Protocol.from_dict(config.protocol)
        return run_protocol(config, spec, proto)

    # --- tab-driven resistive-heating analysis ----------------------------
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

    # --- simple CC -> CV charge (legacy single-run) -----------------------
    if config.analysis == "charge":
        proto = Protocol.charge_protocol(
            c_rate=config.C_rate,
            upper_cutoff_V=spec.upper_cutoff_V,
            cv_hold=bool(config.cutoff_V is None),  # CV hold unless disabled
            rest_s=None,
            thermal_maps=False,
        )
        return run_protocol(config, spec, proto)

    # --- plain constant-current discharge ---------------------------------
    sim = _build_simulation(
        spec, config, config.model_name, config.dimensionality,
        config.thermal, config.mesh,
    )
    sol = sim.discharge(
        C_rate=config.C_rate,
        duration_s=config.duration_s,
        cutoff_V=config.cutoff_V,
    )
    metrics = collect_metrics(sim, sol, config)
    return sim, sol, metrics
