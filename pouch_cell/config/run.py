"""``RunConfig`` -- how a simulation is run (model, mesh, SOC, C-rate, ...).

A single serializable dataclass that the CLI, the Streamlit UI and the JSON
presets all read/write.  :meth:`RunConfig.spec` builds the live
:class:`~pouch_cell.config.design.PouchCellSpec` from the ``design`` dict.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

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
    analysis: str = "discharge"    # registry: discharge | tab (legacy single-run)
    protocol: dict | None = None   # serialized Protocol (takes precedence)
    initial_soc: float = 1.0
    initial_voltage: float | None = None  # V-based init; overrides initial_soc
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
        """Build a ``PouchCellSpec`` from the ``design`` dict (defaults +
        overrides, legacy heat-pipe migrated)."""
        return PouchCellSpec.from_dict(self.design)

    def as_dict(self) -> dict:
        return asdict(self)

    def validate(self) -> None:
        """Raise ``ValueError`` on out-of-range / unknown choices (UI + CLI).

        Structural checks (unknown names, out-of-range scalars) come from
        :func:`pouch_cell.core.constraints.validate_structural`; combination
        checks come from ``constraint_violations`` -- both live in the single
        source of truth shared with the UI, so CLI / notebooks / UI can never
        disagree about what is valid.
        """
        from ..core.constraints import constraint_violations, validate_structural

        validate_structural(self)
        for v in constraint_violations(self):
            if v.kind == "blocked":
                raise ValueError(v.message)
