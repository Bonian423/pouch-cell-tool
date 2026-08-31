"""Subprocess runner for the Streamlit UI.

Usage::

    python -m pouch_cell.ui.worker --config <payload.json> --outdir <dir>

Reads a serialized ``{"spec": ..., "config": ...}`` payload, runs the solve,
and writes to ``<outdir>``:

* ``progress.json`` -- live status (polled by the UI; a watcher thread updates
  the elapsed time while the solve runs).
* ``result.json`` -- metrics + figure filenames (on success or error).
* ``*.png`` -- result figures.

The UI polls ``progress.json`` and can terminate this process to cancel.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import threading
import time
import traceback
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import pybamm  # noqa: E402  (after Agg backend; used by _LiveCallback)


def _write_progress(outdir: Path, **kw) -> None:
    data = {"pid": os.getpid()}
    data.update(kw)
    (outdir / "progress.json").write_text(
        json.dumps(data), encoding="utf-8"
    )


def _watcher(outdir: Path, stop: threading.Event) -> None:
    t0 = time.time()
    while not stop.is_set():
        # preserve stage / cycle / step written by the main thread or callbacks
        data = {}
        prog = outdir / "progress.json"
        if prog.is_file():
            try:
                data = json.loads(prog.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                data = {}
        data.update({"pid": os.getpid(), "status": "running",
                     "elapsed_s": round(time.time() - t0, 1)})
        prog.write_text(json.dumps(data), encoding="utf-8")
        time.sleep(1.0)


class _LiveCallback(pybamm.callbacks.Callback):
    """PyBaMM callback that streams stage / cycle / step to ``progress.json``.

    Attached to the real solve so the UI status bar shows exactly which step
    the simulation is on while it runs.
    """

    def __init__(self, outdir: Path) -> None:
        self.outdir = outdir

    def _set(self, **kw) -> None:
        _write_progress(self.outdir, status="running", stage="solving", **kw)

    def on_experiment_start(self, logs) -> None:  # noqa: D102
        self._set(cycle=1, step=1)

    def on_cycle_start(self, logs) -> None:  # noqa: D102
        cyc = logs.get("cycle number", (1, 1))
        self._set(cycle=cyc[0], cycle_total=cyc[1],
                  experiment_time=logs.get("experiment time"))

    def on_step_start(self, logs) -> None:  # noqa: D102
        cyc = logs.get("cycle number", (1, 1))
        stp = logs.get("step number", (1, 1))
        self._set(cycle=cyc[0], cycle_total=cyc[1],
                  step=stp[0], step_total=stp[1],
                  experiment_time=logs.get("experiment time"))

    def on_step_end(self, logs) -> None:  # noqa: D102
        self._set(experiment_time=logs.get("experiment time"))

    def on_cycle_end(self, logs) -> None:  # noqa: D102
        self._set(experiment_time=logs.get("experiment time"))

    def on_experiment_end(self, logs) -> None:  # noqa: D102
        pass

    def on_experiment_error(self, logs) -> None:  # noqa: D102
        pass


def _run_live_preview(outdir: Path, spec, config, proto) -> None:
    """Stream a fast 1D voltage preview of the protocol to ``live_vt.json``.

    Best-effort: a cheap 1D DFN solve of the same protocol, run step-by-step
    (and sub-chunked for long duration steps) with ``starting_solution``
    chaining, writing the cumulative ``(t, V)`` after every chunk so the UI can
    draw a growing real-time voltage figure.  Never raises.
    """
    import math

    import numpy as np
    import pybamm

    from ..core.experiment import _build_simulation
    from ..config.protocol import Step

    try:
        sim = _build_simulation(spec, config, "DFN", 0, "lumped", "draft")
    except Exception:  # noqa: BLE001 - preview is best-effort
        return

    # plan: split duration-based steps into sub-chunks, capped so the whole
    # preview stays cheap (<=~30 chunks even for hour-long protocols)
    steps = list(proto.steps) or [Step(kind="discharge", c_rate=1.0, duration_s=60.0)]
    total_dur = 0.0
    n_cycles = max(1, int(proto.cycles))
    for _ in range(n_cycles):
        for stp in steps:
            if stp.duration_s and stp.duration_s > 0:
                total_dur += float(stp.duration_s)
    chunk_s = max(1.0, total_dur / 30.0)

    plan: list[str] = []
    for _ in range(n_cycles):
        for stp in steps:
            if stp.duration_s and stp.duration_s > 0:
                d = float(stp.duration_s)
                n = max(1, int(math.ceil(d / chunk_s)))
                for k in range(n):
                    sub = Step(
                        kind=stp.kind, c_rate=stp.c_rate, current_A=stp.current_A,
                        power_W=stp.power_W,
                        duration_s=min(chunk_s, d - k * chunk_s), cutoff_V=None,
                        hold_voltage_V=stp.hold_voltage_V,
                        cutoff_current_C=stp.cutoff_current_C,
                    )
                    plan.append(sub.to_string(spec.capacity_Ah))
            else:
                plan.append(stp.to_string(spec.capacity_Ah))
    n_total = len(plan)

    prev = None
    for i, step_str in enumerate(plan):
        try:
            exp = pybamm.Experiment([step_str], period=None)
            sim.sim = pybamm.Simulation(**sim._sim_kwargs, experiment=exp)
            sol = sim.sim.solve(starting_solution=prev)
            prev = sim.sim.solution if sim.sim.solution is not None else sol
            # the chained solution is CUMULATIVE: it already holds the whole
            # (t, V) history from t=0, so write it directly (no t_off math)
            tt = np.asarray(sol["Time [s]"].entries)
            vv = np.asarray(sol["Voltage [V]"].entries)
            (outdir / "live_vt.json").write_text(
                json.dumps({"t": tt.tolist(), "V": vv.tolist()}, default=float),
                encoding="utf-8",
            )
            _write_progress(
                outdir, status="running", stage="live preview",
                cycle=1, cycle_total=max(1, int(proto.cycles)),
                step=i + 1, step_total=n_total,
                experiment_time=float(tt[-1]) if len(tt) else 0.0,
            )
        except Exception:  # noqa: BLE001 - stop streaming on any chunk failure
            return


def _to_timeseries(arr) -> np.ndarray:
    """Flatten a solution-variable array to a 1D time series (spatial mean)."""
    import numpy as np

    a = np.asarray(arr, dtype=float)
    while a.ndim > 1:
        a = a.mean(axis=0)
    return a


def _save_vt_csv(outdir: Path, sol) -> None:
    """Save Voltage(t) / Temperature(t) as a small CSV for later re-plotting."""
    import numpy as np

    t = _to_timeseries(sol["Time [s]"].entries)
    V = _to_timeseries(sol["Voltage [V]"].entries)
    T = None
    for name in (
        "Volume-averaged cell temperature [K]",
        "X-averaged cell temperature [K]",
        "Cell temperature [K]",
    ):
        try:
            T = _to_timeseries(sol[name].entries)
        except KeyError:
            continue
        break
    with open(outdir / "vt.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["time_s", "voltage_V", "temperature_K"])
        for i in range(len(t)):
            w.writerow([t[i], V[i], float(T[i]) if T is not None else ""])


def _save_figures(outdir: Path, sim, sol, config, spec, metrics) -> list[str]:
    """Save the result figures (per-model maps, per-step maps) + V/T CSV."""
    import matplotlib.pyplot as plt
    from .. import plotting

    names: list[str] = []
    if config.analysis == "tab":
        fig = plotting.plot_tab_heating(sol, spec, param=sim.param)
        fig.savefig(outdir / "tab_heating.png", dpi=110, bbox_inches="tight")
        plt.close(fig)
        names.append("tab_heating.png")
        return names

    # V/T time series + CSV (always)
    fig = plotting.plot_discharge(sol, spec)
    fig.savefig(outdir / "discharge.png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    names.append("discharge.png")
    try:
        _save_vt_csv(outdir, sol)
    except Exception:  # noqa: BLE001 - CSV is best-effort
        pass

    dim = int(getattr(sim, "dimensionality", 0))
    if dim == 2:
        # temperature + current-density + Ohmic-heating maps in one figure
        fig = plotting.plot_tab_heating(sol, spec, param=sim.param)
        fig.savefig(outdir / "thermal_maps.png", dpi=110, bbox_inches="tight")
        plt.close(fig)
        names.append("thermal_maps.png")
    elif config.model_name == "SPM_3D":
        try:
            fig = plotting.plot_3d_cross_section(
                sol, variable="Cell temperature [K]", plane="yz", position=0.5
            )
            fig.savefig(outdir / "temperature_3d.png", dpi=110, bbox_inches="tight")
            plt.close(fig)
            names.append("temperature_3d.png")
        except Exception:  # noqa: BLE001
            pass

    # per-step thermal maps (multi-step protocol on a 2+1D model)
    steps = metrics.get("steps") or []
    if steps and dim == 2:
        from ..config.protocol import Protocol

        proto = Protocol.from_dict(config.protocol) if config.protocol else None
        mode = (proto.step_map_mode if proto else "every")
        if mode == "cycle_last":
            last_by_cycle: dict = {}
            for row in steps:
                last_by_cycle[row["cycle"]] = row
            steps = list(last_by_cycle.values())
        for row in steps:
            try:
                fig = plotting.plot_tab_heating(
                    sol, spec, param=sim.param, t=float(row["t_end_s"])
                )
                name = f"step_{int(row['cycle']):02d}_{int(row['step']):02d}.png"
                fig.savefig(outdir / name, dpi=110, bbox_inches="tight")
                plt.close(fig)
                names.append(name)
            except Exception:  # noqa: BLE001 - per-step maps are best-effort
                continue
    return names


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--outdir", required=True)
    args = p.parse_args(argv)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    payload = json.loads(Path(args.config).read_text(encoding="utf-8"))
    spec_dict = payload.get("spec", {})
    cfg_dict = payload.get("config", {})

    stop = threading.Event()
    watcher = threading.Thread(target=_watcher, args=(outdir, stop), daemon=True)
    watcher.start()
    t0 = time.time()

    try:
        from ..config.design import PouchCellSpec
        from ..config.run import RunConfig
        from ..core.experiment import collect_metrics, run

        spec = PouchCellSpec(**spec_dict)
        config = RunConfig(**cfg_dict)
        config.validate()

        _write_progress(outdir, status="running", stage="building model")
        if config.analysis == "tab":
            from ..core.analysis import tab_heating_analysis
            from ..core.solvers import make_solver

            sim, sol, _fig = tab_heating_analysis(
                spec=spec,
                C_rate=config.C_rate,
                duration_s=config.duration_s or 5,
                mesh=config.mesh,
                particle=config.particle,
                model_name=config.model_name,
                cooling=config.cooling,
                parameter_set=config.parameter_set,
                solver=make_solver(config.solver),
                size_to_capacity=config.size_to_capacity,
            )
            metrics = collect_metrics(sim, sol, config)
            metrics["analysis"] = "tab"
        else:
            # stream a fast 1D voltage preview first (best-effort) so the UI can
            # draw a growing real-time voltage figure during the run
            if config.protocol:
                from ..config.protocol import Protocol

                proto = Protocol.from_dict(config.protocol)
                _write_progress(outdir, status="running", stage="live preview")
                _run_live_preview(outdir, spec, config, proto)
            _write_progress(outdir, status="running", stage="solving")
            live_cb = _LiveCallback(outdir)
            sim, sol, metrics = run(
                config, spec=spec, verbose=False, callbacks=[live_cb]
            )

        _write_progress(outdir, status="running", stage="post-processing")
        metrics["figures"] = _save_figures(outdir, sim, sol, config, spec, metrics)
        metrics["wall_s"] = round(time.time() - t0, 2)
        metrics["sizing_history"] = getattr(sim, "sizing_history", [])

        stop.set()
        (outdir / "result.json").write_text(
            json.dumps(metrics, indent=2, default=float), encoding="utf-8"
        )
        _write_progress(outdir, status="done", stage="complete", wall_s=metrics["wall_s"])
        return 0
    except Exception as err:  # noqa: BLE001 - report any failure to the UI
        stop.set()
        _write_progress(outdir, status="error", error=repr(err))
        (outdir / "result.json").write_text(
            json.dumps(
                {"error": repr(err), "traceback": traceback.format_exc()}
            ),
            encoding="utf-8",
        )
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
