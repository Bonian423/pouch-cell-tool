"""Shared PyBaMM-parameter helpers for the UI (Design + Thermal pages).

These helpers talk to a live ``pybamm.ParameterValues`` for the selected
parameter set so the UI can offer:

* a *curated* list of industrially-measurable knobs (porosity, particle
  radius, Bruggeman, ...) with friendly labels,
* a *searchable full table* of every parameter in the set (numeric cells
  editable -> written into ``extra_overrides``; function-valued read-only),
* copy-ready *example* override snippets,
* a quick in-tab 2+1D thermal-map preview.

The pybamm import is deliberately lazy (a few seconds on first call) and
only happens on the pages that need it.
"""
from __future__ import annotations

import json
from pathlib import Path

# --------------------------------------------------------------------------- #
# Parameter introspection
# --------------------------------------------------------------------------- #
def load_pv(set_name: str):
    """Return the ``pybamm.ParameterValues`` for ``set_name`` (lazy import)."""
    import pybamm

    return pybamm.ParameterValues(set_name)


def _to_scalar(v):
    """Try to turn a parameter value into a plain float/str (else None)."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    import numpy as np

    if isinstance(v, (np.integer, np.floating)):
        return float(v)
    if isinstance(v, str):
        # a plain string parameter (e.g. 'Negative electrode' / "1+0.2" expr)
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    return None


def list_parameters(set_name: str, overrides: dict | None = None) -> list[dict]:
    """Return ``[{name, value, numeric, current}]`` for a parameter set.

    ``overrides`` (e.g. ``config.extra_overrides``) wins on the *current*
    value so the table reflects live edits.
    """
    pv = load_pv(set_name)
    overrides = overrides or {}
    rows: list[dict] = []
    try:
        items = list(pv.items())
    except Exception:  # noqa: BLE001 - exotic values
        items = []
    for name, value in items:
        num = _to_scalar(value)
        current = overrides.get(name, num)
        rows.append(
            {
                "name": name,
                "value": num,           # base-set numeric value (None if not numeric)
                "numeric": num is not None,
                "current": _to_scalar(current) if current is not None else None,
                "overridden": name in overrides,
            }
        )
    rows.sort(key=lambda r: (not r["numeric"], r["name"].lower()))
    return rows


# --------------------------------------------------------------------------- #
# Curated knobs (industrially measurable / tweakable)
# --------------------------------------------------------------------------- #
# (ui label, pybamm parameter name, unit, step, min, max) -- min/max in base units
CURATED_PARAMS: list[tuple[str, str, str, float, float, float]] = [
    ("Neg electrode porosity", "Negative electrode porosity", "—", 0.01, 0.1, 0.6),
    ("Pos electrode porosity", "Positive electrode porosity", "—", 0.01, 0.1, 0.6),
    ("Separator porosity", "Separator porosity", "—", 0.01, 0.1, 0.9),
    ("Neg electrode Bruggeman", "Negative electrode Bruggeman coefficient", "—", 0.05, 0.5, 2.5),
    ("Pos electrode Bruggeman", "Positive electrode Bruggeman coefficient", "—", 0.05, 0.5, 2.5),
    ("Neg particle radius", "Negative electrode particle radius [m]", "µm", 0.1, 0.1, 20.0),
    ("Pos particle radius", "Positive electrode particle radius [m]", "µm", 0.1, 0.1, 20.0),
    ("Neg max concentration", "Maximum concentration in negative electrode [mol.m-3]",
     "mol/m³", 50.0, 1e3, 6e4),
    ("Pos max concentration", "Maximum concentration in positive electrode [mol.m-3]",
     "mol/m³", 50.0, 1e3, 6e4),
    ("Initial electrolyte concentration",
     "Initial concentration in electrolyte [mol.m-3]", "mol/m³", 10.0, 100.0, 5000.0),
    ("Cation transference number", "Cation transference number", "—", 0.01, 0.1, 0.9),
    ("Neg active-material fraction",
     "Negative electrode active material volume fraction", "—", 0.01, 0.1, 0.95),
    ("Pos active-material fraction",
     "Positive electrode active material volume fraction", "—", 0.01, 0.1, 0.95),
    ("Neg electrode conductivity",
     "Negative electrode conductivity [S.m-1]", "S/m", 10.0, 1.0, 5000.0),
    ("Pos electrode conductivity",
     "Positive electrode conductivity [S.m-1]", "S/m", 10.0, 1.0, 5000.0),
    ("Neg collector conductivity",
     "Negative current collector conductivity [S.m-1]", "S/m", 10.0, 1.0, 1e6),
    ("Pos collector conductivity",
     "Positive current collector conductivity [S.m-1]", "S/m", 10.0, 1.0, 1e6),
    ("Neg electrode density",
     "Negative electrode density [kg.m-3]", "kg/m³", 10.0, 500.0, 20000.0),
    ("Pos electrode density",
     "Positive electrode density [kg.m-3]", "kg/m³", 10.0, 500.0, 20000.0),
]

# Thermal-focussed curated params (shown on the Thermal page).
CURATED_THERMAL_PARAMS: list[tuple[str, str, str, float, float, float]] = [
    ("Ambient temperature", "Ambient temperature [K]", "K", 0.5, 250.0, 350.0),
    ("Initial temperature", "Initial temperature [K]", "K", 0.5, 250.0, 350.0),
    ("Heat-transfer coefficient",
     "heat_transfer_coefficient_W_m2K", "W/m²/K", 5.0, 0.0, 5000.0),
    ("Neg electrode thermal conductivity",
     "Negative electrode thermal conductivity [W.m-1.K-1]", "W/m/K", 0.1, 0.1, 100.0),
    ("Pos electrode thermal conductivity",
     "Positive electrode thermal conductivity [W.m-1.K-1]", "W/m/K", 0.1, 0.1, 100.0),
    ("Separator thermal conductivity",
     "Separator thermal conductivity [W.m-1.K-1]", "W/m/K", 0.1, 0.1, 100.0),
    ("Neg collector thermal conductivity",
     "Negative current collector thermal conductivity [W.m-1.K-1]", "W/m/K", 1.0, 1.0, 1000.0),
    ("Pos collector thermal conductivity",
     "Positive current collector thermal conductivity [W.m-1.K-1]", "W/m/K", 1.0, 1.0, 1000.0),
    ("Specific heat capacity",
     "Specific heat capacity [J.kg-1.K-1]", "J/kg/K", 50.0, 100.0, 5000.0),
]


def curated_defaults(set_name: str, overrides: dict | None = None) -> dict[str, float]:
    """Base-set numeric values for every curated parameter name."""
    pv = load_pv(set_name)
    overrides = overrides or {}
    out: dict[str, float] = {}
    for _label, name, _unit, _step, _lo, _hi in CURATED_PARAMS:
        try:
            base = pv[name]
        except KeyError:
            continue
        num = _to_scalar(base)
        if num is None:
            continue
        out[name] = float(overrides.get(name, num))
    return out


def scale_label(name: str, unit: str) -> float:
    """Return the scale to display a parameter in its preferred unit."""
    if unit == "µm":
        return 1e6
    return 1.0


# --------------------------------------------------------------------------- #
# Copy-ready example overrides
# --------------------------------------------------------------------------- #
EXAMPLE_OVERRIDES: list[tuple[str, dict]] = [
    (
        "Faster charging (reduce internal resistance)",
        {
            "Negative electrode Bruggeman coefficient": 1.5,
            "Positive electrode Bruggeman coefficient": 1.5,
            "Negative electrode conductivity [S.m-1]": 500.0,
            "Positive electrode conductivity [S.m-1]": 100.0,
        },
    ),
    (
        "More conductive electrolyte (cold-friendly)",
        {
            "Initial concentration in electrolyte [mol.m-3]": 1200.0,
            "Cation transference number": 0.4,
        },
    ),
    (
        "Cooler ambient (288 K = 15 °C)",
        {
            "Ambient temperature [K]": 288.15,
            "Initial temperature [K]": 288.15,
        },
    ),
    (
        "Reduced SEI growth (OKane2022 aging)",
        {
            "SEI kinetic rate constant [m.s-1]": 1e-14,
            "SEI open-circuit potential [V]": 0.4,
        },
    ),
]


# --------------------------------------------------------------------------- #
# Thermal-map preview (quick 2+1D solve, shown in-tab)
# --------------------------------------------------------------------------- #
QUICK_MAP_DIR = Path(__file__).resolve().parents[2] / "pouch_output" / "quick_maps"


def quick_thermal_preview(spec, config, thermal) -> dict:
    """Run a fast SPM 2+1D micro_21d solve and save thermal maps.

    Returns a dict ``{"ok": bool, "figure": str|None, "error": str|None,
    "metrics": dict}``.  The figure path is a PNG the page can ``st.image``.
    """
    import matplotlib.pyplot as plt
    import pybamm

    from .. import plotting
    from ..core.experiment import collect_metrics
    from ..core.simulation import PouchCellSimulation
    from ..core.solvers import make_solver

    QUICK_MAP_DIR.mkdir(parents=True, exist_ok=True)
    try:
        sim = PouchCellSimulation(
            spec=spec,
            model_name="SPM",
            dimensionality=2,
            thermal="x-lumped",
            parameter_set=config.parameter_set,
            initial_soc=config.initial_soc,
            mesh="micro_21d",
            solver=make_solver("default"),
            cooling=thermal.to_cooling(),
            size_to_capacity=config.size_to_capacity,
            particle="uniform profile",
        )
        if config.extra_overrides:
            sim.param.update(config.extra_overrides)
        sol = sim.discharge(C_rate=config.C_rate, duration_s=5.0)
        metrics = collect_metrics(sim, sol, config)
        fig = plotting.plot_tab_heating(sol, spec, param=sim.param)
        path = QUICK_MAP_DIR / "thermal_preview.png"
        fig.savefig(path, dpi=110, bbox_inches="tight")
        plt.close(fig)
        return {"ok": True, "figure": str(path), "error": None, "metrics": metrics}
    except Exception as err:  # noqa: BLE001
        return {"ok": False, "figure": None, "error": repr(err), "metrics": {}}


def example_json(name: str) -> str:
    """Pretty JSON for one of the copy-ready examples."""
    for label, d in EXAMPLE_OVERRIDES:
        if label == name:
            return json.dumps(d, indent=2)
    return "{}"


# --------------------------------------------------------------------------- #
# Streamlit render helpers (shared by Design + Thermal pages)
# --------------------------------------------------------------------------- #
def _base_key(set_name: str) -> str:
    return f"pvb_{set_name}"


def _rows_key(set_name: str) -> str:
    return f"pvr_{set_name}"


def render_curated_editors(
    set_name: str,
    overrides: dict,
    curated: list = CURATED_PARAMS,
    section_title: str = "Curated parameters",
) -> None:
    """Render one number input per curated parameter; write edits to ``overrides``."""
    import streamlit as st

    st.markdown(f"**{section_title}**")
    base = st.session_state.get(_base_key(set_name))
    if base is None:
        base = curated_defaults(set_name, {})
        st.session_state[_base_key(set_name)] = base
    shown = 0
    for i, (label, name, unit, step, lo, hi) in enumerate(curated):
        if name not in base:
            continue
        cur = float(overrides.get(name, base[name]))
        scale = 1e6 if unit == "µm" else 1.0
        v = min(max(cur * scale, lo * scale), hi * scale)
        new = st.number_input(
            f"{label} ({unit})",
            min_value=lo * scale, max_value=hi * scale,
            value=v, step=step * scale, key=f"cur_{i}_{set_name}",
            format="%g",
        )
        if abs(new / scale - cur) > 1e-9:
            overrides[name] = new / scale
        shown += 1
    if shown == 0:
        st.caption("No curated parameters found for this parameter set.")


def render_param_table(set_name: str, overrides: dict) -> None:
    """Searchable full parameter table + targeted numeric edit (last section)."""
    import pandas as pd
    import streamlit as st

    st.markdown("**Full parameter table** (reference + targeted edits)")
    rows = st.session_state.get(_rows_key(set_name))
    if rows is None:
        rows = list_parameters(set_name, {})
        st.session_state[_rows_key(set_name)] = rows

    filt = st.text_input("Filter parameter names", key=f"ptab_f_{set_name}")
    matches = [r for r in rows if filt.lower() in r["name"].lower()]
    editable = [r for r in matches if r["numeric"]]
    st.caption(f"{len(matches)} parameter(s) match · {len(editable)} numeric/editable")

    df = pd.DataFrame(
        [
            {
                "Parameter": r["name"],
                "Value (base set)": r["value"],
                "Type": "editable" if r["numeric"] else "read-only",
            }
            for r in matches[:500]
        ]
    )
    st.dataframe(df, width="stretch", hide_index=True)

    sel = st.selectbox(
        "Edit a numeric parameter",
        ["— select —"] + [r["name"] for r in editable],
        key=f"ptab_sel_{set_name}",
    )
    if sel != "— select —":
        cur = float(overrides.get(sel, next(r["value"] for r in editable if r["name"] == sel)))
        new = st.number_input(
            f"Value of `{sel}`", value=cur, format="%g", key=f"ptab_v_{sel}",
        )
        if new != cur:
            overrides[sel] = new
        if sel in overrides and st.button(
            f"Clear override: `{sel}`", key=f"ptab_c_{sel}"
        ):
            overrides.pop(sel, None)
            st.rerun()
