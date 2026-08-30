"""Thermal page -- cooling preset, ambient, heat pipe, per-face h, raw overrides."""
import json

import streamlit as st

from pouch_cell import registry
from pouch_cell.ui import common

common.init_state()
common.render_sidebar()

st.title("Thermal & cooling")
spec = st.session_state.spec
thermal = st.session_state.thermal

# ------------------------------------------------------------- cooling
st.markdown("#### Cooling")
cool_opts = ["— none —"] + registry.options("cooling")
c_val = thermal.cooling if isinstance(thermal.cooling, str) else "— none —"
idx = cool_opts.index(c_val) if c_val in cool_opts else 0
sel = st.selectbox("Cooling preset", cool_opts, index=idx, key="t_preset")
thermal.cooling = None if sel == "— none —" else sel

c1, c2 = st.columns(2)
amb = c1.number_input(
    "Ambient temperature (K)", 250.0, 350.0,
    float(thermal.ambient_temperature_K or spec.ambient_temperature_K),
    0.5, key="t_amb",
)
thermal.ambient_temperature_K = amb
h_ov = c2.number_input(
    "Heat-transfer coefficient override (W/m²/K, 0 = preset/natural)",
    0.0, 5000.0, float(thermal.heat_transfer_coefficient_W_m2K or 0.0),
    10.0, key="t_h",
)
thermal.heat_transfer_coefficient_W_m2K = h_ov or None

if thermal.cooling:
    st.caption(
        f"Preset `{thermal.cooling}` h = "
        f"{registry.get('cooling', thermal.cooling)} W/m²/K"
    )

# ------------------------------------------------------------- heat pipe
st.markdown("#### Heat pipe (full-width band below the top edge)")
spec.heat_pipe_enabled = st.checkbox(
    "Enable heat pipe", value=spec.heat_pipe_enabled, key="t_hp_on",
)
if spec.heat_pipe_enabled:
    c1, c2, c3 = st.columns(3)
    spec.heat_pipe_height = c1.number_input(
        "Band height (cm)", 0.1, 3.0, float(spec.heat_pipe_height) * 100,
        0.1, key="t_hp_hgt",
    ) / 100.0
    spec.heat_pipe_h = c2.number_input(
        "Effective h (W/m²/K)", 10.0, 100000.0, float(spec.heat_pipe_h),
        50.0, key="t_hp_h",
    )
    spec.heat_pipe_temperature_K = c3.number_input(
        "Pipe temperature (K)", 250.0, 320.0,
        float(spec.heat_pipe_temperature_K), 0.5, key="t_hp_T",
    )
    st.caption(
        "A copper heat pipe runs across the full cell width right below the "
        "top edge (applied in 2+1D `x-lumped` solves)."
    )

# ------------------------------------------------------------- per-face h
if st.session_state.config.model_name == "SPM_3D":
    st.markdown("#### Per-face heat-transfer coefficients (SPM_3D)")
    cols = st.columns(3)
    for i, face in enumerate(["left", "right", "front", "back", "bottom", "top"]):
        with cols[i % 3]:
            cur = thermal.per_face_h.get(face, 5.0)
            thermal.per_face_h[face] = st.number_input(
                f"{face.capitalize()} face h", 0.0, 5000.0, float(cur),
                5.0, key=f"t_face_{face}",
            )

# ------------------------------------------------------------- raw override
st.markdown("#### Raw PyBaMM parameter overrides (advanced)")
default_raw = json.dumps(thermal.extra_overrides, indent=2) if thermal.extra_overrides else ""
raw = st.text_area(
    "JSON dict of parameter overrides (e.g. "
    '`{"Ambient temperature [K]": 288.15}`)',
    value=default_raw, key="t_raw", height=110,
)
try:
    parsed = json.loads(raw) if raw.strip() else {}
    thermal.extra_overrides = parsed if isinstance(parsed, dict) else {}
    if raw.strip() and not isinstance(parsed, dict):
        st.error("Overrides must be a JSON object.")
except json.JSONDecodeError as err:
    st.error(f"Invalid JSON: {err}")
    thermal.extra_overrides = {}

st.divider()
st.code(
    f"cooling = {thermal.to_cooling()}\n"
    f"heat_pipe = {spec.heat_pipe_enabled} "
    f"(h={spec.heat_pipe_h:.0f}, {spec.heat_pipe_height * 100:.1f} cm band, "
    f"{spec.heat_pipe_temperature_K:.1f} K)"
)
