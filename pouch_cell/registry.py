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

# Full list of parameter sets shipped with PyBaMM 26.8 (in display order).
# Chemistries tagged here drive the UI descriptions on the Model page.
PARAMETER_SETS: tuple[str, ...] = (
    "Chen2020", "Marquis2019", "Ecker2015", "Mohtat2020", "OKane2022",
    "ORegan2022", "NCA_Kim2011", "Ai2020", "Prada2013", "Ramadass2004",
    "Xu2019", "Sulzer2019",
    # advanced / specialised (half-cells, composite, MSMR, ECM, Na-ion)
    "Chen2020_composite", "Ecker2015_graphite_halfcell",
    "OKane2022_graphite_SiOx_halfcell", "MSMR_Example", "ECM_Example",
    "Chayambuka2022",
)

# Structured per-set metadata for the parameter-set browser / Help page.
# ``chemistry`` is a short "cathode/anode" tag, ``kind`` is ``"full-cell"`` or
# ``"advanced"`` (half-cell / composite / MSMR / ECM / Na-ion).
PARAMETER_SET_META: dict[str, dict] = {
    "Chen2020": {"chemistry": "NMC111/graphite", "kind": "full-cell",
                 "description": "PyBaMM default; clean, well-tuned full-cell "
                                "dataset used across the docs and tutorials."},
    "Marquis2019": {"chemistry": "NMC/graphite", "kind": "full-cell",
                    "description": "Reduced-parameter SPM-targeted set (from "
                                   "the SEI / degradation review paper)."},
    "Ecker2015": {"chemistry": "NMC/graphite", "kind": "full-cell",
                  "description": "Kokam pouch cell, very detailed experimental "
                                 "fit (impedance-derived); popular Chen2020 "
                                 "alternative."},
    "Mohtat2020": {"chemistry": "NMC/graphite", "kind": "full-cell",
                   "description": "Targeted at cell-level energy/power & "
                                  "lifetime studies with a fast SPM."},
    "OKane2022": {"chemistry": "NMC811/graphite", "kind": "full-cell",
                  "description": "NMC811 + SEI growth + lithium-plating side "
                                 "reactions; ideal for aging-focused runs."},
    "ORegan2022": {"chemistry": "NMC811 + graphite/silicon", "kind": "full-cell",
                   "description": "Closest chemistry match to your NCM 811 "
                                  "design (high-Ni cathode)."},
    "NCA_Kim2011": {"chemistry": "NCA/graphite", "kind": "full-cell",
                    "description": "Classic automotive high-energy dataset."},
    "Ai2020": {"chemistry": "LFP/graphite", "kind": "full-cell",
               "description": "Lithium iron phosphate; flat voltage plateau, "
                              "fast-charge & thermal studies."},
    "Prada2013": {"chemistry": "LCO/LTO", "kind": "full-cell",
                  "description": "Commercial 16 Ah cell; good for low-ESR / "
                                 "high-power comparisons."},
    "Ramadass2004": {"chemistry": "LCO/LiC6 (graphite)", "kind": "full-cell",
                     "description": "Widely-cited early DFN dataset."},
    "Xu2019": {"chemistry": "NMC/Li", "kind": "full-cell",
               "description": "Half-cell-inspired full-cell dataset with "
                              "low-temperature extrapolation; good for "
                              "cold-soak studies."},
    "Sulzer2019": {"chemistry": "NMC/graphite", "kind": "full-cell",
                   "description": "Focus on energy + degradation balance "
                                  "(used with the degradation models)."},
    "Chen2020_composite": {"chemistry": "composite NMC + graphite",
                           "kind": "advanced",
                           "description": "Composite electrode (requires the "
                                          "composite model)."},
    "Ecker2015_graphite_halfcell": {"chemistry": "graphite half-cell",
                                    "kind": "advanced",
                                    "description": "Anode-only half-cell."},
    "OKane2022_graphite_SiOx_halfcell": {"chemistry": "graphite/SiOx half-cell",
                                         "kind": "advanced",
                                         "description": "Half-cell for SEI & "
                                                        "plating studies."},
    "MSMR_Example": {"chemistry": "MSMR", "kind": "advanced",
                     "description": "Multi-Species Multi-Reaction example "
                                    "(requires the MSMR model)."},
    "ECM_Example": {"chemistry": "ECM", "kind": "advanced",
                    "description": "Equivalent-Circuit-Model set (not a "
                                   "physics DFN dataset; for ECM models)."},
    "Chayambuka2022": {"chemistry": "Na-ion", "kind": "advanced",
                       "description": "Sodium-ion chemistry (not lithium) — "
                                      "for comparison runs."},
}

# Backwards-compatible short descriptions (the old info box text).
PARAMETER_SET_INFO: dict[str, str] = {
    k: v["description"] for k, v in PARAMETER_SET_META.items()
}


def parameter_set_meta(name: str) -> dict:
    """Structured metadata for a built-in or user-defined parameter set.

    Custom sets derive their chemistry / kind tag from their base set and use
    the optional user-saved description (see ``config.io``).
    """
    if name in PARAMETER_SET_META:
        return dict(PARAMETER_SET_META[name])
    try:
        from .config.io import is_user_parameter_set, load_user_parameter_set

        if is_user_parameter_set(name):
            uset = load_user_parameter_set(name)
            base = uset.get("base", "")
            base_meta = PARAMETER_SET_META.get(base, {})
            desc = uset.get("description") or (
                f"Custom parameter set based on `{base}` — "
                f"{len(uset.get('overrides') or {})} override(s)."
            )
            return {
                "chemistry": base_meta.get("chemistry", "custom"),
                "kind": base_meta.get("kind", "custom"),
                "description": desc,
            }
    except Exception:  # noqa: BLE001 - never break the UI for this
        pass
    return {"chemistry": "custom", "kind": "custom", "description": ""}

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
    names = list(_REGISTRY.get(category, {}))
    if category == "parameter_set":
        # dynamically include user-saved custom parameter sets (live from disk)
        try:
            from .config.io import list_user_parameter_sets
            for _n in list_user_parameter_sets():
                if _n not in names:
                    names.append(_n)
        except Exception:  # noqa: BLE001 - never break the UI for this
            pass
    return names


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
