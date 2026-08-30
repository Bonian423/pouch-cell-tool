"""``RunConfig`` -- how a simulation is run (model, mesh, SOC, C-rate, ...).

A single serializable dataclass that the CLI, the Streamlit UI and the JSON
presets all read/write.  :meth:`RunConfig.spec` builds the live
:class:`~pouch_cell.config.design.PouchCellSpec` from the ``design`` dict.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields

from .. import registry
from .design import PouchCellSpec


@dataclass
class RunConfig:
    """Everything needed to build and run one simulation.

    ``design`` holds the :class:`PouchCellSpec` fields as a dict (only the
    overrides from the defaults matter, but the UI stores the full asdict).
    """

    # --- design ------------------------------------------------------------
    design: dict = field(default_factory=dict)  # PouchCellSpec fields

    # --- model -------------------------------------------------------------
    model_name: str = "DFN"
    dimensionality: int = 2
    thermal: str = "x-lumped"
    parameter_set: str = "Chen2020"
    mesh: str = "draft"
    solver: str = "default"        # registry: default | idaklu | casadi-*
    full_stack_3d: bool = False

    # --- run ---------------------------------------------------------------
    analysis: str = "discharge"    # registry: discharge | tab
    initial_soc: float = 1.0
    C_rate: float = 1.0
    duration_s: float = 120.0
    cutoff_V: float | None = None  # None -> spec.lower_cutoff_V
    size_to_capacity: bool = True
    particle: str = "uniform profile"  # used by the tab analysis

    # --- thermal -----------------------------------------------------------
    cooling: str | dict | None = None          # preset name or dict overrides
    extra_overrides: dict = field(default_factory=dict)  # raw PyBaMM params

    # --- output ------------------------------------------------------------
    output_variables: list | None = None
    store_first_last: bool = False

    # ------------------------------------------------------------------ #
    def spec(self) -> PouchCellSpec:
        """Build a ``PouchCellSpec`` from the ``design`` dict (defaults + overrides)."""
        base = PouchCellSpec()
        for key, value in self.design.items():
            if key not in {f.name for f in fields(PouchCellSpec)}:
                continue
            setattr(base, key, value)
        return base

    def as_dict(self) -> dict:
        return asdict(self)

    def validate(self) -> None:
        """Raise ``ValueError`` on out-of-range / unknown choices (UI + CLI)."""
        if self.model_name not in registry.options("model"):
            raise ValueError(f"Unknown model '{self.model_name}'.")
        if self.thermal not in registry.options("thermal"):
            raise ValueError(f"Unknown thermal '{self.thermal}'.")
        if self.parameter_set not in registry.options("parameter_set"):
            raise ValueError(f"Unknown parameter set '{self.parameter_set}'.")
        if self.analysis not in registry.options("analysis"):
            raise ValueError(f"Unknown analysis '{self.analysis}'.")
        if not 0.0 <= self.initial_soc <= 1.0:
            raise ValueError("initial_soc must be between 0 and 1.")
        if self.C_rate <= 0:
            raise ValueError("C_rate must be positive.")
        if self.duration_s is not None and self.duration_s <= 0:
            raise ValueError("duration_s must be positive.")
        if self.dimensionality not in (0, 1, 2):
            raise ValueError("dimensionality must be 0, 1 or 2.")
        if self.thermal == "x-lumped" and self.dimensionality == 0:
            raise ValueError("thermal='x-lumped' requires dimensionality >= 1.")
        if self.thermal == "x-full" and self.dimensionality != 0:
            raise ValueError("thermal='x-full' is only valid for dimensionality=0.")
