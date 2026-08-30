"""Build PyBaMM models for the pouch cell.

Two families of models are available:

1. **2+1D pouch models** (``SPM``, ``SPMe``, ``DFN``): the standard PyBaMM
   "3D pouch cell" models.  They resolve the through-plane coordinate ``x``
   (electrodes / separator / particles) plus the in-plane current-collector
   coordinates ``y`` and ``z``, with the full current-collector potential pair.
   This captures inhomogeneous current distribution, voltage and temperature
   across the face -- the workhorse of the tool.

2. **True 3D thermal model** (``SPM_3D``): an SPM electrochemical model coupled
   to a genuinely 3D finite-element heat equation on the whole cell volume
   (``pybamm.lithium_ion.Basic3DThermalSPM``).  Use it when the through-plane
   temperature gradient across the stack is of interest.
"""
from __future__ import annotations

import pybamm

from ..config.design import PouchCellSpec
from ..registry import MODEL_NAMES


def _check_thermal(thermal: str, dimensionality: int, model_name: str) -> None:
    if model_name == "SPM_3D":
        return
    if thermal not in ("isothermal", "lumped", "x-lumped", "x-full"):
        raise ValueError(
            f"Unknown thermal option '{thermal}'. "
            "Choose from 'isothermal', 'lumped', 'x-lumped', 'x-full'."
        )
    if thermal == "x-full" and dimensionality != 0:
        raise ValueError("thermal='x-full' is only valid for dimensionality=0.")
    if thermal == "x-lumped" and dimensionality == 0:
        raise ValueError("thermal='x-lumped' requires dimensionality >= 1.")


def build_model(
    model_name: str = "DFN",
    dimensionality: int = 2,
    thermal: str = "x-lumped",
    **extra_options,
):
    """Build a PyBaMM lithium-ion model for the pouch cell.

    Parameters
    ----------
    model_name : str
        One of ``"DFN"`` (default), ``"SPM"``, ``"SPMe"`` or ``"SPM_3D"``.
    dimensionality : int
        Current-collector dimensionality (``0``, ``1`` or ``2``).  Only used
        for the 2+1D models; ``SPM_3D`` is always genuinely 3D.
    thermal : str
        Thermal submodel: ``"isothermal"``, ``"lumped"``, ``"x-lumped"``
        (default) or ``"x-full"`` (1D only).
    **extra_options
        Any additional model options, e.g. ``{"particle": "uniform profile"}``.
    """
    if model_name not in MODEL_NAMES:
        raise ValueError(
            f"Unknown model '{model_name}'. Choose from {MODEL_NAMES}."
        )
    _check_thermal(thermal, dimensionality, model_name)

    if model_name == "SPM_3D":
        # True 3D FEM thermal + SPM electrochemistry
        options = {
            "cell geometry": "pouch",
            "dimensionality": 3,
            **extra_options,
        }
        return pybamm.lithium_ion.Basic3DThermalSPM(options=options)

    options = {
        # a 0D model has no current-collector mesh, so a uniform current
        # distribution is used there; 1D/2D resolve the potential pair
        "current collector": "potential pair" if dimensionality > 0 else "uniform",
        "dimensionality": dimensionality,
        "thermal": thermal,
        **extra_options,
    }
    model_cls = getattr(pybamm.lithium_ion, model_name)
    return model_cls(options=options)


def build_geometry_3d_stack(model, spec: PouchCellSpec):
    """Return a custom geometry for the true-3D model whose through-plane
    extent spans the *full* stack thickness.

    The default ``Basic3DThermalSPM`` geometry only spans a single unit-cell
    thickness in ``x``.  For a faithful representation of the stack we extend
    the ``cell`` domain to the active stack thickness, while the volumetric
    heat source and cooling boundary conditions remain uniform.
    """
    x_max = spec.active_stack_thickness
    geometry = {
        "cell": {
            "x": {"min": pybamm.Scalar(0), "max": pybamm.Scalar(x_max)},
            "y": {"min": pybamm.Scalar(0), "max": pybamm.Scalar(spec.width)},
            "z": {"min": pybamm.Scalar(0), "max": pybamm.Scalar(spec.height)},
        },
        "current collector": {"z": {"position": 1}},
    }
    # particle domains are required by the SPM electrochemistry
    for domain, var, radius in (
        ("negative particle", "r_n", "Negative particle radius [m]"),
        ("positive particle", "r_p", "Positive particle radius [m]"),
    ):
        geometry[domain] = {
            var: {"min": pybamm.Scalar(0), "max": pybamm.Parameter(radius)}
        }
    return geometry
