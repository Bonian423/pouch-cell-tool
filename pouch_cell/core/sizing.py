"""Automatic electrode sizing.

The requested *nominal* capacity is a design input.  Given the fixed footprint
and number of parallel stacks, the electrode thicknesses must be chosen so the
cell actually delivers the target capacity (to the lower voltage cut-off).
This module iteratively scales the negative and positive electrode thicknesses
(keeping the N/P ratio constant) until a fast 1D reference simulation delivers
``target_Ah`` within tolerance.
"""
from __future__ import annotations

import copy

import pybamm

from ..config.design import PouchCellSpec
from .model import build_model
from .parameters import build_parameter_values

_FAST_VAR_PTS = {"x_n": 20, "x_s": 20, "x_p": 20, "r_n": 30, "r_p": 30}


def _delivered_capacity(spec: PouchCellSpec, C_rate: float) -> float:
    """Run a fast 1D DFN discharge and return the coulomb-counted capacity (Ah)."""
    param = build_parameter_values(spec)
    param.set_initial_state(1.0)  # fully charged
    model = build_model("DFN", dimensionality=0, thermal="isothermal")
    experiment = pybamm.Experiment(
        [f"Discharge at {C_rate}C until {spec.lower_cutoff_V} V"]
    )
    sim = pybamm.Simulation(
        model,
        parameter_values=param,
        var_pts=_FAST_VAR_PTS,
        experiment=experiment,
    )
    sol = sim.solve()
    return float(sol["Discharge capacity [A.h]"].entries[-1])


def size_electrodes_to_capacity(
    spec: PouchCellSpec,
    target_Ah: float | None = None,
    tolerance: float = 0.02,
    max_iter: int = 8,
    C_rate: float = 1.0,
    verbose: bool = True,
) -> tuple[PouchCellSpec, list[float]]:
    """Return a copy of ``spec`` whose electrode thicknesses deliver ``target_Ah``.

    Parameters
    ----------
    spec : PouchCellSpec
        The cell design (footprint, stacks, chemistry are fixed).
    target_Ah : float, optional
        Capacity to deliver (defaults to ``spec.capacity_Ah``).
    tolerance : float
        Relative tolerance on the delivered capacity.
    max_iter : int
        Maximum number of sizing iterations.
    C_rate : float
        Reference C-rate used to measure delivered capacity (default 1C).
    verbose : bool
        Print the sizing iterations.

    Returns
    -------
    (sized_spec, history)
        The resized cell specification (a copy; the input is untouched) and the
        delivered-capacity history of the iterations in Ah.
    """
    if target_Ah is None:
        target_Ah = spec.capacity_Ah
    if target_Ah <= 0:
        raise ValueError("target_Ah must be positive.")

    sized = copy.copy(spec)
    history: list[float] = []
    converged = False

    for it in range(1, max_iter + 1):
        cap = _delivered_capacity(sized, C_rate)
        history.append(cap)
        if not cap or cap <= 0:
            raise RuntimeError(
                f"Sizing failed: reference discharge delivered {cap:.3f} Ah."
            )
        scale = target_Ah / cap
        if verbose:
            print(
                f"  [sizing {it}/{max_iter}] L_n = {sized.L_n * 1e6:.1f} um, "
                f"L_p = {sized.L_p * 1e6:.1f} um -> delivers {cap:.2f} Ah "
                f"(target {target_Ah:.2f} Ah, scale {scale:.3f})"
            )
        if abs(scale - 1.0) < tolerance:
            converged = True
            break
        # Delivered capacity is NOT monotonic in electrode thickness (thicker
        # electrodes are transport-limited, so capacity can fall as we grow).
        # If we are trying to grow and the capacity just dropped, the target
        # is beyond the cell's practical maximum -> stop rather than diverge.
        if it > 1 and scale > 1.0 and cap < history[-2]:
            raise RuntimeError(
                f"Cannot reach {target_Ah:.2f} Ah for this footprint/stacks: "
                f"delivered capacity falls as the electrodes thicken "
                f"(transport-limited; best so far {max(history):.2f} Ah). "
                "Try a smaller target, a larger footprint, or more stacks."
            )
        # clamp the per-step scaling to avoid runaway divergence
        scale = min(max(scale, 0.5), 2.0)
        # scale both electrodes together to keep the N/P ratio fixed
        sized.L_n *= scale
        sized.L_p *= scale

    if not converged:
        raise RuntimeError(
            f"Sizing did not converge to {target_Ah:.2f} Ah in {max_iter} "
            f"iterations (best delivered {max(history):.2f} Ah). The target may "
            "exceed the cell's transport-limited maximum; try a smaller target, "
            "a larger footprint, or more stacks."
        )

    sized.capacity_Ah = target_Ah
    return sized, history
