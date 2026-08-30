"""Results page -- metrics + figures of the most recent run."""
from pathlib import Path

import streamlit as st

from pouch_cell.ui import common

common.init_state()
common.render_sidebar()

st.title("Results")

last = st.session_state.last_result
if last is None:
    st.info("No run yet — press **Run** in the sidebar.")
    st.stop()

if "error" in last:
    st.error(f"Run failed:\n\n`{last['error']}`")
    tb = last.get("traceback", "")
    with st.expander("Traceback"):
        st.code(tb)
    st.stop()

st.success(f"Run complete in {last.get('wall_s', 0):.1f} s")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Final voltage", f"{last.get('final_V', float('nan')):.3f} V")
c2.metric("Delivered capacity", f"{last.get('delivered_Ah', float('nan')):.2f} Ah")
c3.metric("T max", f"{last.get('Tmax_K', float('nan')):.1f} K")
c4.metric("T final", f"{last.get('T_final_K', float('nan')):.1f} K")

st.markdown("#### Config")
cfg = st.session_state.config
st.code(
    f"analysis={last.get('analysis', cfg.analysis)} · {last.get('model', cfg.model_name)} "
    f"dim={last.get('dimensionality', cfg.dimensionality)} · "
    f"thermal={last.get('thermal', cfg.thermal)} · mesh={last.get('mesh', cfg.mesh)} · "
    f"{last.get('C_rate', cfg.C_rate)}C · "
    f"{last.get('duration_s', cfg.duration_s):.0f}s"
)

st.markdown("#### Figures")
run_dir = Path(last["run_dir"])
figs = last.get("figures", [])
if figs:
    cols = st.columns(min(len(figs), 2))
    for i, name in enumerate(figs):
        p = run_dir / name
        if p.is_file():
            with cols[i % 2]:
                st.image(str(p), caption=name, use_container_width=True)
else:
    st.caption("No figures were saved for this run.")

hist = last.get("sizing_history", [])
if hist:
    st.markdown("#### Sizing history (Ah delivered per iteration)")
    st.caption(f"{[f'{h:.2f}' for h in hist]}")
