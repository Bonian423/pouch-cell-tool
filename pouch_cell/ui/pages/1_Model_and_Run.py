"""Model & Run page -- physics model, mesh, thermal, parameter set + outputs.

The *run type* (discharge / charge / multi-step protocol) lives on the
Protocols page; this page only tunes the underlying battery model.
"""
import streamlit as st

from pouch_cell import registry
from pouch_cell.ui import common

common.page_setup()

st.title("Model & Run")
with common.page_body():
    cfg = st.session_state.config

    # ---------------------------------------------------------------- model
    # Guards keep only viable combinations selectable.  Read the *intended*
    # selection from the widget keys first, then auto-correct the dependent
    # fields BEFORE their widgets are instantiated (Streamlit forbids writing
    # a widget's key after it has been created in the same run).  Rules live in
    # pouch_cell/core/constraints.py (single source of truth).
    from pouch_cell.core import constraints as _constraints

    intended_dim = st.session_state.get("m_dim", cfg.dimensionality)
    cfg.dimensionality = intended_dim
    intended_model = st.session_state.get("m_model", cfg.model_name)
    cfg.model_name = intended_model
    mesh_opts = common.sync_mesh(cfg, "m_mesh")  # per-family mesh memory + valid list
    fixed = _constraints.normalise_config(cfg)
    if "thermal" in fixed:
        st.session_state["m_thermal"] = cfg.thermal
    if "mesh" in fixed:
        st.session_state["m_mesh"] = cfg.mesh
    common.note_corrections(
        [f"auto-corrected {f} → {getattr(cfg, f)}" for f in fixed]
    )

    st.markdown("#### Model")
    c1, c2, c3 = st.columns(3)
    _is_3d = cfg.model_name == "SPM_3D"
    if _is_3d:
        # true-3D FEM: dimensionality and thermal are dead controls -> hide
        c1.caption("**Dimensionality**  \nfixed — true 3D FEM")
        c2.caption("**Thermal**  \nfixed — true 3D FEM")
    else:
        thermal_opts = _constraints.viable_thermal(cfg.dimensionality)
        cfg.dimensionality = c1.selectbox(
            "Dimensionality", [0, 1, 2], index=[0, 1, 2].index(cfg.dimensionality),
            key="m_dim",
            help="0 = 0D (through-plane only) · 1 = pseudo-2D · 2 = 2+1D with "
                 "in-plane current collectors (needed for tab/thermal maps).",
        )
        cfg.thermal = c2.selectbox(
            "Thermal", thermal_opts,
            index=thermal_opts.index(cfg.thermal), key="m_thermal",
            help="Only thermal submodels valid for the chosen dimensionality "
                 "are listed.",
        )
    cfg.model_name = c3.selectbox(
        "Model", registry.options("model"),
        index=registry.options("model").index(cfg.model_name), key="m_model",
    )
    if _is_3d:
        st.caption(
            "`SPM_3D` is true-3D FEM — dimensionality and thermal are fixed "
            "(not applicable). Your previous values are kept and restored when "
            "you switch back."
        )

    model_help = {
        "DFN": "**Doyle–Fuller–Newman** full porous-electrode model: solid-phase "
               "diffusion in both electrodes, electrolyte concentration + "
               "potential, and both electrode reactions. The physically most "
               "complete option, and the slowest.",
        "SPMe": "**Single Particle with Electrolyte**: solid diffusion per "
                "electrode plus a simplified electrolyte distribution. Much "
                "faster than DFN and very accurate for moderate currents.",
        "SPM": "**Single Particle Model**: only solid-phase diffusion, no "
               "electrolyte dynamics. The fastest option — required for longer "
               "2+1D / tab runs.",
        "SPM_3D": "**True-3D SPM** on an FEM mesh (full stack). Visualises the "
                  "whole pouch in 3D but is very slow — use short durations.",
    }
    with st.expander("What is this model?"):
        st.markdown(model_help.get(cfg.model_name, ""))

    if cfg.model_name == "SPM_3D":
        cfg.full_stack_3d = st.checkbox(
            "Full-stack 3D geometry (span all layers in x)",
            value=cfg.full_stack_3d, key="m_full_stack",
        )

    # ---------------------------------------------------------------- mesh
    st.markdown("#### Mesh")
    cfg.mesh = st.selectbox(
        "Mesh density", mesh_opts,
        index=mesh_opts.index(cfg.mesh) if cfg.mesh in mesh_opts else 0,
        key="m_mesh",
        help="The 2+1D presets are 2× the original mesh density (user request). "
             "True-3D meshes are FEM element sizes — use coarse.",
    )
    if cfg.model_name == "SPM_3D":
        st.caption(
            "3D FEM solves are intractable beyond ~seconds at fine element "
            "sizes; `draft_3d` is the only practical choice for a full pouch."
        )
    elif cfg.mesh in ("micro_21d", "coarse_21d"):
        st.caption(
            "`micro_21d` / `coarse_21d` use r=1 particle meshes, so the "
            "particle model is locked to `uniform profile`."
        )

    # ---------------------------------------------------------------- parameter set
    st.markdown("#### Parameter set")

    def _browse_sets(set_opts: list[str]) -> None:
        """Filterable reference table of every available set (replaces the old
        chemistry-guide expander).  Each row has a **Use** button that sets the
        active set via ``m_set_intent`` (consumed write-before-instantiate)."""
        filter_txt = st.text_input(
            "Filter (name / chemistry / kind)", key="m_set_filter",
            help="Type to filter the table by set name or chemistry.",
        )
        rows = []
        for _name in set_opts:
            _m = registry.parameter_set_meta(_name)
            rows.append((_name, _m))
        if filter_txt:
            flt = filter_txt.strip().lower()
            rows = [r for r in rows
                    if flt in r[0].lower()
                    or flt in (r[1].get("chemistry", "")).lower()
                    or flt in (r[1].get("kind", "")).lower()]
        if not rows:
            st.caption("No parameter sets match that filter.")
            return
        for _name, _m in rows:
            c1, c2 = st.columns([0.6, 6])
            if c1.button("Use", key=f"m_set_use_{_name}"):
                st.session_state["m_set_intent"] = _name
                st.rerun()
            c2.markdown(
                f"**`{_name}`** — {_m.get('chemistry', '')} "
                f"(`{_m.get('kind', '')}`)  \n{_m.get('description', '')}"
            )

    set_opts = registry.options("parameter_set")
    _intent = st.session_state.pop("m_set_intent", None)
    if _intent and _intent in set_opts:
        cfg.parameter_set = _intent
        # write-before-instantiate so the Use-button intent takes effect
        st.session_state["m_param_set"] = cfg.parameter_set
    set_idx = set_opts.index(cfg.parameter_set) if cfg.parameter_set in set_opts else 0
    cfg.parameter_set = st.selectbox(
        "Electrochemistry parameter set", set_opts, index=set_idx, key="m_param_set",
        help="The active electrochemistry set. Use **Browse parameter sets** "
             "below for a filterable reference of every option.",
    )
    _meta = registry.parameter_set_meta(cfg.parameter_set)
    st.caption(
        f"**{_meta.get('chemistry', '')}** · {_meta.get('kind', '')} — "
        f"{_meta.get('description', '')}"
    )
    with st.expander("Browse parameter sets"):
        _browse_sets(set_opts)

    # ---------------------------------------------------------------- run settings
    st.markdown("#### Solve settings")
    c1, c2, c3 = st.columns(3)
    cfg.solver = c1.selectbox(
        "Solver", registry.options("solver"),
        index=registry.options("solver").index(cfg.solver), key="m_solver",
    )
    cfg.size_to_capacity = c2.checkbox(
        "Auto-size to capacity", value=cfg.size_to_capacity, key="m_size",
    )
    c3.caption("Run type & current are set on the **Protocols** page.")

    # ---------------------------------------------------------------- outputs
    st.markdown("#### Outputs")
    _solver_ignores_outputs = cfg.solver not in (None, "default")
    c1, c2 = st.columns(2)
    cfg.store_first_last = c1.checkbox(
        "Store first/last only (memory-light)", value=cfg.store_first_last,
        key="m_sfl", disabled=_solver_ignores_outputs,
    )
    cfg.output_variables = c2.text_input(
        "Output variables (comma-separated, optional)",
        value=", ".join(cfg.output_variables) if cfg.output_variables else "",
        key="m_outputs", disabled=_solver_ignores_outputs,
    ) or None
    if cfg.output_variables:
        cfg.output_variables = [v.strip() for v in cfg.output_variables.split(",")]
    if _solver_ignores_outputs:
        st.caption(
            f"Output variables / store-first-last only apply with the "
            f"**default** solver — they are ignored with `{cfg.solver}` (values "
            "are kept for when you switch back)."
        )
    else:
        _names = [v for v in (cfg.output_variables or []) if v.strip()]
        if st.button("Check variable names", key="m_check_vars", disabled=not _names):
            _missing = common.check_variable_names(_names)
            if _missing:
                st.error("Not found in the model: " + ", ".join(_missing))
            else:
                st.success(f"All {len(_names)} output variable(s) resolve.")

    st.divider()
    st.markdown("**Summary**")
    st.code(
        f"{cfg.model_name} dim={cfg.dimensionality} thermal={cfg.thermal} · "
        f"mesh={cfg.mesh} · param_set={cfg.parameter_set} · SOC={cfg.initial_soc} · "
        f"solver={cfg.solver}"
    )
