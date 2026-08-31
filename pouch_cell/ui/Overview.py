"""Overview tab -- current-settings summary + preset management.

The app's landing page.  Shows a readable summary of every knob that will be
used for the next run (design, model, protocol, thermal), lets you load/save
named presets, and reminds you how to get started.
"""
import streamlit as st

from pouch_cell.config import io as preset_io
from pouch_cell.ui import common

common.init_state()
common.render_sidebar()

st.title("Overview")
st.caption(
    "Current simulation settings — tweak them on the other tabs, then press "
    "**Run** in the sidebar. Settings are remembered between sessions."
)

# ------------------------------------------------------------------ presets
with st.expander("Presets (load / save a named configuration)", expanded=False):
    names = preset_io.list_presets()
    sel = st.selectbox("Load preset", ["— none —"] + names, key="ov_preset_sel")
    if st.button("Load preset", width="stretch") and sel != "— none —":
        common.apply_config(preset_io.load_preset(sel))
        st.rerun()
    save_name = st.text_input("Save current settings as", key="ov_save_name")
    if st.button("Save preset", width="stretch") and save_name:
        cfg = st.session_state.config
        cfg.design = st.session_state.spec.as_dict()
        cfg.protocol = st.session_state.protocol.as_dict()
        path = preset_io.save_preset(save_name, cfg)
        st.success(f"Saved preset `{path.stem}`.")

# ------------------------------------------------------------------ summary
spec = st.session_state.spec
cfg = st.session_state.config
thermal = st.session_state.thermal
proto = st.session_state.protocol

st.divider()
st.markdown("#### Cell design")
st.markdown(common.summary_markdown())

st.markdown("#### Model & run")
_kv = [
    ("Model", f"`{cfg.model_name}` · dim {cfg.dimensionality} · "
              f"`{cfg.thermal}` · `{cfg.mesh}`"),
    ("Parameter set", f"`{cfg.parameter_set}`"),
    ("Solver", f"`{cfg.solver}`"),
    ("Initial state",
     f"SOC {cfg.initial_soc:.2f}" if cfg.initial_voltage is None
     else f"**{cfg.initial_voltage:.2f} V** (voltage mode)"),
    ("Run type", cfg.analysis),
    ("Protocol", f"`{proto.type}` · {len(proto.steps)} step(s) × "
                 f"{max(1, int(proto.cycles))} cycle(s)"),
]
st.markdown("\n".join(f"- **{k}:** {v}" for k, v in _kv))

st.markdown("#### Thermal & cooling")
cool = thermal.to_cooling()
_kv2 = [
    ("Cooling", cool if isinstance(cool, str) else ("custom" if cool else "natural")),
    ("Ambient", f"{thermal.ambient_temperature_K or spec.ambient_temperature_K:.1f} K"),
    ("Heat pipe", "enabled" if spec.heat_pipe_enabled else "off"),
]
st.markdown("\n".join(f"- **{k}:** {v}" for k, v in _kv2))

st.divider()
st.markdown(
    """
**Pages** (sidebar): **Model & Run** · **Design** (geometry + chemistry) ·
**Thermal** (cooling / heat pipe / maps) · **Protocols** (discharge / charge /
multi-step) · **Results** · **History** · **Help**.

Solves run in a background process, so you can keep tweaking while a long 2+1D
or 3D run is in flight, and cancel it at any time.

> Tip: start fast with `Model = DFN`, `dimensionality 0` (1D), then switch to
> `2` for the 2+1D current/temperature maps.  Note DFN/SPMe 2+1D are DAE-limited
> to ~5–10 s of 1C discharge (`IDA_ERR_FAIL`); use **SPM** 2+1D for longer runs.
"""
)

