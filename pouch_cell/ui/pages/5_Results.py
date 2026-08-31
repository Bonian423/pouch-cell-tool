"""Results page -- metrics, per-step maps, V/T CSV and saved-run review.

Shows the most recent (or a loaded) run's metrics, its figures and, for
multi-step protocols, the per-step thermal maps with a selector and the
per-step metrics table.  Saved runs (from the History page or the dropdown
below) can be re-reviewed without re-running.
"""
import csv
import io
from pathlib import Path

import streamlit as st

from pouch_cell.ui import common

common.init_state()
common.render_sidebar()

st.title("Results")

last = st.session_state.last_result
if last is None:
    st.info("No run yet — press **Run** in the sidebar (or load a saved run).")
    if st.session_state.get("run_state") != "running":
        saved = common.load_saved_runs()
        if saved:
            st.markdown("#### Or review a saved run")
            labels = [
                f"{e.get('saved_at', '?')} · {e['result'].get('model', '?')} · "
                f"V={e['result'].get('final_V', float('nan')):.2f} · "
                f"Ah={e['result'].get('delivered_Ah', float('nan')):.2f}"
                for e in saved
            ]
            choice = st.selectbox("Saved runs", labels, key="res_saved")
            if st.button("Load into Results", key="res_load"):
                common.load_result_into_session(saved[labels.index(choice)])
                st.rerun()
    st.stop()

if "error" in last:
    st.error(f"Run failed:\n\n`{last['error']}`")
    tb = last.get("traceback", "")
    with st.expander("Traceback"):
        st.code(tb)
    st.stop()

st.success(f"Run complete in {last.get('wall_s', 0):.1f} s")

# ------------------------------------------------------------------ metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("Final voltage", f"{last.get('final_V', float('nan')):.3f} V")
c2.metric("Delivered capacity", f"{last.get('delivered_Ah', float('nan')):.2f} Ah")
c3.metric("T max", f"{last.get('Tmax_K', float('nan')):.1f} K")
c4.metric("T final", f"{last.get('T_final_K', float('nan')):.1f} K")

st.markdown("#### Config")
cfg = st.session_state.config
proto_label = f" · protocol=`{last.get('protocol_type', '?')}`" if "protocol_type" in last else ""
st.code(
    f"analysis={last.get('analysis', cfg.analysis)}{proto_label} · "
    f"{last.get('model', cfg.model_name)} "
    f"dim={last.get('dimensionality', cfg.dimensionality)} · "
    f"thermal={last.get('thermal', cfg.thermal)} · mesh={last.get('mesh', cfg.mesh)} · "
    f"{last.get('C_rate', cfg.C_rate)}C"
)

# ------------------------------------------------------------------ per-step metrics
steps = last.get("steps")
if steps:
    st.markdown("#### Per-step metrics")
    st.dataframe(
        [
            {
                "cycle": r["cycle"], "step": r["step"],
                "t_end_s": r["t_end_s"], "V_end": r["V_end"], "Ah": r["Ah"],
                "T_end_K": r.get("T_end_K", float("nan")),
            }
            for r in steps
        ],
        width="stretch", hide_index=True,
    )

# ------------------------------------------------------------------ figures
st.markdown("#### Figures")
run_dir = Path(last["run_dir"])
figs = last.get("figures", [])
step_figs = sorted(f for f in figs if f.startswith("step_"))
main_figs = [f for f in figs if not f.startswith("step_")]

if main_figs:
    cols = st.columns(min(len(main_figs), 2))
    for i, name in enumerate(main_figs):
        p = run_dir / name
        if p.is_file():
            with cols[i % 2]:
                st.image(str(p), caption=name, width="stretch")
else:
    st.caption("No figures were saved for this run.")

if step_figs:
    st.markdown("#### Per-step thermal maps")
    sel = st.selectbox("Step map", step_figs, key="res_step_sel")
    p = run_dir / sel
    if p.is_file():
        st.image(str(p), caption=sel, width="stretch")

# ------------------------------------------------------------------ V/T CSV
csv_path = run_dir / "vt.csv"
if csv_path.is_file():
    st.download_button(
        "Download V/T CSV",
        data=csv_path.read_text(encoding="utf-8"),
        file_name="vt.csv", mime="text/csv",
    )

# ------------------------------------------------------------------ save this run
c1, c2 = st.columns(2)
if c1.button("Save this run to history file"):
    common.save_run(last)
    st.success(f"Saved to {common.HISTORY_FILE}")
if c2.button("Load into Results a saved run"):
    st.session_state["res_show_saved"] = True

if st.session_state.get("res_show_saved"):
    saved = common.load_saved_runs()
    if saved:
        labels = [
            f"{e.get('saved_at', '?')} · {e['result'].get('model', '?')} · "
            f"V={e['result'].get('final_V', float('nan')):.2f} · "
            f"Ah={e['result'].get('delivered_Ah', float('nan')):.2f}"
            for e in saved
        ]
        choice = st.selectbox("Saved runs", labels, key="res_saved2")
        if st.button("Load", key="res_load2"):
            common.load_result_into_session(saved[labels.index(choice)])
            st.rerun()

hist = last.get("sizing_history", [])
if hist:
    st.markdown("#### Sizing history (Ah delivered per iteration)")
    st.caption(f"{[f'{h:.2f}' for h in hist]}")
