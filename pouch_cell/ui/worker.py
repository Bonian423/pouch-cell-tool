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


def _save_figures(outdir: Path, sim, sol, config, spec) -> list[str]:
    """Save the result figures and return their filenames."""
    import matplotlib.pyplot as plt
    from .. import plotting

    names: list[str] = []
    if config.analysis == "tab":
        fig = plotting.plot_tab_heating(sol, spec, param=sim.param)
        fig.savefig(outdir / "tab_heating.png", dpi=110, bbox_inches="tight")
        plt.close(fig)
        names.append("tab_heating.png")
        return names

    fig = plotting.plot_discharge(sol, spec)
    fig.savefig(outdir / "discharge.png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    names.append("discharge.png")
    if config.dimensionality == 2:
        plotting.plot_temperature_map(sol)
        plt.savefig(outdir / "temperature.png", dpi=110, bbox_inches="tight")
        plt.close()
        names.append("temperature.png")
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
        metrics["figures"] = _save_figures(outdir, sim, sol, config, spec)
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
