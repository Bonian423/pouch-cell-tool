"""Design page -- cell geometry + auto-sizing.

Auto-sizing runs at the TOP of the script, before any widget is instantiated,
so the sized thicknesses can be written back into the widget keys (``d_L_n``,
``d_L_p``, ``d_capacity``, ...).  Streamlit forbids writing a widget's
``session_state`` key after that widget has been instantiated in the same run,
so the intended geometry is *read* from session state (reading is always safe)
and the sized values are *written* before the widgets exist.  The manual
"Re-size to capacity" button uses an ``on_click`` callback for the same reason.
"""
import copy

import streamlit as st

from pouch_cell.ui import common

common.init_state()
common.render_sidebar()

st.title("Design — cell geometry")
spec = st.session_state.spec

# ------------------------------------------------------------------ manual
manual = st.checkbox(
    "Manual thicknesses (disable auto-sizing)", value=False, key="d_manual"
)
st.caption(
    "When capacity / footprint / stacks change, the electrodes are re-sized "
    "automatically to hit the target capacity (unless manual is on)."
)

# ------------------------------------------------------------------ auto-size
# Read the *intended* geometry from widget state -- safe to read; the writes
# below happen before those widgets are instantiated on this run.
new_capacity = st.session_state.get("d_capacity", spec.capacity_Ah)
new_height = st.session_state.get("d_height", spec.height * 100.0) / 100.0
new_width = st.session_state.get("d_width", spec.width * 100.0) / 100.0
new_nstacks = int(st.session_state.get("d_nstacks", spec.n_stacks))

sizing_key = (float(new_capacity), float(new_height), float(new_width), new_nstacks)
if (not manual) and (sizing_key != tuple(st.session_state.sizing_key)):
    from pouch_cell.core.sizing import size_electrodes_to_capacity

    work = copy.copy(spec)
    work.capacity_Ah = float(new_capacity)
    work.height = float(new_height)
    work.width = float(new_width)
    work.n_stacks = new_nstacks
    try:
        with st.spinner("Auto-sizing electrodes (fast 1D reference solve)…"):
            sized, _hist = size_electrodes_to_capacity(work, verbose=False)
    except RuntimeError as err:
        # don't retry on every rerun -- the user must change a knob to retry
        st.session_state.sizing_key = tuple(sizing_key)
        st.error(f"⚠️ Auto-sizing couldn't reach the target: {err}")
    else:
        st.session_state.spec = sized
        # safe: these widgets are not instantiated yet on this run
        st.session_state["d_L_n"] = float(sized.L_n * 1e6)
        st.session_state["d_L_p"] = float(sized.L_p * 1e6)
        st.session_state["d_capacity"] = float(sized.capacity_Ah)
        st.session_state["d_height"] = float(sized.height * 100.0)
        st.session_state["d_width"] = float(sized.width * 100.0)
        st.session_state["d_nstacks"] = int(sized.n_stacks)
        st.session_state.sizing_key = tuple(sizing_key)
        spec = sized

# ------------------------------------------------------------------ footprint
st.markdown("#### Footprint")
c1, c2, c3 = st.columns(3)
spec.height = c1.number_input(
    "Height (cm)", 5.0, 50.0, float(spec.height) * 100, 0.5, key="d_height"
) / 100.0
spec.width = c2.number_input(
    "Width (cm)", 5.0, 50.0, float(spec.width) * 100, 0.5, key="d_width"
) / 100.0
spec.thickness_total = c3.number_input(
    "Outer thickness (mm)", 1.0, 30.0, float(spec.thickness_total) * 1000, 0.5,
    key="d_thickness",
) / 1000.0

# ------------------------------------------------------------------ stack
st.markdown("#### Stack & capacity")
c1, c2 = st.columns(2)
spec.n_stacks = int(
    c1.number_input("Stacks in parallel", 1, 100, spec.n_stacks, 1, key="d_nstacks")
)
spec.capacity_Ah = c2.number_input(
    "Nominal capacity (Ah)", 0.5, 100.0, float(spec.capacity_Ah), 0.5,
    key="d_capacity",
)

# ------------------------------------------------------------------ layers
st.markdown("#### Unit-cell layer thicknesses")
c1, c2, c3, c4, c5 = st.columns(5)
spec.L_n = c1.number_input(
    "Neg electrode L_n (µm)", 10.0, 2000.0, float(spec.L_n) * 1e6, 1.0, key="d_L_n"
) * 1e-6
spec.L_p = c2.number_input(
    "Pos electrode L_p (µm)", 10.0, 2000.0, float(spec.L_p) * 1e6, 1.0, key="d_L_p"
) * 1e-6
spec.L_s = c3.number_input(
    "Separator L_s (µm)", 1.0, 50.0, float(spec.L_s) * 1e6, 0.5, key="d_L_s"
) * 1e-6
spec.L_cn = c4.number_input(
    "Neg collector L_cn (µm)", 1.0, 50.0, float(spec.L_cn) * 1e6, 0.5, key="d_L_cn"
) * 1e-6
spec.L_cp = c5.number_input(
    "Pos collector L_cp (µm)", 1.0, 50.0, float(spec.L_cp) * 1e6, 0.5, key="d_L_cp"
) * 1e-6

# ------------------------------------------------------------------ tabs
st.markdown("#### Tabs (top edge)")
c1, c2, c3 = st.columns(3)
spec.tab_width = c1.number_input(
    "Tab width (cm)", 0.5, 5.0, float(spec.tab_width) * 100, 0.1, key="d_tab_w"
) / 100.0
spec.neg_tab_y_centre = c2.number_input(
    "Neg tab y-centre (cm)", 0.0, 50.0, float(spec.neg_tab_y_centre) * 100, 0.1,
    key="d_tab_neg",
) / 100.0
spec.pos_tab_y_centre = c3.number_input(
    "Pos tab y-centre (cm)", 0.0, 50.0, float(spec.pos_tab_y_centre) * 100, 0.1,
    key="d_tab_pos",
) / 100.0

# ------------------------------------------------------------------ re-size
def _force_resize() -> None:
    """Button callback: re-size to the current capacity (runs before widgets)."""
    from pouch_cell.core.sizing import size_electrodes_to_capacity

    try:
        sized, _hist = size_electrodes_to_capacity(
            st.session_state.spec, verbose=False
        )
    except RuntimeError as err:
        st.session_state["sizing_error"] = str(err)
        return
    st.session_state.pop("sizing_error", None)
    st.session_state.spec = sized
    st.session_state["d_L_n"] = float(sized.L_n * 1e6)
    st.session_state["d_L_p"] = float(sized.L_p * 1e6)
    st.session_state["d_capacity"] = float(sized.capacity_Ah)
    st.session_state["d_manual"] = False
    st.session_state.sizing_key = (
        sized.capacity_Ah, sized.height, sized.width, sized.n_stacks,
    )


if "sizing_error" in st.session_state:
    st.error(f"⚠️ Re-sizing failed: {st.session_state['sizing_error']}")

c1, c2 = st.columns([1, 3])
c1.button(
    "🔄 Re-size to capacity",
    on_click=_force_resize,
    disabled=manual,
    use_container_width=True,
)
c2.caption(
    f"Current thicknesses: L_n = {spec.L_n * 1e6:.1f} µm, "
    f"L_p = {spec.L_p * 1e6:.1f} µm."
)

st.divider()
st.code(spec.report())
