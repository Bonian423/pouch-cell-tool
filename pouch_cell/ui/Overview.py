"""App entrypoint + navigation router.

The old Overview tab was removed and its summary integrated into the
persistent right-side panel (``common.render_persistent_panel``) that every
page shows.  This script is the Streamlit entrypoint (``streamlit run
Overview.py``) and just wires up ``st.navigation`` to the seven pages, setting
the wide layout once (pages must NOT call ``st.set_page_config`` again).
"""
import streamlit as st

st.set_page_config(layout="wide", page_title="Pouch cell tool",
                   initial_sidebar_state="expanded")

_PAGES = [
    st.Page("pages/1_Model_and_Run.py", title="Model & Run", icon="🔬"),
    st.Page("pages/2_Design.py", title="Design", icon="📐"),
    st.Page("pages/3_Protocols.py", title="Protocols", icon="⚙️"),
    st.Page("pages/4_Thermal.py", title="Thermal & cooling", icon="🌡️"),
    st.Page("pages/5_Results.py", title="Results", icon="📊"),
    st.Page("pages/6_History.py", title="Run history", icon="🗂️"),
    st.Page("pages/7_Help.py", title="Help", icon="❓"),
]

_nav = st.navigation(_PAGES)
_nav.run()

