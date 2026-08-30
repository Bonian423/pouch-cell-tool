"""Build PyBaMM ``ParameterValues`` for the NCM811/graphite pouch cell."""
from __future__ import annotations

import pybamm

from ..config.design import PouchCellSpec
from ..registry import PARAMETER_SETS

# Backwards-compatible alias for code that imported ``AVAILABLE_SETS``.
AVAILABLE_SETS = PARAMETER_SETS


def build_parameter_values(
    spec: PouchCellSpec,
    parameter_set: str = "Chen2020",
    ambient_temperature_K: float | None = None,
    heat_transfer_coefficient_W_m2K: float | None = None,
) -> pybamm.ParameterValues:
    """Build processed ``ParameterValues`` for the pouch cell.

    Parameters
    ----------
    spec : PouchCellSpec
        Cell design specification.
    parameter_set : str
        Base electrochemical parameter set. ``"Chen2020"`` (default) is an
        NCM811/graphite cell; ``"OKane2022"`` is NCM811 with a graphite-SiOx
        blend anode and SEI/degradation parameters.
    ambient_temperature_K : float, optional
        Ambient temperature (K).  Defaults to the value in ``spec``.
    heat_transfer_coefficient_W_m2K : float, optional
        Heat-transfer coefficient used for the pouch faces/tabs/edges
        (W/m^2/K).  Defaults to 5 W/m^2/K.

    Returns
    -------
    pybamm.ParameterValues
        Parameter values with the cell geometry, stack architecture,
        capacity and thermal settings applied.
    """
    if parameter_set not in PARAMETER_SETS:
        raise ValueError(
            f"Unknown parameter set '{parameter_set}'. "
            f"Choose from {PARAMETER_SETS}."
        )

    param = pybamm.ParameterValues(parameter_set)

    # Geometry, stack architecture, capacity and voltage limits
    param.update(spec.geometry_overrides())

    # Thermal boundary conditions (required by the x-lumped / lumped models)
    if heat_transfer_coefficient_W_m2K is None:
        h = 5.0
    else:
        h = heat_transfer_coefficient_W_m2K
    if ambient_temperature_K is None:
        T_amb = spec.ambient_temperature_K
    else:
        T_amb = ambient_temperature_K

    param.update(
        {
            "Ambient temperature [K]": T_amb,
            "Negative current collector surface heat transfer coefficient [W.m-2.K-1]": h,
            "Positive current collector surface heat transfer coefficient [W.m-2.K-1]": h,
            "Negative tab heat transfer coefficient [W.m-2.K-1]": h,
            "Positive tab heat transfer coefficient [W.m-2.K-1]": h,
            "Edge heat transfer coefficient [W.m-2.K-1]": h,
            "Total heat transfer coefficient [W.m-2.K-1]": h,
            # per-face coefficients required by the true-3D (SPM_3D) thermal model
            "Left face heat transfer coefficient [W.m-2.K-1]": h,
            "Right face heat transfer coefficient [W.m-2.K-1]": h,
            "Front face heat transfer coefficient [W.m-2.K-1]": h,
            "Back face heat transfer coefficient [W.m-2.K-1]": h,
            "Bottom face heat transfer coefficient [W.m-2.K-1]": h,
            "Top face heat transfer coefficient [W.m-2.K-1]": h,
            # cell volume / cooling area of the full-stack pouch, used by the
            # lumped thermal model (cell_geometry != "pouch")
            "Cell volume [m3]": (
                spec.height * spec.width * spec.thickness_total
            ),
            "Cell cooling surface area [m2]": (
                2.0 * spec.height * spec.width
                + 2.0 * spec.height * spec.thickness_total
                + 2.0 * spec.width * spec.thickness_total
            ),
        }
    )

    return param
