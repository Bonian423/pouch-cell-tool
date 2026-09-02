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


def _parallel_scale(spec, dim: int) -> int:
    """The parallel-stack factor a model must be scaled by.

    PyBaMM's 0D/1D (uniform collector) models honour ``Number of electrodes
    connected in parallel to make a cell`` through ``A_cc``, so the full cell
    capacity/current is represented directly.  The 2+1D potential-pair models
    apply the cell current to a SINGLE layer (the through-plane current density
    is the total current over the footprint), so ``n_stacks`` does NOT scale the
    capacity there.  For those, the tool runs the model at the per-stack
    current and scales the extensive metrics (Ah / Wh / W / A) back up by this
    factor."""
    if spec is None or getattr(spec, "n_stacks", 1) <= 1:
        return 1
    return int(spec.n_stacks) if int(dim) >= 1 else 1


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
        metrics["T_min_K"] = float(T.min())
        return


def _time_series(sol, name: str):
    """Return a 1D time series for a solution variable (spatial mean)."""
    try:
        a = np.asarray(sol[name].entries, dtype=float)
        while a.ndim > 1:
            a = a.mean(axis=0)
        return a
    except (KeyError, TypeError, ValueError):
        return None


def _estimate_cell_mass_kg(sim, spec) -> float | None:
    """Estimate the electrochemical core mass (kg) from the layer densities.

    Uses the solved parameter values (``sim.param``) for the electrode /
    separator / collector densities times the stack geometry.  Excludes the
    pouch and packaging.  Returns ``None`` if the densities are unavailable.
    """
    try:
        param = getattr(sim, "param", None)
        if param is None or spec is None:
            return None

        def _rho(name: str) -> float:
            return float(param[name])

        area = float(spec.width) * float(spec.height)
        n = int(spec.n_stacks)
        m_active = n * (
            float(spec.L_n) * _rho("Negative electrode density [kg.m-3]")
            + float(spec.L_s) * _rho("Separator density [kg.m-3]")
            + float(spec.L_p) * _rho("Positive electrode density [kg.m-3]")
        ) * area
        m_cc = n * (
            float(spec.L_cn) * _rho("Negative current collector density [kg.m-3]")
            + float(spec.L_cp) * _rho("Positive current collector density [kg.m-3]")
        ) * area
        return m_active + m_cc
    except Exception:  # noqa: BLE001 - mass estimate is best-effort
        return None


def _electrical_metrics(sim, sol, spec, scale: int = 1) -> dict:
    """Energy / power / capacity-throughput / cycle-efficiency metrics.

    PyBaMM's convention is ``Current [A]`` positive on discharge and negative
    on charge, so ``P = V * I`` is positive while discharging and negative
    while charging.  All integrals are trapezoidal over the time series.
    ``scale`` multiplies the extensive quantities (Wh / Ah / W) -- used to
    convert the single-layer 2+1D model back to the full parallel-stack cell.
    """
    out: dict = {}
    t = _time_series(sol, "Time [s]")
    V = _time_series(sol, "Voltage [V]")
    I = _time_series(sol, "Current [A]")
    if t is None or V is None or I is None or len(t) < 2:
        return out
    dt = np.maximum(np.diff(t), 0.0)
    P = V * I
    P_mid = 0.5 * (P[:-1] + P[1:])
    I_mid = 0.5 * (I[:-1] + I[1:])
    e_disch = float(np.sum(np.maximum(P_mid, 0.0) * dt) / 3600.0)
    e_chg = float(np.sum(np.maximum(-P_mid, 0.0) * dt) / 3600.0)
    e_thru = float(np.sum(np.abs(P_mid) * dt) / 3600.0)
    q_disch = float(np.sum(np.maximum(I_mid, 0.0) * dt) / 3600.0)
    q_chg = float(np.sum(np.maximum(-I_mid, 0.0) * dt) / 3600.0)
    q_thru = float(np.sum(np.abs(I_mid) * dt) / 3600.0)
    duration = float(t[-1] - t[0])
    # convert the single-layer 2+1D model back to the full parallel-stack cell
    e_disch *= scale
    e_chg *= scale
    e_thru *= scale
    q_disch *= scale
    q_chg *= scale
    q_thru *= scale
    out.update({
        "delivered_energy_Wh": round(e_disch, 4),
        "charged_energy_Wh": round(e_chg, 4),
        "throughput_energy_Wh": round(e_thru, 4),
        "discharge_capacity_Ah": round(q_disch, 4),
        "charge_capacity_Ah": round(q_chg, 4),
        "throughput_capacity_Ah": round(q_thru, 4),
        "peak_power_W": round(float(np.max(np.abs(P))) * scale, 2),
        "initial_V": round(float(V[0]), 4),
    })
    if duration > 1e-9:
        out["average_power_W"] = round(e_thru * 3600.0 / duration, 2)
    if q_disch > 1e-9:
        out["mean_voltage_V"] = round(e_disch / q_disch, 4)
    if q_chg > 1e-9:
        out["coulombic_efficiency_pct"] = round(100.0 * q_disch / q_chg, 2)
        out["roundtrip_energy_efficiency_pct"] = round(100.0 * e_disch / e_chg, 2)
    # per-mass / per-volume figures
    if spec is not None:
        nom = float(getattr(spec, "capacity_Ah", 0.0) or 0.0)
        if nom > 0:
            out["capacity_utilisation_pct"] = round(100.0 * q_disch / nom, 2)
        mass_kg = _estimate_cell_mass_kg(sim, spec)
        if mass_kg:
            out["cell_mass_g"] = round(mass_kg * 1000.0, 1)
            out["specific_capacity_Ah_per_kg"] = round(q_disch / mass_kg, 2)
            out["specific_energy_Wh_per_kg"] = round(e_disch / mass_kg, 2)
            out["peak_power_density_W_per_kg"] = round(
                out["peak_power_W"] / mass_kg, 2)
        vol_m3 = (float(getattr(spec, "width", 0.0) or 0.0)
                  * float(getattr(spec, "height", 0.0) or 0.0)
                  * float(getattr(spec, "thickness_total", 0.0) or 0.0))
        if vol_m3 > 0:
            out["cell_volume_L"] = round(vol_m3 * 1000.0, 3)
            out["energy_density_Wh_per_L"] = round(
                e_disch / (vol_m3 * 1000.0), 2)
    return out


def collect_metrics(sim: PouchCellSimulation, sol, config: RunConfig,
                    spec=None) -> dict:
    """Extract the key numbers shown in the UI history / results table.

    Adds the electrical (energy / power / capacity-throughput / cycle
    efficiency) and specific (per-mass / per-volume) metrics when ``spec``
    (and the solution variables) are available.
    """
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
    _s = _parallel_scale(spec, int(getattr(sim, "dimensionality", 0)))
    if _s > 1:
        metrics["delivered_Ah"] *= _s
    metrics["final_capacity_Ah"] = metrics["delivered_Ah"]
    metrics.update(_electrical_metrics(sim, sol, spec, scale=_s))
    if "Tmax_K" in metrics and spec is not None:
        amb = float(getattr(spec, "ambient_temperature_K", 298.15) or 298.15)
        metrics["T_rise_K"] = round(metrics["Tmax_K"] - amb, 2)
    return metrics


def collect_step_metrics(sol, parallel_scale: int = 1) -> list[dict]:
    """Per-step metrics for a multi-step solution (cycles -> steps).

    Each row carries the end-of-step time, voltage, discharge capacity, signed
    current and end-of-step temperature (volume-averaged + hot-spot) so the UI
    table shows how the electrochemical AND thermal state evolve step by step
    (the thermal state is inherited exactly across steps) and the post-hoc
    temperature / loop-until scan can evaluate conditions at step ends.
    """
    rows: list[dict] = []
    cycles = getattr(sol, "cycles", None) or []

    def _end_scalar(step, name: str):
        try:
            return float(np.asarray(step[name].entries)[..., -1].max())
        except (KeyError, TypeError, IndexError):
            return None

    for ci, cycle in enumerate(cycles):
        steps = getattr(cycle, "steps", None) or []
        for si, step in enumerate(steps):
            row = {"cycle": ci + 1, "step": si + 1, "t_end_s": float("nan"),
                   "V_end": float("nan"), "Ah": float("nan"),
                   "I_end_A": float("nan"), "T_end_K": float("nan"),
                   "T_end_volav_K": float("nan"), "T_end_hotspot_K": float("nan"),
                   "solve_s": float("nan")}
            if isinstance(step, pybamm.EmptySolution) or step is None:
                rows.append(row)
                continue
            try:
                _st = getattr(step, "solve_time", None)
                if _st is not None:
                    # pybamm wraps solve wall-time in a TimerTime whose .value
                    # is the seconds float (float(TimerTime) raises)
                    if hasattr(_st, "value"):
                        _st = _st.value
                    row["solve_s"] = round(float(_st), 6)
            except Exception:  # noqa: BLE001
                pass
            try:
                tt = np.asarray(step.t)
                row["t_end_s"] = float(tt[-1]) if len(tt) else float("nan")
            except Exception:  # noqa: BLE001
                pass
            try:
                row["V_end"] = float(np.asarray(step["Voltage [V]"].entries)[-1])
            except Exception:  # noqa: BLE001
                pass
            try:
                row["Ah"] = float(
                    np.asarray(step["Discharge capacity [A.h]"].entries)[-1]
                )
            except Exception:  # noqa: BLE001
                pass
            # per-step energy throughput (Wh, absolute)
            try:
                _I_s = np.asarray(step["Current [A]"].entries)
                _V_s = np.asarray(step["Voltage [V]"].entries)
                if _I_s.ndim > 1:
                    _I_s = _I_s.mean(axis=0)
                if _V_s.ndim > 1:
                    _V_s = _V_s.mean(axis=0)
                _tt = np.asarray(step.t)
                _P = _V_s * _I_s
                _dtt = np.maximum(np.diff(_tt), 0.0)
                row["Wh"] = round(
                    float(np.sum(np.abs(0.5 * (_P[:-1] + _P[1:])) * _dtt)
                          / 3600.0), 4)
            except Exception:  # noqa: BLE001
                pass
            I_end = _end_scalar(step, "Current [A]")
            if I_end is not None:
                row["I_end_A"] = I_end
            T_volav = _end_scalar(step, "Volume-averaged cell temperature [K]")
            T_hot = _end_scalar(step, "X-averaged cell temperature [K]")
            if T_hot is None:
                T_hot = _end_scalar(step, "Cell temperature [K]")
            if T_volav is not None:
                row["T_end_volav_K"] = T_volav
            if T_hot is not None:
                row["T_end_hotspot_K"] = T_hot
            if T_volav is not None or T_hot is not None:
                row["T_end_K"] = T_volav if T_volav is not None else T_hot
            if parallel_scale > 1:
                for _k in ("Ah", "Wh", "I_end_A"):
                    if row.get(_k) is not None and row[_k] == row[_k]:
                        row[_k] *= parallel_scale
            rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# Post-hoc run-termination / loop-until stop evaluation.
#
# PyBaMM 26.8 has no experiment-level temperature termination (its termination
# strings support only capacity/voltage/time) and cannot branch mid-solve, so
# the run-level conditions (temperature / current limits and capacity-Ah) and
# any loop ``loop_until`` conditions are evaluated AFTER the solve by scanning
# the per-step metrics for the first condition to fire, then truncating the
# reported steps.  The solve itself always runs to completion (compute cost is
# documented in the UI).  Voltage / capacity-% / time conditions are ALSO
# mapped onto the experiment termination string so the solver stops cleanly.
# --------------------------------------------------------------------------- #
def _cond_met(c: dict, row: dict, spec: PouchCellSpec, temp_source: str) -> bool:
    """Evaluate one end-condition dict against a per-step metrics row."""
    c = dict(c or {})
    typ = c.get("type")
    op = c.get("operator", ">=")
    val = float(c.get("value", 0.0))
    unit = c.get("unit")
    if typ == "voltage":
        v = row.get("V_end")
        return v is not None and (v <= val if op == "<=" else v >= val)
    if typ == "current":
        i = abs(row.get("I_end_A") or 0.0)
        return i <= val if op == "<=" else i >= val
    if typ in ("temperature", "temp_limit"):
        kv = val + 273.15 if unit == "C" else val
        src = c.get("source") or temp_source
        t = (row.get("T_end_hotspot_K") if src == "hot_spot"
             else row.get("T_end_volav_K", row.get("T_end_hotspot_K")))
        if t is None or t != t:  # nan
            return False
        return t >= kv if op == ">=" else t <= kv
    if typ == "capacity":
        x = val if unit != "%" else val / 100.0 * spec.capacity_Ah
        ah = row.get("Ah")
        return ah is not None and (ah >= x if op == ">=" else ah <= x)
    return False


def _posthoc_stop(proto: Protocol, sol, spec: PouchCellSpec,
                  temp_source: str, parallel_scale: int = 1) -> dict | None:
    """Return ``{"reason", "cycle", "step", "index", "message"}`` for the first
    condition to fire (run-level termination conditions + every loop-until), or
    None.  ``index`` is the number of step rows to keep (exclusive end)."""
    rows = collect_step_metrics(sol, parallel_scale=parallel_scale)
    if not rows:
        return None
    candidates: list[tuple[int, str]] = []
    # run-level termination conditions (voltage/capacity/time/current/temp)
    for c in proto.termination_conditions():
        src = c.get("source") or temp_source
        for ri, row in enumerate(rows):
            if _cond_met(c, row, spec, src):
                candidates.append((ri, c.get("type", "condition")))
                break
    # loop-until conditions at iteration ends
    flat, infos = proto.expand()
    for info in infos:
        until = list(info.get("until") or [])
        if not until:
            continue
        for ri in info.get("iter_ends", []):
            if ri >= len(rows):
                continue
            if any(_cond_met(c, rows[ri], spec, temp_source) for c in until):
                candidates.append((ri, "loop"))
                break  # earliest iteration of this loop wins
    if not candidates:
        return None
    ri, reason = min(candidates, key=lambda x: x[0])
    row = rows[ri]
    _labels = {"temperature": "temperature limit", "loop": "loop exit condition",
               "voltage": "voltage limit", "capacity": "capacity limit",
               "time": "time limit", "current": "current limit"}
    label = _labels.get(reason, f"{reason} condition")
    msg = f"{label} reached at cycle {row['cycle']} step {row['step']}"
    return {"reason": reason, "cycle": row["cycle"], "step": row["step"],
            "index": ri + 1, "message": msg}


def run_protocol(
    config: RunConfig,
    spec: PouchCellSpec,
    proto: Protocol,
    note: str = "",
    callbacks: list | None = None,
):
    """Run a multi-step :class:`Protocol` and return ``(sim, sol, metrics)``."""
    import time

    _t0 = time.time()
    model, dim, thermal, mesh = _resolve_protocol_model(config, proto)
    sim = _build_simulation(spec, config, model, dim, thermal, mesh)
    _t_build = time.time() - _t0
    _s = _parallel_scale(spec, dim)
    _ref_cap = spec.capacity_Ah / _s
    experiment = pybamm.Experiment(
        proto.experiment_cycles(_ref_cap, proto.default_temperature_source),
        period=proto.period,
        temperature=proto.run_condition_ambient_K(),
        termination=proto.run_termination_strings(spec) or None,
    )
    _t0 = time.time()
    sol = sim.run_experiment_obj(experiment, callbacks=callbacks)
    _t_solve = time.time() - _t0
    metrics = collect_metrics(sim, sol, config, spec=spec)
    # report the *actually resolved* model/dim/thermal/mesh (the protocol may
    # have forced SPM 2+1D x-lumped for thermal maps)
    metrics["model"] = model
    metrics["dimensionality"] = dim
    metrics["thermal"] = thermal
    metrics["mesh"] = mesh if isinstance(mesh, str) else str(mesh)
    metrics["analysis"] = "protocol"
    metrics["protocol_type"] = proto.type
    metrics["steps"] = collect_step_metrics(sol, parallel_scale=_s)
    metrics["timeline"] = {"build_s": round(_t_build, 3),
                           "solve_s": round(_t_solve, 3)}
    # post-hoc run-termination / loop-until stop (PyBaMM can't do these at runtime)
    stop = _posthoc_stop(proto, sol, spec, proto.default_temperature_source,
                         parallel_scale=_s)
    if stop:
        metrics["steps"] = metrics["steps"][: stop["index"]]
        metrics["stopped"] = {k: stop[k]
                              for k in ("reason", "cycle", "step", "message")}
    if note:
        metrics["note"] = note
    return sim, sol, metrics



def _build_simulation(spec, config, model_name, dimensionality, thermal, mesh):
    sim = PouchCellSimulation(
        spec=spec,
        model_name=model_name,
        dimensionality=dimensionality,
        thermal=thermal,
        parameter_set=config.parameter_set,
        initial_soc=config.initial_soc,
        initial_voltage=config.initial_voltage,
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
        from .parameters import apply_parameter_overrides
        apply_parameter_overrides(sim.param, config.extra_overrides)
    # 2+1D potential-pair models apply the cell current to a single layer, so
    # use the per-stack nominal capacity reference (the extensive metrics are
    # scaled back up by n_stacks in collect_metrics / collect_step_metrics).
    _s = _parallel_scale(spec, dimensionality)
    if _s > 1:
        sim.param["Nominal cell capacity [A.h]"] = spec.capacity_Ah / _s
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


def run(config: RunConfig, spec: PouchCellSpec | None = None, verbose: bool = True,
        callbacks: list | None = None):
    """Run a :class:`RunConfig` and return ``(sim, sol, metrics)``.

    Dispatch order: ``config.protocol`` (multi-step) -> ``tab`` analysis ->
    ``charge`` analysis -> plain constant-current discharge.
    """
    config.validate()
    spec = spec or config.spec()

    # --- multi-step protocol (takes precedence) --------------------------
    if config.protocol:
        proto = Protocol.from_dict(config.protocol)
        return run_protocol(config, spec, proto, callbacks=callbacks)

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
        metrics = collect_metrics(sim, sol, config, spec=spec)
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
    metrics = collect_metrics(sim, sol, config, spec=spec)
    return sim, sol, metrics
