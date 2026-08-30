"""Parallel C-rate discharge sweeps.

Two parallelisation routes:

* ``processes=None`` -- PyBaMM's **multi-input** path: the applied current is
  an ``InputParameter`` and all C-rates are integrated in a single solver call
  with ``nproc`` workers.  Works only for 0D/1D models.
* ``processes=N`` -- **process-level** parallelism via ``multiprocessing``;
  each C-rate solves in its own process with a fixed current, so it works for
  any model (including the 2+1D potential-pair and SPM_3D).
"""
from __future__ import annotations

import os as _os
from typing import Iterable

import numpy as np
import pybamm

from ..config.design import PouchCellSpec
from ..registry import MESH_PRESETS
from .model import build_geometry_3d_stack, build_model
from .parameters import build_parameter_values
from .simulation import resolve_mesh_3d


def _parallel_sweep_worker(job: tuple) -> tuple:
    """Module-level worker for process-level C-rate sweeps.

    Must be importable (picklable) for ``multiprocessing`` spawn on Windows.
    Each worker builds the model with the applied current fixed to the
    requested C-rate and returns a lightweight ``(c_rate, final_voltage)``
    summary.  This is the route that *does* work for the 2+1D potential-pair
    models (a fixed current avoids the input-in-boundary-condition problem).
    """
    c_rate, duration_s, model_name, dimensionality, thermal, mesh, spec = job
    param = build_parameter_values(spec)
    param["Current function [A]"] = c_rate * spec.capacity_Ah
    param.set_initial_state(1.0)
    model = build_model(
        model_name, dimensionality=dimensionality, thermal=thermal
    )
    geometry = None
    submesh_types = None
    if model_name == "SPM_3D":
        h = resolve_mesh_3d(mesh)
        geometry = build_geometry_3d_stack(model, spec)
        submesh_types = model.default_submesh_types.copy()
        submesh_types["cell"] = pybamm.ScikitFemGenerator3D("pouch", h=h)
        var_pts = {"x_n": 4, "x_s": 4, "x_p": 4, "r_n": 6, "r_p": 6}
    else:
        if isinstance(mesh, str):
            if mesh not in MESH_PRESETS or mesh.endswith("_3d"):
                raise ValueError(
                    f"Unknown mesh preset '{mesh}'. "
                    f"Use one of 'draft', 'standard', 'fine' or a var_pts dict."
                )
            var_pts = dict(MESH_PRESETS[mesh])
        else:
            var_pts = dict(mesh)
        if dimensionality < 2:
            var_pts.pop("y", None)
        if dimensionality < 1:
            var_pts.pop("z", None)
    sim = pybamm.Simulation(
        model, parameter_values=param, geometry=geometry,
        submesh_types=submesh_types, var_pts=var_pts,
        solver=pybamm.IDAKLUSolver(),
    )
    sol = sim.solve(t_eval=np.linspace(0.0, duration_s, max(2, int(duration_s))))
    return c_rate, float(sol["Voltage [V]"].entries[-1])


def parallel_sweep(
    spec: PouchCellSpec | None = None,
    C_rates: Iterable[float] = (0.5, 1.0, 2.0),
    duration_s: float = 60.0,
    model_name: str = "DFN",
    dimensionality: int = 0,
    thermal: str = "isothermal",
    mesh: str | dict = "draft",
    nproc: int | None = None,
    processes: int | None = None,
    initial_soc: float | None = 1.0,
    full_stack_3d: bool = False,
    **model_options,
):
    """Run a C-rate discharge sweep in parallel.

    * ``processes=None`` (default): PyBaMM's **multi-input** path -- the
      applied current is exposed as an ``InputParameter`` and all C-rates are
      integrated in a *single* solver call with ``nproc`` workers.  This works
      only for the **0D/1D** models (an input current breaks the 2+1D
      potential-pair current-collector boundary conditions).
    * ``processes=N``: **process-level** parallelism via ``multiprocessing`` --
      each C-rate is solved in its own process with the current fixed (not an
      input), so it works for **any** model, including the slow 2+1D DFN/SPMe
      and SPM_3D solves.  Returns lightweight ``(C_rate, final_voltage)``
      summaries.  Callers running scripts must guard with
      ``if __name__ == "__main__"`` (Windows spawn).

    Uses direct solves (no experiment): the integration runs to ``duration_s``
    with no voltage-cutoff event, so pick a duration suitable for the highest
    C-rate.

    Returns
    -------
    (solutions, C_rates)
        ``solutions`` is a list of :class:`pybamm.Solution` (multi-input mode)
        or ``(C_rate, final_voltage)`` tuples (process mode), aligned with
        ``C_rates``.
    """
    if spec is None:
        spec = PouchCellSpec()
    C_rates = list(C_rates)

    # --- process-level mode: works for any model (incl. 2+1D) -----------
    if processes:
        from concurrent.futures import ProcessPoolExecutor

        jobs = [
            (c, duration_s, model_name, dimensionality, thermal, mesh, spec)
            for c in C_rates
        ]
        with ProcessPoolExecutor(max_workers=int(processes)) as ex:
            results = list(ex.map(_parallel_sweep_worker, jobs))
        return results, C_rates

    # --- multi-input mode: 0D/1D only -----------------------------------
    if dimensionality >= 1:
        raise ValueError(
            "parallel_sweep multi-input mode only supports 0D/1D models; "
            "the 2+1D potential-pair models cannot take the applied "
            "current as an input.  Use processes=N for process-level "
            "parallelism (works for 2+1D)."
        )
    param = build_parameter_values(spec)
    param["Current function [A]"] = "[input]"
    if initial_soc is not None:
        param.set_initial_state(initial_soc)
    model = build_model(
        model_name,
        dimensionality=dimensionality,
        thermal=thermal,
        **model_options,
    )
    var_pts = dict(MESH_PRESETS[mesh]) if isinstance(mesh, str) else dict(mesh)
    solver = pybamm.IDAKLUSolver()
    sim = pybamm.Simulation(
        model, parameter_values=param, var_pts=var_pts, solver=solver,
    )
    t_eval = np.linspace(0.0, duration_s, max(2, int(duration_s)))
    amps = [c * spec.capacity_Ah for c in C_rates]
    inputs = [{"Current function [A]": a} for a in amps]
    n = nproc or _os.cpu_count() or 1
    sols = sim.solve(t_eval=t_eval, inputs=inputs, nproc=n)
    if not isinstance(sols, list):
        sols = [sols]
    return sols, C_rates
