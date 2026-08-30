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


def _write_progress(outdir: Path, **kw) -> None:
    data = {"pid": os.getpid()}
    data.update(kw)
    (outdir / "progress.json").write_text(
        json.dumps(data), encoding="utf-8"
    )


def _watcher(outdir: Path, stop: threading.Event) -> None:
    t0 = time.time()
    while not stop.is_set():
        _write_progress(outdir, status="running", elapsed_s=round(time.time() - t0, 1))
        time.sleep(1.0)


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
            _write_progress(outdir, status="running", stage="solving")
            sim, sol, metrics = run(config, spec=spec, verbose=False)

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
