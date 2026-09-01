"""Constraints -- single source of truth for viable option combinations.

Both the Streamlit UI (filtering dropdowns, disabling irrelevant controls and
auto-correcting invalid combos) and the backend (``RunConfig.validate``) derive
their rules from here, so the CLI, notebooks and UI never disagree about what
is a valid model / dimensionality / thermal / mesh combination.

Guard model (as agreed with the user):

* **filter** -- ``viable_thermal`` / ``viable_mesh`` return only the options
  valid for the current roots, so impossible choices never appear.
* **normalise** -- ``normalise_config`` forces stale stored values to a valid
  default and reports what it corrected (the UI surfaces these in the
  Compatibility panel).
* **block** -- ``constraint_violations`` returns ``blocked`` messages for
  combinations that cannot be auto-corrected (invalid output variables,
  degenerate initial state, broken presets); the UI disables Run for those.
* **disable** -- irrelevant controls (cooling under ``isothermal``, heat pipe
  outside 2+1D ``x-lumped``, outputs under a non-default solver) are disabled
  rather than silently ignored.
"""
from __future__ import annotations

from dataclasses import dataclass

from .. import registry

MESH_DEFAULT_3D = "draft_3d"
MESH_DEFAULT_21D = "draft"

# Parameter sets that cannot build a full-cell 2+1D SPM model (half-cells,
# composite electrodes, MSMR, ECM, Na-ion) -- used by the thermal preview.
_NON_FULL_CELL_HINTS = ("halfcell", "composite", "msmr", "ecm")
_NON_FULL_CELL_NAMES = {"MSMR_Example", "ECM_Example", "Chayambuka2022"}


def is_full_cell_parameter_set(name: str | None) -> bool:
    """True when ``name`` can build a full lithium-ion cell (not half/composite
    /MSMR/ECM/Na-ion)."""
    low = (name or "").lower()
    return not (
        name in _NON_FULL_CELL_NAMES
        or any(hint in low for hint in _NON_FULL_CELL_HINTS)
    )


# --------------------------------------------------------------------------- #
# Viable option lists (filtering)
# --------------------------------------------------------------------------- #
def viable_thermal(dim: int) -> list[str]:
    """Thermal submodels valid for a given dimensionality."""
    if dim == 0:
        return ["isothermal", "lumped", "x-full"]
    return ["isothermal", "lumped", "x-lumped"]


def viable_mesh(model_name: str) -> list[str]:
    """Mesh presets that work with a model (true-3D FEM vs 2+1D)."""
    return registry.options("mesh_3d" if model_name == "SPM_3D" else "mesh_21d")


def mesh_default(model_name: str) -> str:
    """The mesh to fall back to when the current one is invalid."""
    return MESH_DEFAULT_3D if model_name == "SPM_3D" else MESH_DEFAULT_21D


def normalise_config(cfg) -> list[str]:
    """Force a viable (thermal, mesh, particle) combination in place.

    Returns the names of the fields that were corrected.  Call this before
    rendering dependent widgets so a widget's stored value is always a valid
    option (and the underlying config never holds a broken combination).
    Dimensionality / model are treated as the user-driven roots and are never
    auto-corrected here.
    """
    fixed: list[str] = []
    th = viable_thermal(cfg.dimensionality)
    if cfg.thermal not in th:
        cfg.thermal = "lumped"
        fixed.append("thermal")
    meshes = viable_mesh(cfg.model_name)
    if cfg.mesh not in meshes:
        cfg.mesh = mesh_default(cfg.model_name)
        fixed.append("mesh")
    # r=1 meshes (micro/coarse 2+1D) require uniform-profile particles
    if cfg.mesh in ("micro_21d", "coarse_21d") and cfg.particle != "uniform profile":
        cfg.particle = "uniform profile"
        fixed.append("particle")
    return fixed


def validate_structural(cfg) -> None:
    """Raise ``ValueError`` on unknown choices / out-of-range scalars.

    Deliberately *not* combination checks -- those are auto-correctable and
    handled by :func:`normalise_config`.  Used by preset loading (hard error
    only for genuinely broken presets) and by :meth:`RunConfig.validate`
    before the combo checks.
    """
    if cfg.model_name not in registry.options("model"):
        raise ValueError(f"Unknown model '{cfg.model_name}'.")
    if cfg.thermal not in registry.options("thermal"):
        raise ValueError(f"Unknown thermal '{cfg.thermal}'.")
    if cfg.parameter_set not in registry.options("parameter_set"):
        raise ValueError(f"Unknown parameter set '{cfg.parameter_set}'.")
    if cfg.analysis not in registry.options("analysis"):
        raise ValueError(f"Unknown analysis '{cfg.analysis}'.")
    if not 0.0 <= cfg.initial_soc <= 1.0:
        raise ValueError("initial_soc must be between 0 and 1.")
    if cfg.C_rate <= 0:
        raise ValueError("C_rate must be positive.")
    if cfg.duration_s is not None and cfg.duration_s <= 0:
        raise ValueError("duration_s must be positive.")
    if cfg.dimensionality not in (0, 1, 2):
        raise ValueError("dimensionality must be 0, 1 or 2.")


# --------------------------------------------------------------------------- #
# Violations
# --------------------------------------------------------------------------- #
@dataclass
class Violation:
    """One guard message with a severity + the control it targets."""

    kind: str  # "blocked" | "warning" | "info"
    message: str
    control: str | None = None  # widget key / config field, for inline display

    def __str__(self) -> str:
        return self.message


def sanity_check_output_variables(names) -> list[str]:
    """Loose up-front output-variable sanity check; returns problem messages.

    PyBaMM variable names legitimately contain spaces (e.g. ``"Voltage [V]"``,
    ``"X-averaged cell temperature [K]"``), so this loose check only flags
    empty entries and control characters.  Real name verification is the
    strict on-demand model build (``common.check_variable_names``).
    """
    bad: list[str] = []
    for i, name in enumerate(names or []):
        n = (name or "").strip()
        if not n:
            bad.append(f"Output variable #{i + 1} is empty.")
        elif "\t" in n or "\n" in n:
            bad.append(f"Output variable {n!r} contains a tab or newline.")
    return bad


def resolve_effective(cfg, protocol=None) -> dict:
    """The ``(model, dimensionality, thermal, mesh)`` a run will actually use.

    For protocols with ``thermal_maps`` this reflects the forced SPM 2+1D
    x-lumped configuration (see ``experiment._resolve_protocol_model``);
    otherwise it mirrors the config.
    """
    if protocol is None and getattr(cfg, "protocol", None):
        from ..config.protocol import Protocol

        try:
            protocol = Protocol.from_dict(cfg.protocol)
        except Exception:  # noqa: BLE001
            protocol = None
    if protocol is None or not getattr(protocol, "thermal_maps", False):
        return {
            "model": cfg.model_name,
            "dimensionality": cfg.dimensionality,
            "thermal": cfg.thermal,
            "mesh": cfg.mesh,
        }
    from .experiment import _resolve_protocol_model

    model, dim, thermal, mesh = _resolve_protocol_model(cfg, protocol)
    return {
        "model": model,
        "dimensionality": dim,
        "thermal": thermal,
        "mesh": mesh if isinstance(mesh, str) else str(mesh),
    }


# Maximum unrolled steps per cycle before we warn about a runaway loop.
MAX_EXPANDED_STEPS = 200


def protocol_violations(proto, cfg) -> list[Violation]:
    """Guard messages specific to a multi-step :class:`Protocol` (conditions +
    loops + temperature source / stop)."""
    vios: list[Violation] = []
    steps = getattr(proto, "steps", None) or []
    if not steps:
        return vios
    eff = resolve_effective(cfg, proto)
    isothermal = eff["thermal"] == "isothermal"
    src = getattr(proto, "temperature_source", "volume_averaged")

    # --- temperature source: hot-spot needs a 2+1D x-lumped solve ----------
    if src == "hot_spot" and not (
        eff["dimensionality"] == 2 and eff["thermal"] == "x-lumped"
    ):
        vios.append(Violation(
            "blocked",
            "Temperature source **hot-spot** needs a 2+1D `x-lumped` solve — "
            "use Volume-averaged, or change the model/thermal.",
            control="temperature_source",
        ))

    for i, s in enumerate(steps):
        conds = list(getattr(s, "terminations", None) or [])
        if not conds:
            vios.append(Violation(
                "blocked",
                f"Step {i + 1} has no end condition — add a duration or cut-off.",
                control=f"step_{i}",
            ))
        for c in conds:
            if (c or {}).get("type") == "temperature" and isothermal:
                vios.append(Violation(
                    "blocked",
                    f"Step {i + 1}: a temperature condition needs a "
                    "non-isothermal thermal model.",
                    control=f"step_{i}",
                ))
        if s.loop_to is not None:
            if not 0 <= int(s.loop_to) < i:
                vios.append(Violation(
                    "blocked",
                    f"Step {i + 1}: loop target must be an earlier step "
                    f"(0..{i - 1}).",
                    control=f"step_{i}",
                ))
            if int(s.loop_count or 1) < 1:
                vios.append(Violation(
                    "warning",
                    f"Step {i + 1}: loop repeat count must be ≥ 1.",
                    control=f"step_{i}",
                ))

    # --- run-level temperature stop needs a non-isothermal thermal ---------
    if getattr(proto, "temperature_stop", None) is not None and isothermal:
        vios.append(Violation(
            "blocked",
            "Run-level temperature stop needs a non-isothermal thermal model.",
            control="temperature_stop",
        ))

    # --- runaway-loop guard -------------------------------------------------
    try:
        n = proto.expanded_step_count()
    except Exception:  # noqa: BLE001 - treat as raw count on error
        n = len(steps)
    if n > MAX_EXPANDED_STEPS:
        vios.append(Violation(
            "warning",
            f"Loops unroll to **{n} steps per cycle** — expect a long solve. "
            "Consider fewer repeats.",
            control="cycles",
        ))
    return vios


def constraint_violations(cfg, *, protocol=None, spec=None, cooling=None,
                          preview=False) -> list[Violation]:
    """All guard messages for the current UI state.

    ``cfg`` is a :class:`~pouch_cell.config.run.RunConfig`; ``protocol`` an
    optional :class:`~pouch_cell.config.protocol.Protocol` (falls back to
    ``cfg.protocol``); ``spec`` an optional :class:`PouchCellSpec` (heat pipe +
    cut-offs); ``cooling`` the thermal page's cooling value; ``preview`` adds
    thermal-preview-only checks.
    """
    vios: list[Violation] = []
    model = cfg.model_name
    dim = cfg.dimensionality
    thermal = cfg.thermal
    solver = cfg.solver

    # --- true-3D model ignores dimensionality/thermal (dead controls) ------
    if model == "SPM_3D":
        vios.append(Violation(
            "info",
            "SPM_3D is true-3D FEM — dimensionality and thermal are fixed "
            "(controls hidden).",
        ))

    # --- thermal vs dimensionality (should be prevented by filtering) ------
    if thermal not in viable_thermal(dim):
        vios.append(Violation(
            "blocked",
            f"thermal='{thermal}' is not valid for dimensionality={dim}. "
            "Pick a valid thermal model or dimensionality.",
            control="thermal",
        ))

    # --- user-defined cooling geometry needs 2+1D x-lumped -----------------
    regions = list(getattr(spec, "cooling_regions", None) or [])
    if regions and not (dim == 2 and thermal == "x-lumped"):
        vios.append(Violation(
            "warning",
            "Custom cooling geometry only applies in 2+1D `x-lumped` solves — "
            "it will be ignored with the current model/dim/thermal.",
            control="cooling_regions",
        ))

    # --- cooling is irrelevant under isothermal ----------------------------
    if thermal == "isothermal" and cooling:
        vios.append(Violation(
            "warning",
            "Cooling has no effect with the `isothermal` thermal model — it "
            "is ignored.",
            control="cooling",
        ))

    # --- non-default solver silently drops outputs / store-first-last ------
    if solver not in (None, "default") and (
        cfg.output_variables or cfg.store_first_last
    ):
        vios.append(Violation(
            "warning",
            f"Output variables / store-first-last are ignored with solver "
            f"`{solver}` — they only apply with the default solver.",
            control="output_variables",
        ))

    # --- output-variable sanity (loose, up-front) --------------------------
    bad_ov = sanity_check_output_variables(cfg.output_variables)
    if bad_ov:
        vios.append(Violation(
            "blocked",
            "Invalid output variables: " + " ".join(bad_ov),
            control="output_variables",
        ))

    # --- thermal maps: effective combo (readout, not a blocker) ------------
    proto = protocol
    if proto is None and getattr(cfg, "protocol", None):
        from ..config.protocol import Protocol

        try:
            proto = Protocol.from_dict(cfg.protocol)
        except Exception:  # noqa: BLE001
            proto = None
    if proto is not None and getattr(proto, "thermal_maps", False):
        eff = resolve_effective(cfg, proto)
        vios.append(Violation(
            "info",
            f"Thermal maps will run as **SPM · 2+1D · x-lumped** "
            f"(mesh `{eff['mesh']}`) — your model/dim/thermal are overridden "
            "for this protocol run.",
        ))

    # --- protocol-specific guards (conditions + loops) ---------------------
    if proto is not None and getattr(proto, "steps", None):
        vios.extend(protocol_violations(proto, cfg))

    # --- degenerate initial state (hard block) -----------------------------
    iv = cfg.initial_voltage
    if iv is not None:
        lower = cfg.cutoff_V
        if lower is None:
            lower = getattr(spec, "lower_cutoff_V", None)
        upper = getattr(spec, "upper_cutoff_V", None)
        if lower is not None and iv <= lower:
            vios.append(Violation(
                "blocked",
                f"Initial voltage {iv:.2f} V is at/below the {lower:.2f} V "
                "cut-off — the solver cannot start.",
                control="initial_voltage",
            ))
        elif upper is not None and iv >= upper:
            vios.append(Violation(
                "blocked",
                f"Initial voltage {iv:.2f} V is at/above the {upper:.2f} V "
                "upper cut-off.",
                control="initial_voltage",
            ))

    # --- thermal preview needs a full-cell parameter set -------------------
    if preview and not is_full_cell_parameter_set(cfg.parameter_set):
        vios.append(Violation(
            "blocked",
            "This parameter set isn't a full lithium-ion cell set "
            "(half-cell / composite / MSMR / ECM / Na-ion) — the thermal "
            "preview needs a full-cell set.",
            control="parameter_set",
        ))

    return vios
