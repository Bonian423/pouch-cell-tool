"""History page -- comparison table of past runs + CSV export."""
import csv
import io

import pandas as pd
import streamlit as st

from pouch_cell.ui import common

common.init_state()
common.render_sidebar()

st.title("Run history")

history = st.session_state.history
if not history:
    st.info("No runs recorded yet.")
    st.stop()

# keep only the comparable numeric rows
rows = []
for h in history:
    rows.append(
        {
            "model": h.get("model"),
            "dim": h.get("dimensionality"),
            "thermal": h.get("thermal"),
            "mesh": h.get("mesh"),
            "analysis": h.get("analysis"),
            "C_rate": h.get("C_rate"),
            "duration_s": h.get("duration_s"),
            "final_V": h.get("final_V"),
            "Ah": h.get("delivered_Ah"),
            "Tmax_K": h.get("Tmax_K"),
            "wall_s": h.get("wall_s"),
            "error": h.get("error"),
        }
    )
df = pd.DataFrame(rows)

st.dataframe(df, use_container_width=True, hide_index=True)

c1, c2, c3 = st.columns(3)
csv_buf = io.StringIO()
df.to_csv(csv_buf, index=False)
c1.download_button(
    "⬇ Export CSV",
    data=csv_buf.getvalue(),
    file_name="pouch_run_history.csv",
    mime="text/csv",
)
if c2.button("🗑 Clear history"):
    st.session_state.history = []
    st.rerun()
c3.caption(f"{len(history)} runs recorded")

st.divider()
st.markdown("#### Side-by-side hints")
st.caption(
    "Run the same design with different cooling / heat-pipe / mesh settings and "
    "compare `Tmax_K` and `final_V` rows here. History lives for this session "
    "only — use **💾 Presets** in the sidebar to persist configurations."
)
