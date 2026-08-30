"""Model & Run page -- model / mesh / SOC / C-rate / duration controls.

The sidebar already handles the quick knobs (model, mesh, C-rate, duration,
SOC); this page carries the detailed model options and the run definition.
"""
import streamlit as st

from pouch_cell import registry
from pouch_cell.ui import common

common.init_state()
common.render_sidebar()

st.title("Model & Run")
cfg = st.session_state.config

# ---------------------------------------------------------------- analysis
st.markdown("#### Analysis")
ana_opts = registry.options("analysis")
# Tab analysis only makes sense for the 2+1D models -- SPM_3D has no in-plane
# current-collector map.  Read the *intended* selection from the widget key and
# force 'discharge' for SPM_3D *before* the radio is instantiated (writing a
# widget key after it is instantiated is forbidden by Streamlit).
intended = st.session_state.get("r_analysis", cfg.analysis)
if cfg.model_name == "SPM_3D" and intended == "tab":
    st.session_state["r_analysis"] = "discharge"
    cfg.analysis = "discharge"
    st.warning(
        "Tab analysis requires a 2+1D model (SPM / SPMe / DFN); switched the "
        "analysis to 'discharge'. Choose SPM for long tab runs."
    )
cfg.analysis = st.radio(
    "Type", ana_opts,
    index=ana_opts.index(cfg.analysis) if cfg.analysis in ana_opts else 0,
    key="r_analysis", horizontal=True,
    help="discharge = plain CC discharge · tab = tab heating",
)
if cfg.analysis == "tab":
    st.info(
        "Tab analysis uses a 2+1D `x-lumped` model. DFN/SPMe are DAE-limited to "
        "~5–10 s (`IDA_ERR_FAIL`); choose **SPM** for longer tab runs."
    )

# ---------------------------------------------------------------- model
st.markdown("#### Model")
c1, c2, c3 = st.columns(3)
cfg.dimensionality = c1.selectbox(
    "Dimensionality", [0, 1, 2], index=[0, 1, 2].index(cfg.dimensionality),
    key="r_dim",
)
cfg.thermal = c2.selectbox(
    "Thermal", registry.options("thermal"),
    index=registry.options("thermal").index(cfg.thermal), key="r_thermal",
)
cfg.parameter_set = c3.selectbox(
    "Parameter set", registry.options("parameter_set"),
    index=registry.options("parameter_set").index(cfg.parameter_set),
    key="r_param_set",
)

if cfg.thermal == "x-lumped" and cfg.dimensionality == 0:
    st.warning("x-lumped requires dimensionality >= 1; will fall back to lumped.")
if cfg.model_name == "SPM_3D":
    cfg.full_stack_3d = st.checkbox(
        "Full-stack 3D geometry (span all layers in x)",
        value=cfg.full_stack_3d, key="r_full_stack",
    )

# ---------------------------------------------------------------- run
st.markdown("#### Run definition")
c1, c2, c3 = st.columns(3)
cfg.solver = c1.selectbox(
    "Solver", registry.options("solver"),
    index=registry.options("solver").index(cfg.solver), key="r_solver",
)
cfg.cutoff_V = c2.number_input(
    "Cut-off voltage (V, 0 = spec default)", 0.0, 4.5,
    float(cfg.cutoff_V or 0.0), 0.05, key="r_cutoff",
) or None
cfg.size_to_capacity = c3.checkbox(
    "Auto-size to capacity", value=cfg.size_to_capacity, key="r_size",
)

if cfg.analysis == "tab":
    cfg.particle = st.selectbox(
        "Particle model", ["uniform profile", "Fickian diffusion"],
        index=0 if cfg.particle == "uniform profile" else 1, key="r_particle",
    )

st.markdown("#### Outputs")
c1, c2 = st.columns(2)
cfg.store_first_last = c1.checkbox(
    "Store first/last only (memory-light)", value=cfg.store_first_last,
    key="r_sfl",
)
cfg.output_variables = c2.text_input(
    "Output variables (comma-separated, optional)",
    value=", ".join(cfg.output_variables) if cfg.output_variables else "",
    key="r_outputs",
) or None
if cfg.output_variables:
    cfg.output_variables = [v.strip() for v in cfg.output_variables.split(",")]

st.divider()
st.markdown("**Summary**")
st.code(
    f"analysis={cfg.analysis} · {cfg.model_name} dim={cfg.dimensionality} "
    f"thermal={cfg.thermal} · mesh={cfg.mesh} · SOC={cfg.initial_soc} · "
    f"{cfg.C_rate}C · {cfg.duration_s:.0f}s · solver={cfg.solver}"
)
