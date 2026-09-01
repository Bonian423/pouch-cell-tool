"""Parallel studies — run many independent ``(config, spec)`` jobs in parallel.

Process-level parallelism via :class:`concurrent.futures.ProcessPoolExecutor`,
so it works for **every** model (0D / 1D / 2+1D / SPM_3D).  On Windows
``multiprocessing`` uses ``spawn``, so the worker must be a module-level,
importable function (see :func:`_study_worker`) and a caller running from a
plain script must guard its entry point with ``if __name__ == "__main__"``.

The alternative single-solve multi-input path (``sim.solve(inputs=..., nproc=N)``)
only works for 0D/1D models (an input current breaks the 2+1D current-collector
boundary conditions) — see :mod:`pouch_cell.core.sweep` for that.

Example
-------
>>> from pouch_cell.config.run import RunConfig
>>> from pouch_cell.core.study import grid_jobs, run_study, results_table
>>> base = RunConfig(model_name="DFN", dimensionality=0, thermal="lumped",
...                  mesh="draft", C_rate=1.0, duration_s=600.0)
>>> jobs = grid_jobs(base, vary={"C_rate": [0.5, 1.0, 2.0],
...                              "cooling": ["natural", "forced_air"]})
>>> results = run_study(jobs)          # 6 jobs fanned out across processes
>>> for row in results_table(results):
...     print(row)
"""
from __future__ import annotations

import os
from dataclasses import replace
from typing import Iterable

import numpy as np

from ..config.design import PouchCellSpec
from ..config.run import RunConfig


def _study_worker(payload: dict) -> dict:
    """Module-level (picklable) worker: build + run one ``(config, spec)`` job.

    Returns a small JSON-serialisable result — the job ``label`` (echoed back),
    an ``ok`` flag, the :func:`~pouch_cell.core.experiment.collect_metrics`
    dict, and (optionally) a downsampled ``(t, V)`` voltage trace.  Whole
    solutions are intentionally **not** returned: they are large, and pickling
    2+1D solutions back over the pipe is slow/error-prone.
    """
    try:
        config = RunConfig(**payload["config"])
        spec_dict = payload.get("spec")
        spec = PouchCellSpec.from_dict(spec_dict) if spec_dict else None
        trace = int(payload.get("trace_points") or 0)

        from .experiment import run  # lazy: heavy imports stay in the worker

        _sim, sol, metrics = run(config, spec=spec, verbose=False)
        out: dict = {"label": payload.get("label"), "ok": True, "metrics": metrics}
        if trace > 0:
            try:
                t = np.asarray(sol["Time [s]"].entries, dtype=float)
                v = np.asarray(sol["Voltage [V]"].entries, dtype=float)
                if len(t) > 0:
                    idx = np.linspace(0, len(t) - 1, min(trace, len(t)), dtype=int)
                    out["trace"] = {"t": t[idx].tolist(), "V": v[idx].tolist()}
            except Exception:  # noqa: BLE001 — trace is best-effort
                pass
        return out
    except Exception as err:  # noqa: BLE001 — one bad point must not kill the study
        return {"label": payload.get("label"), "ok": False,
                "error": repr(err), "metrics": {}}


def run_study(
    jobs: Iterable[dict],
    nproc: int | None = None,
    trace_points: int = 0,
) -> list[dict]:
    """Run a list of independent study jobs in parallel.

    Parameters
    ----------
    jobs :
        Iterable of dicts, each ``{"config": {...}, "spec": {...}, "label": ...}``
        — the serialised :class:`~pouch_cell.config.run.RunConfig` fields, an
        optional serialised :class:`~pouch_cell.config.design.PouchCellSpec`
        (defaults to ``config.spec()`` when omitted) and an optional label.
    nproc :
        Number of worker processes.  Defaults to ``os.cpu_count()`` (capped by
        the number of jobs).  Keep it at/below the physical core count and watch
        memory for large 2+1D / SPM_3D models (each process builds its own model).
    trace_points :
        If > 0, also return a downsampled ``(t, V)`` voltage trace per job
        (handy for overlay plots).  ``0`` returns metrics only (fastest).

    Returns
    -------
    list[dict]
        One result per job, in input order: ``{"label", "ok", "metrics", ...}``
        (or ``{"label", "ok": False, "error"}`` when a job raised).
    """
    jobs = [dict(j) for j in jobs]
    if not jobs:
        return []
    for j in jobs:
        j.setdefault("trace_points", trace_points)
    max_workers = max(1, min(int(nproc or (os.cpu_count() or 1)), len(jobs)))
    try:
        # joblib's loky backend spawns cleanly on Windows AND inside notebooks
        # (plain ProcessPoolExecutor re-imports __main__, which breaks Jupyter).
        from joblib import Parallel, delayed
    except ImportError:  # pragma: no cover - joblib ships with PyBaMM
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(max_workers=max_workers) as ex:
            return list(ex.map(_study_worker, jobs))
    return Parallel(n_jobs=max_workers, backend="loky")(
        delayed(_study_worker)(j) for j in jobs
    )


def grid_jobs(
    base: RunConfig,
    spec: PouchCellSpec | None = None,
    vary: dict[str, list] | None = None,
    label_fmt: str = "{key}={value}",
) -> list[dict]:
    """Build study jobs for a cartesian grid over ``RunConfig`` fields.

    ``vary`` maps a :class:`RunConfig` field name to a list of values, e.g.
    ``{"C_rate": [0.5, 1.0, 2.0], "cooling": ["natural", "forced_air"]}``
    produces 6 jobs.  The full spec is folded into each job's ``design`` dict so
    every worker rebuilds an identical cell.
    """
    import itertools

    keys = list((vary or {}).keys())
    values = [list((vary or {})[k]) for k in keys]
    spec_dict = spec.as_dict() if spec is not None else base.spec().as_dict()
    jobs: list[dict] = []
    for combo in itertools.product(*values) if keys else [()]:
        overrides = dict(zip(keys, combo))
        cfg = replace(base, **overrides)
        cfg.design = spec_dict  # carry the full design with each job
        label = ", ".join(
            label_fmt.format(key=k, value=v) for k, v in overrides.items()
        )
        jobs.append({"config": cfg.as_dict(), "label": label})
    return jobs


def results_table(results: list[dict]) -> list[dict]:
    """Flatten study results into comparable rows (ready for ``pandas``).

    Each row carries ``label``, ``ok``, and — for successful jobs — the key
    metrics (``final_V``, ``delivered_Ah``, ``Tmax_K``, ``analysis``, step count);
    failed jobs carry ``error`` instead.
    """
    rows: list[dict] = []
    for r in results:
        row = {"label": r.get("label"), "ok": r.get("ok")}
        m = r.get("metrics") or {}
        if r.get("ok"):
            row.update(
                {
                    "model": m.get("model"),
                    "final_V": m.get("final_V"),
                    "delivered_Ah": m.get("delivered_Ah"),
                    "Tmax_K": m.get("Tmax_K"),
                    "analysis": m.get("analysis"),
                    "protocol_type": m.get("protocol_type"),
                    "n_steps": len(m.get("steps") or []),
                }
            )
        else:
            row["error"] = r.get("error")
        rows.append(row)
    return rows
