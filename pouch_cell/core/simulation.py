"""High-level simulation runner (:class:`PouchCellSimulation`).

The class is deliberately *thin*: the cooling / heat-pipe parameter logic lives
in :mod:`pouch_cell.thermal`, the C-rate sweep in :mod:`pouch_cell.core.sweep`
and the tab analysis in :mod:`pouch_cell.core.analysis`.  This module keeps the
run/solve loop, the mesh resolution and the convenience accessors.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pybamm

from ..config.design import PouchCellSpec
from ..registry import MESH_PRESETS
from ..thermal.cooling import resolve_cooling
from ..thermal.heat_pipe import heat_pipe_overrides
from .model import build_geometry_3d_stack, build_model
from .parameters import build_parameter_values
from .sizing import size_electrodes_to_capacity

# Backwards-compatible aliases (old code imported these from simulation).
_MESH_PRESETS = MESH_PRESETS


def resolve_mesh_21d(mesh, dimensionality: int) -> dict:
    """Resolve a 2+1D mesh preset name or ``var_pts`` dict for ``dimensionality``."""
    if isinstance(mesh, str):
        if mesh not in MESH_PRESETS or mesh.endswith("_3d"):
            raise ValueError(
                f"Unknown mesh preset '{mesh}'. "
                f"Use one of 'draft', 'standard', 'fine' or a var_pts dict."
            )
        var_pts = dict(MESH_PRESETS[mesh])
    else:
        var_pts = dict(mesh)
    # remove coordinates that are not discretised at this dimensionality
    if dimensionality < 2:
        var_pts.pop("y", None)
    if dimensionality < 1:
        var_pts.pop("z", None)
    return var_pts


def resolve_mesh_3d(mesh) -> float:
    """Resolve a true-3D mesh preset name (or element size) to a size in metres."""
    if isinstance(mesh, str):
        key = mesh if mesh.endswith("_3d") else mesh + "_3d"
        if key not in MESH_PRESETS:
            raise ValueError(
                f"Unknown mesh preset '{mesh}' for the 3D model. "
                "Use 'draft', 'standard' or 'fine'."
            )
        return MESH_PRESETS[key]
    return float(mesh)  # treated as element size


class PouchCellSimulation:
    """Run and analyse PyBaMM simulations of the NCM811/graphite pouch.

    Parameters
    ----------
    spec : PouchCellSpec, optional
        Cell design.  Defaults to the stock pouch.
    model_name : str
        ``"DFN"`` (default, recommended), ``"SPM"``, ``"SPMe"`` or
        ``"SPM_3D"`` (true 3D FEM thermal).
    dimensionality : int
        Current-collector dimensionality for the 2+1D models (0, 1 or 2).
        Ignored by ``SPM_3D``.
    thermal : str
        ``"x-lumped"`` (default), ``"lumped"`` or ``"isothermal"``.
    parameter_set : str
        ``"Chen2020"`` (default) or ``"OKane2022"``.
    initial_soc : float or None
        Initial state of charge (0-1).  ``None`` keeps the parameter-set
        default; for a discharge from full use ``1.0`` (the default).
    mesh : str or dict
        ``"draft"``, ``"standard"`` (default), ``"fine"`` or a custom
        ``var_pts`` dict (or element size for ``SPM_3D``).
    solver : pybamm.Solver, optional
        Override the default DAE solver.
    output_variables : list[str], optional
        Only compute/store these output variables in the solution.
    store_first_last : bool, optional
        If True, only the first and last sample of each integration window are
        stored (memory-light).
    heat_transfer_coefficient : float, optional
        Uniform surface heat-transfer coefficient (W/m^2/K), default 5.
    cooling : str or dict, optional
        Convenience control for thermal dissipation / active cooling
        (preset name or dict of parameter overrides) -- see
        :func:`pouch_cell.thermal.cooling.resolve_cooling`.
    full_stack_3d : bool
        Only for ``SPM_3D``: span the ``cell`` domain over the full stack
        thickness instead of a single unit cell.
    **model_options
        Extra options forwarded to the PyBaMM model.
    """

    def __init__(
        self,
        spec: PouchCellSpec | None = None,
        model_name: str = "DFN",
        dimensionality: int = 2,
        thermal: str = "x-lumped",
        parameter_set: str = "Chen2020",
        initial_soc: float | None = 1.0,
        initial_voltage: float | None = None,
        mesh: str | dict = "standard",
        solver: pybamm.Solver | None = None,
        output_variables: list[str] | None = None,
        store_first_last: bool | None = None,
        heat_transfer_coefficient: float | None = None,
        cooling: str | dict | None = None,
        full_stack_3d: bool = False,
        size_to_capacity: bool = True,
        sizing_tolerance: float = 0.02,
        **model_options,
    ):
        if solver is None and (output_variables is not None
                               or store_first_last is not None):
            solver = pybamm.IDAKLUSolver(
                output_variables=output_variables or [],
                store_first_last=bool(store_first_last),
            )
        elif output_variables is not None:
            # respect an explicitly-provided solver, but record the request
            self.output_variables = output_variables
        self._requested_output_variables = output_variables
        self.spec = spec if spec is not None else PouchCellSpec()
        self.model_name = model_name
        self.dimensionality = dimensionality
        self.thermal = thermal
        self.initial_soc = initial_soc
        self.initial_voltage = initial_voltage

        # --- size the electrodes so the cell delivers the target capacity ---
        self.sizing_history: list[float] = []
        if size_to_capacity:
            self.spec, self.sizing_history = size_electrodes_to_capacity(
                self.spec,
                target_Ah=self.spec.capacity_Ah,
                tolerance=sizing_tolerance,
                verbose=True,
            )

        # --- parameter values -----------------------------------------------
        h_cool, t_amb_cool, extra_cool = resolve_cooling(cooling)
        if h_cool is not None:
            heat_transfer_coefficient = h_cool  # cooling preset/dict wins
        self.param = build_parameter_values(
            self.spec,
            parameter_set=parameter_set,
            heat_transfer_coefficient_W_m2K=heat_transfer_coefficient,
            ambient_temperature_K=t_amb_cool,
        )
        self.cooling = cooling

        # --- optional localized heat-pipe cooling (2+1D x-lumped only) -----
        if (self.spec.heat_pipe_enabled
                and dimensionality == 2 and thermal == "x-lumped"):
            try:
                h_base = float(
                    self.param["Edge heat transfer coefficient [W.m-2.K-1]"]
                )
            except (TypeError, ValueError):
                h_base = 5.0
            try:
                T_base = float(self.param["Ambient temperature [K]"])
            except (TypeError, ValueError):
                T_base = self.spec.ambient_temperature_K
            self.param.update(heat_pipe_overrides(self.spec, h_base, T_base))
        if initial_voltage is not None:
            # start the cell at a target open-circuit voltage (PyBaMM
            # interprets "3.9 V" as a voltage, 0-1 as a SOC)
            self.param.set_initial_state(f"{initial_voltage:g} V")
        elif initial_soc is not None:
            if not 0.0 <= initial_soc <= 1.0:
                raise ValueError("initial_soc must be between 0 and 1.")
            self.param.set_initial_state(initial_soc)
        # cooling / raw overrides are applied *after* the initial state so
        # they win over set_initial_state (which would otherwise reset any
        # concentration-type override back to the SOC-1.0 values)
        if extra_cool:
            self.param.update(extra_cool)

        # --- model -----------------------------------------------------------
        self.model = build_model(
            model_name=model_name,
            dimensionality=dimensionality,
            thermal=thermal,
            **model_options,
        )

        # --- geometry / mesh -------------------------------------------------
        geometry = None
        submesh_types = None
        if model_name == "SPM_3D":
            self.dimensionality = 3
            h = resolve_mesh_3d(mesh)
            geometry = (
                build_geometry_3d_stack(self.model, self.spec)
                if full_stack_3d
                else None
            )
            submesh_types = self.model.default_submesh_types.copy()
            submesh_types["cell"] = pybamm.ScikitFemGenerator3D("pouch", h=h)
            var_pts = {
                "x_n": 4, "x_s": 4, "x_p": 4, "r_n": 6, "r_p": 6,
                "x": None, "y": None, "z": None,
            }
        else:
            var_pts = resolve_mesh_21d(mesh, dimensionality)

        self.var_pts = var_pts

        # The pybamm.Simulation is constructed lazily so that an experiment can
        # be attached at solve time (in this PyBaMM version the experiment is a
        # constructor argument, not a solve() argument).  Discretisation is
        # cached by PyBaMM, so re-creating the Simulation for a new experiment
        # is cheap.
        self._sim_kwargs = dict(
            model=self.model,
            parameter_values=self.param,
            geometry=geometry,
            submesh_types=submesh_types,
            var_pts=var_pts,
            solver=solver,
        )
        self.sim: pybamm.Simulation | None = None
        self.solution = None

    # ------------------------------------------------------------------ #
    # Running simulations
    # ------------------------------------------------------------------ #
    def run_experiment(
        self,
        steps: Iterable[str],
        period: str | None = None,
        **sim_kwargs,
    ) -> pybamm.Solution:
        """Run a PyBaMM experiment (list of step strings).

        ``period`` controls the spacing of saved output points (e.g.
        ``"10 seconds"``); a coarser period saves fewer points and reduces
        post-processing cost (the solution is still integrated fully).

        Example
        -------
        >>> sim = PouchCellSimulation()
        >>> sol = sim.run_experiment([
        ...     "Discharge at 1C until 2.5 V",
        ...     "Rest for 10 minutes",
        ... ])
        """
        experiment = pybamm.Experiment(list(steps), period=period)
        self.sim = pybamm.Simulation(**self._sim_kwargs, experiment=experiment)
        self.solution = self.sim.solve(**sim_kwargs)
        return self.solution

    def run_experiment_obj(
        self,
        experiment: pybamm.Experiment,
        callbacks: list | None = None,
        **sim_kwargs,
    ) -> pybamm.Solution:
        """Run a pre-built :class:`pybamm.Experiment`.

        Supports everything ``Experiment`` accepts that ``run_experiment``
        doesn't expose directly: cycles, ``temperature`` and overall
        ``termination`` conditions (used by multi-step protocols).
        """
        self.sim = pybamm.Simulation(**self._sim_kwargs, experiment=experiment)
        if callbacks:
            sim_kwargs["callbacks"] = callbacks
        self.solution = self.sim.solve(**sim_kwargs)
        return self.solution

    def discharge(
        self,
        C_rate: float = 1.0,
        duration_s: float | None = None,
        cutoff_V: float | None = None,
        **sim_kwargs,
    ) -> pybamm.Solution:
        """Constant-current discharge.

        Either ``duration_s`` or ``cutoff_V`` (or both) may be given.

        Example
        -------
        >>> sol = sim.discharge(C_rate=1.0, cutoff_V=2.5)      # full 1C discharge
        >>> sol = sim.discharge(C_rate=0.5, duration_s=600)    # 10 min at C/2
        """
        if cutoff_V is None:
            cutoff_V = self.spec.lower_cutoff_V
        if duration_s is not None:
            step = f"Discharge at {C_rate}C for {duration_s} seconds"
        else:
            step = f"Discharge at {C_rate}C until {cutoff_V} V"
        return self.run_experiment([step], **sim_kwargs)

    def solve(self, t_eval, t_interp=None, **sim_kwargs) -> pybamm.Solution:
        """Solve directly over a time grid (uses the parameter-set current).

        ``t_eval`` lists the times the solver must stop at.  For smoother
        output without extra stops, pass a *coarse* ``t_eval`` and a fine
        ``t_interp``: the IDAKLU solver interpolates at the interpolation
        points without stopping, which is faster than requesting every output
        time in ``t_eval``.
        """
        self.sim = pybamm.Simulation(**self._sim_kwargs)
        self.solution = self.sim.solve(
            t_eval=t_eval, t_interp=t_interp, **sim_kwargs
        )
        return self.solution

    # ------------------------------------------------------------------ #
    # Parallel C-rate sweep & tab analysis (delegated to dedicated modules)
    # ------------------------------------------------------------------ #
    @classmethod
    def parallel_sweep(
        cls,
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
        """Run a C-rate discharge sweep in parallel -- see
        :func:`pouch_cell.core.sweep.parallel_sweep` for details."""
        from .sweep import parallel_sweep as _run

        return _run(
            spec=spec,
            C_rates=C_rates,
            duration_s=duration_s,
            model_name=model_name,
            dimensionality=dimensionality,
            thermal=thermal,
            mesh=mesh,
            nproc=nproc,
            processes=processes,
            initial_soc=initial_soc,
            full_stack_3d=full_stack_3d,
            **model_options,
        )

    @classmethod
    def tab_heating_analysis(
        cls,
        spec: PouchCellSpec | None = None,
        C_rate: float = 1.0,
        duration_s: float = 5,
        mesh: str | dict = "micro_21d",
        particle: str = "uniform profile",
        model_name: str = "DFN",
        cooling: str | dict | None = None,
        **kwargs,
    ):
        """Tab-driven resistive-heating analysis -- see
        :func:`pouch_cell.core.analysis.tab_heating_analysis` for details."""
        from .analysis import tab_heating_analysis as _run

        return _run(
            cls=cls,
            spec=spec,
            C_rate=C_rate,
            duration_s=duration_s,
            mesh=mesh,
            particle=particle,
            model_name=model_name,
            cooling=cooling,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    # Convenience accessors
    # ------------------------------------------------------------------ #
    def get(self, variable: str, t: float | None = None):
        """Return a solution variable (optionally interpolated at time ``t``)."""
        if self.solution is None:
            raise RuntimeError("No solution yet -- run a simulation first.")
        var = self.solution[variable]
        if t is not None:
            return var(t)
        return var

    def discharge_capacity_Ah(self) -> float:
        """Coulomb-counted discharge capacity of the last solution (Ah)."""
        cap = self.solution["Discharge capacity [A.h]"].entries
        return float(cap[-1])

    def summary(self) -> str:
        """Design + (if available) simulation summary."""
        lines = [self.spec.report(self.param)]
        if self.sizing_history:
            lines.append(
                f"  Electrode sizing  : L_n = {self.spec.L_n * 1e6:.1f} um, "
                f"L_p = {self.spec.L_p * 1e6:.1f} um "
                f"(delivered {self.sizing_history[-1]:.2f} Ah at 1C)"
            )
        lines.append(
            f"  Model            : {self.model_name}"
            f" (dimensionality {self.dimensionality}, thermal '{self.thermal}')"
        )
        if self.solution is not None:
            V = self.solution["Voltage [V]"].entries
            T = self.solution["Volume-averaged cell temperature [K]"]
            lines.append(
                f"  Discharge        : {V[0]:.3f} V -> {V[-1]:.3f} V | "
                f"{self.discharge_capacity_Ah():.3f} Ah | "
                f"T = {T.entries[0]:.1f} K -> {T.entries[-1]:.1f} K"
            )
        return "\n".join(lines)
