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

import streamlit as st  # noqa: E402  (module-level: used by @st.dialog etc.)

# --------------------------------------------------------------------------- #
# Parameter introspection
# --------------------------------------------------------------------------- #
def load_pv(set_name: str):
    """Return the ``pybamm.ParameterValues`` for ``set_name`` (lazy import).

    A saved custom parameter set is resolved to its base set + overrides so the
    table / curated knobs reflect the live edited values.
    """
    import pybamm

    from ..config.io import resolve_parameter_set
    from ..core.parameters import apply_parameter_overrides

    base, overrides = resolve_parameter_set(set_name)
    pv = pybamm.ParameterValues(base)
    if overrides:
        apply_parameter_overrides(pv, overrides)
    return pv


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

# Coarse 2+1D mesh used ONLY for the in-tab quick preview: r=1 is required for
# the 2+1D thermal submodel (with "uniform profile" particles), and the reduced
# y/z plane makes a preview solve run in seconds instead of minutes. The full
# run keeps using the normal micro_21d / draft meshes.
PREVIEW_MESH = {"x_n": 4, "x_s": 4, "x_p": 4, "r_n": 1, "r_p": 1, "y": 8, "z": 12}


def _friendly_preview_error(err) -> str:
    """Turn a raw PyBaMM exception into an actionable one-liner."""
    msg = repr(err)
    if "EmptySolution" in msg or "not subscriptable" in msg:
        return (
            "The solver returned an empty solution — the preview step is "
            "infeasible from the current initial state (e.g. charging from a "
            "nearly-full or degenerate state, or an override pushing the OCP "
            "out of range). Lower the C-rate, adjust the Initial SOC / "
            "voltage, or reset the parameter overrides."
        )
    if (("infeasible" in msg and "exceeded bounds at initial conditions" in msg)
            or "skip_ok is True" in msg):
        return (
            "The protocol steps are infeasible from the initial state — the "
            "start voltage/SOC is inconsistent with the step directions and "
            "cut-offs. Lower the C-rate, adjust the Initial SOC / initial "
            "voltage, or reset the parameter overrides."
        )
    if "Parameter" in msg and "not found" in msg:
        return (
            "This parameter set isn't a full lithium-ion cell set "
            "(half-cell / composite / MSMR / ECM / Na-ion), so it can't build a "
            "2+1D SPM thermal map. Pick a full-cell set on the Model & Run page "
            "(e.g. Chen2020, OKane2022, ORegan2022)."
        )
    if "initial condition is outside of variable bounds" in msg:
        return (
            "The initial cell state is outside physical bounds — check Initial "
            "SOC and any parameter overrides (porosity, concentrations, radii)."
        )
    if "Maximum voltage" in msg and "initial conditions" in msg:
        return (
            "The cell's initial voltage is already ABOVE the upper cut-off "
            "(4.2 V) — usually an override pushing the OCP up, or charging from "
            "a high SOC at high C-rate. Lower the Initial SOC / C-rate or reset "
            "the overrides."
        )
    if ("non-positive at initial conditions" in msg
            or "Minimum voltage" in msg
            or "IDA_CONV_FAIL" in msg
            or "CONV_FAIL" in msg):
        return (
            "The cell's initial state is degenerate: the initial voltage is at "
            "or far below the discharge cut-off (2.5 V), so the solver can't "
            "start. This usually means a parameter override set an electrode "
            "concentration / OCP out of range, or the Initial SOC is too low. "
            "Reset the overrides (Design → parameter table, or Thermal → raw "
            "overrides) and set Initial SOC back up, then retry."
        )
    return msg


def _preview_voltage_warning(sol, spec) -> str | None:
    """Return a warning when the preview's end-state voltage looks unphysical.

    The 2+1D SPM includes current-collector resistance, so an aggressive step
    (e.g. a 3 C charge from a high SOC) can push the terminal voltage far above
    the 4.2 V upper cut-off and the solver stops early. The temperature map is
    still meaningful up to the last good state, so we show it but flag the
    voltage so the caption doesn't present a nonsense number.
    """
    import numpy as np

    try:
        V = float(np.asarray(sol["Voltage [V]"].entries)[-1])
    except Exception:  # noqa: BLE001
        return None
    if V > spec.upper_cutoff_V + 0.4:
        return (
            f"End-state voltage {V:.2f} V is well above the "
            f"{spec.upper_cutoff_V:.1f} V upper cut-off — the preview step drove "
            "the 2+1D terminal voltage into a high over-potential regime (large "
            "tab current). The map shows the last good state; try a lower "
            "C-rate, a shorter step, or a lower Initial SOC."
        )
    if V < spec.lower_cutoff_V - 0.2:
        return (
            f"End-state voltage {V:.2f} V is near/below the "
            f"{spec.lower_cutoff_V:.1f} V cut-off — the cell is deeply "
            "discharged at this preview point."
        )
    return None


def quick_thermal_preview(
    spec,
    config,
    thermal,
    steps: list | None = None,
    step_idx: int | None = None,
) -> dict:
    """Run a fast SPM 2+1D micro_21d solve and save thermal maps.

    By default it is a fresh 5-second 1C discharge.  If ``steps`` (a list of
    :class:`~pouch_cell.config.protocol.Step`) and ``step_idx`` are given, it
    instead runs the protocol up to the *end* of ``steps[step_idx]`` and draws
    the map at that point (so the preview is "stationed on" a chosen step).

    Returns a dict ``{"ok": bool, "figure": str|None, "error": str|None,
    "note": str, "metrics": dict}``.  The figure path is a PNG the page can
    ``st.image``.

    Degenerate initial states (initial voltage at/below the discharge cut-off,
    usually from a bad parameter override or a low Initial SOC) and
    non-full-cell parameter sets return a human-readable ``error`` instead of
    a raw PyBaMM traceback.
    """
    import matplotlib.pyplot as plt
    import pybamm

    from .. import plotting
    from ..config.protocol import Protocol
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
            initial_voltage=config.initial_voltage,
            mesh=PREVIEW_MESH,          # coarse -> preview runs in seconds
            solver=make_solver("default"),
            cooling=thermal.to_cooling(),
            size_to_capacity=False,     # skip the expensive full-build sizing
            particle="uniform profile",
        )
        # fold in BOTH override sources (Design-page electrochemistry overrides
        # and this page's raw overrides) -- previously only the Design ones
        # reached the preview.
        overrides = dict(config.extra_overrides or {})
        overrides.update(thermal.extra_overrides or {})
        if overrides:
            from ..core.parameters import apply_parameter_overrides
            apply_parameter_overrides(sim.param, overrides)
        if steps and step_idx is not None:
            proto = Protocol(type="custom", steps=list(steps[: step_idx + 1]),
                             thermal_maps=False)
            exp = pybamm.Experiment(
                proto.experiment_cycles(spec.capacity_Ah), period=None
            )
            sol = sim.run_experiment_obj(exp)
            note = f"after step {step_idx + 1} ({len(steps)}-step protocol)"
        else:
            sol = sim.discharge(C_rate=config.C_rate, duration_s=5.0)
            note = "fresh 5 s discharge"
        if isinstance(sol, pybamm.EmptySolution) or getattr(sol, "is_empty", False):
            return {"ok": False, "figure": None,
                    "error": (
                        "The solver returned an empty solution — the preview "
                        "step is infeasible from the current initial state "
                        "(e.g. charging from a nearly-full or degenerate "
                        "state, or an override pushing the OCP out of range). "
                        "Lower the C-rate, adjust the Initial SOC / voltage, or "
                        "reset the parameter overrides."
                    ),
                    "metrics": {}, "note": note, "warning": None}
        metrics = collect_metrics(sim, sol, config, spec=spec)
        warning = _preview_voltage_warning(sol, spec)
        fig = plotting.plot_tab_heating(sol, spec, param=sim.param)
        path = QUICK_MAP_DIR / "thermal_preview.png"
        fig.savefig(path, dpi=110, bbox_inches="tight")
        plt.close(fig)
        return {"ok": True, "figure": str(path), "error": None,
                "note": note, "warning": warning, "metrics": metrics}
    except Exception as err:  # noqa: BLE001
        return {"ok": False, "figure": None,
                "error": _friendly_preview_error(err), "metrics": {},
                "note": "", "warning": None}


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


def _sample_function_table(
    set_name: str, param_name: str, x0: float, x1: float, n: int
):
    """Sample a function-valued parameter into an ``(x, y)`` DataFrame.

    Used to pre-fill the function-table editor: the current (base-set) function
    is evaluated at ``n`` evenly spaced points over ``[x0, x1]`` so the user can
    tweak the values (or the domain and re-sample).
    """
    import numpy as np
    import pandas as pd
    import pybamm

    from ..config.io import resolve_parameter_set

    base_name, _ = resolve_parameter_set(set_name)
    pv = pybamm.ParameterValues(base_name)
    xs = np.linspace(float(x0), float(x1), max(3, int(n)))
    try:
        fn = pv[param_name]
        ys = [float(fn(x)) for x in xs]
    except Exception:  # noqa: BLE001 - fall back to a flat default table
        ys = [1.0] * len(xs)
    return pd.DataFrame({"x": xs, "y": ys})


@st.dialog("Edit function as a data table")
def _edit_function_table(param_name: str, overrides: dict, set_name: str) -> None:
    """Popup to edit a function-valued parameter as an (x, y) data table.

    The current function is sampled into the table; the user edits / adds rows
    and PyBaMM interpolates the result for the whole run.  The override is
    stored JSON-serialisably as ``{"__function_table__": {"x": [...], "y": [...]}}``
    and converted to a PyBaMM table parameter by
    :func:`pouch_cell.core.parameters.apply_parameter_overrides`.
    """
    import pandas as pd

    st.caption(
        f"PyBaMM interpolates these **(x, y)** points for `{param_name}`. "
        "Pick a domain and re-sample from the current function, then edit / add "
        "rows by hand."
    )
    c1, c2, c3 = st.columns(3)
    x0 = c1.number_input("x min", value=0.0, key=f"ft_x0_{param_name}")
    x1 = c2.number_input("x max", value=1.0, key=f"ft_x1_{param_name}")
    n = int(c3.number_input("Points", 3, 300, 21, key=f"ft_n_{param_name}"))
    if st.button("Re-sample from current function", key=f"ft_build_{param_name}"):
        st.session_state[f"ft_tbl_{param_name}"] = _sample_function_table(
            set_name, param_name, x0, x1, n
        )
        st.rerun()

    key = f"ft_tbl_{param_name}"
    if key not in st.session_state:
        existing = overrides.get(param_name)
        if isinstance(existing, dict) and "__function_table__" in existing:
            d = existing["__function_table__"]
            st.session_state[key] = pd.DataFrame(
                {"x": d.get("x", []), "y": d.get("y", [])}
            )
        else:
            st.session_state[key] = _sample_function_table(
                set_name, param_name, x0, x1, n
            )
    edited = st.data_editor(
        st.session_state[key].copy(),
        num_rows="dynamic",
        width="stretch",
        column_config={
            "x": st.column_config.NumberColumn("x", format="%.4g"),
            "y": st.column_config.NumberColumn("y", format="%.4g"),
        },
        key=f"ft_edit_{param_name}",
    )
    b1, b2 = st.columns(2)
    if b1.button("Apply table override", type="primary", key=f"ft_apply_{param_name}"):
        try:
            xs = [float(v) for v in edited["x"]]
            ys = [float(v) for v in edited["y"]]
        except (KeyError, TypeError, ValueError):
            st.error("The table must have numeric x and y columns.")
        else:
            overrides[param_name] = {"__function_table__": {"x": xs, "y": ys}}
            st.session_state.pop(key, None)
            st.rerun()
    if b2.button("Clear override", key=f"ft_clear_{param_name}"):
        overrides.pop(param_name, None)
        st.session_state.pop(key, None)
        st.rerun()


def _constant_override_input(sel: str, overrides: dict, row: dict | None) -> None:
    """Number input for a single-constant override of parameter ``sel``."""
    cur = overrides.get(sel)
    if cur is None:
        cur = (row or {}).get("value")
    try:
        cur_f = float(cur)
    except (TypeError, ValueError):
        cur_f = 0.0
    new = st.number_input(
        f"Constant value of `{sel}`", value=cur_f, format="%g", key=f"ptab_v_{sel}",
    )
    if new != cur_f:
        overrides[sel] = new


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
    st.caption(
        f"{len(matches)} parameter(s) match · {len(editable)} numeric/editable · "
        "the rest are function-valued and can be edited as a data table."
    )

    df = pd.DataFrame(
        [
            {
                "Parameter": r["name"],
                "Value (base set)": r["value"],
                "Type": ("numeric (editable)" if r["numeric"]
                         else "function (editable table)"),
            }
            for r in matches[:500]
        ]
    )
    st.dataframe(df, width="stretch", hide_index=True)

    sel = st.selectbox(
        "Edit a parameter (numeric or function-valued)",
        ["— select —"] + [r["name"] for r in matches],
        key=f"ptab_sel_{set_name}",
    )
    if sel != "— select —":
        row = next((r for r in matches if r["name"] == sel), None)
        if row and not row["numeric"]:
            st.warning(
                "This parameter is normally a **function** (e.g. OCP vs "
                "stoichiometry, diffusivity vs concentration). Edit it as a "
                "data table (recommended) or override with a single constant."
            )
            if st.button("Edit function table…", key=f"ptab_fn_{sel}"):
                _edit_function_table(sel, overrides, set_name)
            with st.expander("…or set a single constant instead", expanded=False):
                _constant_override_input(sel, overrides, row)
        else:
            _constant_override_input(sel, overrides, row)
        if sel in overrides and st.button(
            f"Clear override: `{sel}`", key=f"ptab_c_{sel}"
        ):
            overrides.pop(sel, None)
            st.rerun()
