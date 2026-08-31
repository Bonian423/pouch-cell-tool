"""Thermal page -- cooling preset, ambient, heat pipe, per-face h, thermal-map
preview and a parameter-override reference ordered (i) curated -> (iii) examples
-> (ii) full table last.
"""
import json

import streamlit as st

from pouch_cell import registry
from pouch_cell.ui import common
from pouch_cell.ui.params import (
    CURATED_THERMAL_PARAMS,
    EXAMPLE_OVERRIDES,
    example_json,
    quick_thermal_preview,
    render_curated_editors,
    render_param_table,
)

common.init_state()
common.render_sidebar()

st.title("Thermal & cooling")
spec = st.session_state.spec
thermal = st.session_state.thermal
cfg = st.session_state.config

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
if cfg.model_name == "SPM_3D":
    st.markdown("#### Per-face heat-transfer coefficients (SPM_3D)")
    cols = st.columns(3)
    for i, face in enumerate(["left", "right", "front", "back", "bottom", "top"]):
        with cols[i % 3]:
            cur = thermal.per_face_h.get(face, 5.0)
            thermal.per_face_h[face] = st.number_input(
                f"{face.capitalize()} face h", 0.0, 5000.0, float(cur),
                5.0, key=f"t_face_{face}",
            )

# ------------------------------------------------------------- quick thermal map
st.markdown("#### Thermal map preview")
st.caption(
    "Run a fast coarse 2+1D SPM solve and draw the temperature / "
    "current-density / Ohmic-heating maps right here, so you can iterate on "
    "cooling and heat-pipe settings before a full run. Pick a **protocol step** "
    "to draw the map at the end of that step instead of a fresh 5-second "
    "discharge."
)
proto = st.session_state.protocol
_step_labels = ["Fresh 5 s discharge"] + [
    f"step {i + 1}: {s.to_string(spec.capacity_Ah)}"
    for i, s in enumerate(proto.steps)
]
prev_step = st.selectbox("Preview at", _step_labels, key="t_prev_step")

c1, c2 = st.columns([1, 3])
if c1.button("Generate thermal map", type="primary"):
    with st.spinner("Running quick 2+1D solve…"):
        if prev_step == "Fresh 5 s discharge":
            st.session_state["quick_map"] = quick_thermal_preview(
                spec, cfg, thermal
            )
        else:
            idx = _step_labels.index(prev_step) - 1
            st.session_state["quick_map"] = quick_thermal_preview(
                spec, cfg, thermal, steps=proto.steps, step_idx=idx
            )
qm = st.session_state.get("quick_map")
if qm:
    if qm.get("ok"):
        st.image(qm["figure"], caption=f"Thermal preview ({qm.get('note', '')})", width="stretch")
        if qm.get("warning"):
            st.warning(qm["warning"])
        m = qm.get("metrics", {})
        st.caption(
            f"final V = {m.get('final_V', float('nan')):.3f} V · "
            f"Tmax = {m.get('Tmax_K', float('nan')):.1f} K"
        )
    else:
        st.error(f"Quick preview failed: {qm.get('error')}")

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

# ------------------------------------------------------------- override reference
with st.expander("Parameter overrides — reference & examples", expanded=False):
    tab_curated, tab_examples, tab_table = st.tabs(
        ["Curated knobs", "Copy-ready examples", "Full parameter table"]
    )
    with tab_curated:  # (i) curated dict for the selected model
        render_curated_editors(
            cfg.parameter_set, thermal.extra_overrides,
            curated=CURATED_THERMAL_PARAMS, section_title="Thermal / material knobs",
        )
        st.caption(
            "Edits here are folded into the solve's `ParameterValues` (via the "
            "raw overrides dict above)."
        )
    with tab_examples:  # (iii) copy-ready examples
        st.caption("Click **Use** to load an example into the raw override box.")
        for label, _d in EXAMPLE_OVERRIDES:
            c1, c2 = st.columns([3, 1])
            c1.markdown(f"**{label}**")
            if c2.button("Use", key=f"ex_{label[:20]}"):
                thermal.extra_overrides.update(_d)
                st.rerun()
            st.code(example_json(label), language="json")
    with tab_table:  # (ii) full searchable table -- last
        render_param_table(cfg.parameter_set, thermal.extra_overrides)
        if st.button("Reset ALL thermal overrides"):
            thermal.extra_overrides.clear()
            st.rerun()

st.divider()
st.code(
    f"cooling = {thermal.to_cooling()}\n"
    f"heat_pipe = {spec.heat_pipe_enabled} "
    f"(h={spec.heat_pipe_h:.0f}, {spec.heat_pipe_height * 100:.1f} cm band, "
    f"{spec.heat_pipe_temperature_K:.1f} K)"
)
