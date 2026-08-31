"""Model & Run page -- physics model, mesh, thermal, parameter set + outputs.

The *run type* (discharge / charge / multi-step protocol) lives on the
Protocols page; this page only tunes the underlying battery model.
"""
import streamlit as st

from pouch_cell import registry
from pouch_cell.ui import common

common.init_state()
common.render_sidebar()

st.title("Model & Run")
cfg = st.session_state.config

# ---------------------------------------------------------------- model
# Guards keep only viable combinations selectable.  Read the *intended*
# selection from the widget keys first, then auto-correct the dependent fields
# BEFORE their widgets are instantiated (Streamlit forbids writing a widget's
# key after it has been created in the same run).
intended_dim = st.session_state.get("m_dim", cfg.dimensionality)
cfg.dimensionality = intended_dim
thermal_opts = common.viable_thermal(cfg.dimensionality)
if cfg.thermal not in thermal_opts:
    st.session_state["m_thermal"] = "lumped"
    cfg.thermal = "lumped"

intended_model = st.session_state.get("m_model", cfg.model_name)
cfg.model_name = intended_model
mesh_opts = common.viable_mesh(cfg.model_name)
if cfg.mesh not in mesh_opts:
    st.session_state["m_mesh"] = mesh_opts[0]
    cfg.mesh = mesh_opts[0]
if cfg.mesh in ("micro_21d", "coarse_21d"):
    cfg.particle = "uniform profile"

st.markdown("#### Model")
c1, c2, c3 = st.columns(3)
cfg.dimensionality = c1.selectbox(
    "Dimensionality", [0, 1, 2], index=[0, 1, 2].index(cfg.dimensionality),
    key="m_dim",
    help="0 = 0D (through-plane only) · 1 = pseudo-2D · 2 = 2+1D with in-plane "
         "current collectors (needed for tab/thermal maps).",
)
cfg.thermal = c2.selectbox(
    "Thermal", thermal_opts,
    index=thermal_opts.index(cfg.thermal), key="m_thermal",
    help="Only thermal submodels valid for the chosen dimensionality are listed.",
)
cfg.model_name = c3.selectbox(
    "Model", registry.options("model"),
    index=registry.options("model").index(cfg.model_name), key="m_model",
)

model_help = {
    "DFN": "**Doyle–Fuller–Newman** full porous-electrode model: solid-phase "
           "diffusion in both electrodes, electrolyte concentration + potential, "
           "and both electrode reactions. The physically most complete option, "
           "and the slowest.",
    "SPMe": "**Single Particle with Electrolyte**: solid diffusion per electrode "
            "plus a simplified electrolyte distribution. Much faster than DFN "
            "and very accurate for moderate currents.",
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
        "3D FEM solves are intractable beyond ~seconds at fine element sizes; "
        "`draft_3d` is the only practical choice for a full pouch."
    )
elif cfg.mesh in ("micro_21d", "coarse_21d"):
    st.caption(
        "`micro_21d` / `coarse_21d` use r=1 particle meshes, so the particle "
        "model is locked to `uniform profile`."
    )

# ---------------------------------------------------------------- parameter set
st.markdown("#### Parameter set")
set_opts = registry.options("parameter_set")
set_idx = set_opts.index(cfg.parameter_set) if cfg.parameter_set in set_opts else 0
cfg.parameter_set = st.selectbox(
    "Electrochemistry parameter set", set_opts, index=set_idx, key="m_param_set",
)
info = registry.PARAMETER_SET_INFO.get(cfg.parameter_set)
if info:
    st.info(info)
with st.expander("What is this set? / chemistry guide"):
    st.markdown(
        "The parameter set defines the **electrode chemistries**, electrolyte "
        "and transport/kinetic constants. For your **NCM 811 cathode + "
        "graphite anode**, the closest matches are:\n\n"
        "- **ORegan2022** — NMC811 + graphite/silicon (high-Ni, closest to NCM 811)\n"
        "- **OKane2022** — NMC/graphite with SEI + plating side reactions\n"
        "- **Chen2020** — NMC111/graphite, the PyBaMM default\n"
        "- **Marquis2019 / Ecker2015 / Mohtat2020** — other NMC/graphite fits\n\n"
        "The trailing names are advanced (half-cells, composite electrodes, "
        "MSMR/ECM, sodium-ion) and are flagged as such."
    )

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
c1, c2 = st.columns(2)
cfg.store_first_last = c1.checkbox(
    "Store first/last only (memory-light)", value=cfg.store_first_last,
    key="m_sfl",
)
cfg.output_variables = c2.text_input(
    "Output variables (comma-separated, optional)",
    value=", ".join(cfg.output_variables) if cfg.output_variables else "",
    key="m_outputs",
) or None
if cfg.output_variables:
    cfg.output_variables = [v.strip() for v in cfg.output_variables.split(",")]

st.divider()
st.markdown("**Summary**")
st.code(
    f"{cfg.model_name} dim={cfg.dimensionality} thermal={cfg.thermal} · "
    f"mesh={cfg.mesh} · param_set={cfg.parameter_set} · SOC={cfg.initial_soc} · "
    f"solver={cfg.solver}"
)
