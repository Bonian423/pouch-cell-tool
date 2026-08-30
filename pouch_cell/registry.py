"""Registries -- the single source of truth for every pluggable option.

Adding a new model, thermal submodel, cooling preset, mesh preset, parameter
set or analysis **here** automatically exposes it to the CLI ``--choices``,
the Streamlit UI dropdowns and preset validation -- no other code needs to
change (the plugin pattern).

The UI and CLI derive their option lists from :func:`options`; extension
code can add entries with :func:`register` (or the ``@register`` decorator).
"""
from __future__ import annotations

# --- models -----------------------------------------------------------------
MODEL_NAMES: tuple[str, ...] = ("SPM", "SPMe", "DFN", "SPM_3D")
THERMAL_OPTIONS: tuple[str, ...] = ("isothermal", "lumped", "x-lumped", "x-full")
PARAMETER_SETS: tuple[str, ...] = ("Chen2020", "OKane2022")
ANALYSES: tuple[str, ...] = ("discharge", "tab")
SOLVERS: tuple[str, ...] = ("default", "idaklu", "casadi-fast", "casadi-safe")

# Cooling presets -> uniform surface heat-transfer coefficient (W/m^2/K).
# Newton's law: Q_diss = h * A * (T - T_amb); raising h models active cooling
# (fan / forced convection ~20-100, liquid cold plate ~500+).
COOLING_PRESETS: dict[str, float] = {
    "natural": 5.0,              # free convection in air (tool default)
    "forced_air": 50.0,          # fan / forced convection
    "fan": 50.0,                 # alias
    "liquid_cold_plate": 500.0,  # liquid cold plate / active liquid cooling
    "cold_plate": 500.0,         # alias
}

# Short alias -> PyBaMM per-face heat-transfer coefficient parameter.
FACE_ALIASES: dict[str, str] = {
    "left": "Left face heat transfer coefficient [W.m-2.K-1]",
    "right": "Right face heat transfer coefficient [W.m-2.K-1]",
    "front": "Front face heat transfer coefficient [W.m-2.K-1]",
    "back": "Back face heat transfer coefficient [W.m-2.K-1]",
    "bottom": "Bottom face heat transfer coefficient [W.m-2.K-1]",
    "top": "Top face heat transfer coefficient [W.m-2.K-1]",
}

# Mesh presets -> var_pts / FEM element size.
# The 2+1D presets are 2x mesh density (user request).  The true-3D FEM presets
# are NOT doubled: at h=0.0025 the SPM_3D solve is intractable in PyBaMM 26.8
# (a 15 s discharge took >18 min wall -- ~60-90 s per simulated second).  Pass
# a custom element size (e.g. mesh=0.0025) for finer 3D FEM if you can wait.
MESH_PRESETS: dict[str, dict | float] = {
    # 2+1D models: var_pts for the through-plane (x), particle (r) and
    # current-collector (y, z) coordinates -- 2x mesh density
    "draft": {"x_n": 8, "x_s": 8, "x_p": 8, "r_n": 12, "r_p": 12, "y": 24, "z": 36},
    "standard": {"x_n": 16, "x_s": 16, "x_p": 16, "r_n": 20, "r_p": 20, "y": 40, "z": 60},
    "fine": {"x_n": 24, "x_s": 24, "x_p": 24, "r_n": 30, "r_p": 30, "y": 64, "z": 96},
    # coarse 2+1D preset -- used for the (slow) DFN/SPMe tab analysis; r points
    # are dropped because tab_heating_analysis uses uniform-profile particles
    "coarse_21d": {"x_n": 8, "x_s": 8, "x_p": 8, "r_n": 1, "r_p": 1, "y": 16, "z": 24},
    # smallest 2+1D preset -- the DFN/SPMe 2+1D DAE is limited: it completes at
    # 1-5 s of discharge but hits IDA_ERR_FAIL (minimum step size) beyond ~10 s
    # even here
    "micro_21d": {"x_n": 6, "x_s": 6, "x_p": 6, "r_n": 1, "r_p": 1, "y": 12, "z": 18},
    # true-3D model: FEM characteristic element size (m)
    "draft_3d": 0.005,
    "standard_3d": 0.003,
    "fine_3d": 0.002,
}

# --------------------------------------------------------------------------- #
# Mutable registry (seeded from the constants above; extend via register())
# --------------------------------------------------------------------------- #
_REGISTRY: dict[str, dict] = {
    "model": {m: m for m in MODEL_NAMES},
    "thermal": {t: t for t in THERMAL_OPTIONS},
    "parameter_set": {p: p for p in PARAMETER_SETS},
    "analysis": {a: a for a in ANALYSES},
    "solver": {s: s for s in SOLVERS},
    "cooling": dict(COOLING_PRESETS),
    "mesh_21d": {k: v for k, v in MESH_PRESETS.items() if not k.endswith("_3d")},
    "mesh_3d": {k: v for k, v in MESH_PRESETS.items() if k.endswith("_3d")},
}


def options(category: str) -> list[str]:
    """List the registered option names for ``category`` (e.g. 'model')."""
    return list(_REGISTRY.get(category, {}))


def get(category: str, name: str, default=None):
    """Look up the value registered for ``(category, name)`` (default: ``name``)."""
    return _REGISTRY.get(category, {}).get(name, default if default is not None else name)


def register(category: str, name: str, value=None) -> None:
    """Register a new option so UI dropdowns / CLI choices pick it up."""
    _REGISTRY.setdefault(category, {})[name] = (
        value if value is not None else name
    )


def register_decorator(category: str, name: str | None = None):
    """Decorator form: ``@register('cooling', 'my_preset')`` on a value/function."""

    def _wrap(value):
        register(category, name or value.__name__, value)
        return value

    return _wrap


# Backwards-compatible private aliases (older code referenced the underscore
# names inside pouch_cell; kept so nothing external breaks).
_MESH_PRESETS = MESH_PRESETS
_COOLING_PRESETS = COOLING_PRESETS
_FACE_ALIASES = FACE_ALIASES
