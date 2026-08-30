"""Pouch-cell tool -- Streamlit entry point.

Launch: ``python -m pouch_cell --ui``  (or ``streamlit run pouch_cell/ui/app.py``)
"""
import streamlit as st

from pouch_cell.ui import common

common.init_state()
common.render_sidebar()

st.title("⚡ Pouch Cell Modelling Tool")
st.caption(
    "Tweak the design and run conditions, press **Run**, and compare results — "
    "fast iteration on a PyBaMM 3D pouch-cell model."
)

with st.container():
    st.markdown("#### Current design")
    st.markdown(common.summary_markdown())

st.divider()
st.markdown(
    """
**Pages** (sidebar): **Design** (geometry + auto-sizing) · **Model & Run** ·
**Thermal** (cooling / heat pipe) · **Results** · **History**.

Solves run in a background process, so you can keep tweaking while a long 2+1D
or 3D run is in flight, and cancel it at any time.

> Tip: start fast with `Model = DFN`, `dimensionality 0` (1D), then switch to
> `2` for the 2+1D current/temperature maps.  Note DFN/SPMe 2+1D are DAE-limited
> to ~5–10 s of 1C discharge (`IDA_ERR_FAIL`); use **SPM** 2+1D for longer runs.
"""
)
