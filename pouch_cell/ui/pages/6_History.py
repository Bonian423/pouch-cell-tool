"""History page -- in-session run comparison + persistent JSONL history.

Runs from the current session appear in the table; each can be saved
individually, or the whole session can be persisted to
``pouch_output/history.jsonl`` (survives restarts).  Saved runs can be loaded
back into Results for review without re-running.
"""
import pandas as pd
import streamlit as st

from pouch_cell.ui import common

common.page_setup()

st.title("Run history")
with common.page_body():
    # ------------------------------------------------------------------ session table
    history = st.session_state.history
    st.markdown("#### This session")
    if not history:
        st.info("No runs recorded yet in this session.")
    else:
        rows = []
        for h in history:
            rows.append(
                {
                    "model": h.get("model"),
                    "dim": h.get("dimensionality"),
                    "thermal": h.get("thermal"),
                    "mesh": h.get("mesh"),
                    "type": h.get("protocol_type") or h.get("analysis"),
                    "final_V": h.get("final_V"),
                    "Ah": h.get("delivered_Ah"),
                    "Tmax_K": h.get("Tmax_K"),
                    "wall_s": h.get("wall_s"),
                    "error": (h.get("error") or "")[:40],
                }
            )
        df = pd.DataFrame(rows)
        st.dataframe(df, width="stretch", hide_index=True)

        c1, c2, c3 = st.columns(3)
        if c1.button("Save session to history file"):
            n = common.save_session()
            st.success(f"Saved {n} run(s) to {common.HISTORY_FILE}")
        if c2.button("Clear session history"):
            st.session_state.history = []
            st.session_state.saved_count = 0
            st.rerun()
        c3.caption(f"{len(history)} runs in session")

    # ------------------------------------------------------------------ persistent history
    st.markdown("#### Saved history file")
    saved = common.load_saved_runs()
    st.caption(f"{len(saved)} saved run(s) in `{common.HISTORY_FILE}`")
    if saved:
        labels = [
            f"{e.get('saved_at', '?')} · {e['result'].get('model', '?')} · "
            f"V={e['result'].get('final_V', float('nan')):.2f} · "
            f"Ah={e['result'].get('delivered_Ah', float('nan')):.2f} · "
            f"Tmax={e['result'].get('Tmax_K', float('nan')):.1f}"
            for e in saved
        ]
        choice = st.selectbox("Saved runs", list(reversed(labels)), key="hist_saved")
        idx = len(labels) - 1 - labels.index(choice)
        _res = saved[idx].get("result", {})
        _eff = _res.get("effective_config")
        _warns = _res.get("warnings") or []
        if _eff or _warns:
            with st.expander("Effective config & warnings (selected run)"):
                if _eff:
                    st.json(_eff)
                for _w in _warns:
                    st.warning(_w)
        c1, c2 = st.columns(2)
        if c1.button("Load into Results", key="hist_load"):
            common.load_result_into_session(saved[idx])
            st.rerun()
        if c2.button("Delete this entry", key="hist_del"):
            common.delete_saved_run(idx)
            st.rerun()

    st.divider()
    st.markdown("#### Tips")
    st.caption(
        "Run the same design with different cooling / cooling-geometry / mesh "
        "settings and compare `Tmax_K` and `final_V` rows here. Session history "
        "is cleared when the server restarts; **Save session** persists it to "
        "the JSONL file."
    )
