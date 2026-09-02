"""Results page -- metrics, interactive plot browser, data export and saved-run
review.

Shows the most recent (or a loaded) run's metrics, an interactive Plotly plot
browser (zoom/pan, swappable axes, PNG export), the per-step thermal maps and
time-series CSV exports, plus saved-run review without re-running.
"""
import csv
import io
from pathlib import Path

import numpy as np
import streamlit as st

from pouch_cell.ui import common

common.page_setup()

st.title("Results")
with common.page_body():

    @st.fragment(run_every=1.0)
    def _live_run_section() -> None:
        """While a run is in flight: draw a growing real-time voltage figure.

        Polls the worker's ``progress.json`` and ``live_vt.json`` every second
        so the user sees the voltage being plotted as the simulation runs,
        plus the current stage / cycle / step in a status line.  Keeps the
        rest of the app usable -- the page no longer blanks during a run.
        """
        import json

        import pandas as pd

        run_dir = Path(st.session_state.get("run_dir") or ".")
        prog = run_dir / "progress.json"
        data = {}
        if prog.is_file():
            try:
                data = json.loads(prog.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                data = {}

        cfg = st.session_state.config
        proto = st.session_state.protocol
        st.info("**Running…** — the voltage below plots live as the simulation "
                "runs. You can still browse the other tabs.")
        st.markdown(
            f"**Now running:** `{cfg.model_name}` · dim {cfg.dimensionality} · "
            f"{cfg.thermal} · {cfg.mesh} · protocol `{proto.type}` "
            f"({len(proto.steps)} steps × {max(1, int(proto.cycles))} cycle(s))"
        )

        lv = run_dir / "live_vt.json"
        if lv.is_file():
            try:
                lvd = json.loads(lv.read_text(encoding="utf-8"))
                t = lvd.get("t", [])
                v = lvd.get("V", [])
                if t and v:
                    st.line_chart(
                        pd.DataFrame({"Voltage [V]": v}, index=t),
                        x_label="Time [s]",
                        y_label="Voltage [V]",
                    )
                else:
                    st.caption("Waiting for live voltage…")
            except Exception:  # noqa: BLE001
                st.caption("Waiting for live voltage…")
        else:
            st.caption("Waiting for live voltage…")

        st.caption(f"`{common.status_text(data)}`")
        if st.session_state.get("run_state") != "running":
            st.rerun()

    if st.session_state.get("run_state") == "running":
        _live_run_section()
        st.stop()

    last = st.session_state.last_result
    if last is None:
        st.info("No run yet — press **Run** in the sidebar (or load a saved run).")
        if st.session_state.get("run_state") != "running":
            saved = common.load_saved_runs()
            if saved:
                st.markdown("#### Or review a saved run")
                labels = [common.saved_run_label(e) for e in saved]
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
    _M = last

    def _fmt(key: str, fmt: str = "{:.2f}", default: str = "—") -> str:
        v = _M.get(key)
        if not isinstance(v, (int, float)) or v != v:  # NaN guard
            return default
        return fmt.format(v)

    # headline row (always visible)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Final voltage", _fmt("final_V", "{:.3f} V"))
    c2.metric("Delivered capacity", _fmt("delivered_Ah", "{:.2f} Ah"))
    c3.metric("Energy (discharge)", _fmt("delivered_energy_Wh", "{:.2f} Wh"))
    c4.metric("Peak power", _fmt("peak_power_W", "{:.1f} W"))

    with st.expander("Electrical", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Initial voltage", _fmt("initial_V", "{:.3f} V"))
        c2.metric("Mean voltage", _fmt("mean_voltage_V", "{:.3f} V"))
        c3.metric("Average power", _fmt("average_power_W", "{:.1f} W"))
        c4.metric("Capacity utilisation",
                  _fmt("capacity_utilisation_pct", "{:.1f} %"))
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Discharge energy",
                  _fmt("delivered_energy_Wh", "{:.2f} Wh"))
        c2.metric("Charge energy", _fmt("charged_energy_Wh", "{:.2f} Wh"))
        c3.metric("Throughput energy",
                  _fmt("throughput_energy_Wh", "{:.2f} Wh"))
        c4.metric("Throughput capacity",
                  _fmt("throughput_capacity_Ah", "{:.2f} Ah"))

    with st.expander("Cycle & efficiency", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Discharge capacity",
                  _fmt("discharge_capacity_Ah", "{:.2f} Ah"))
        c2.metric("Charge capacity", _fmt("charge_capacity_Ah", "{:.2f} Ah"))
        c3.metric("Coulombic efficiency",
                  _fmt("coulombic_efficiency_pct", "{:.2f} %"))
        c4.metric("Round-trip energy eff.",
                  _fmt("roundtrip_energy_efficiency_pct", "{:.2f} %"))

    with st.expander("Specific & energy density", expanded=False):
        c1, c2, c3 = st.columns(3)
        c1.metric("Cell mass (est.)", _fmt("cell_mass_g", "{:.0f} g"))
        c2.metric("Specific capacity",
                  _fmt("specific_capacity_Ah_per_kg", "{:.2f} Ah/kg"))
        c3.metric("Specific energy",
                  _fmt("specific_energy_Wh_per_kg", "{:.2f} Wh/kg"))
        c1, c2, c3 = st.columns(3)
        c1.metric("Energy density",
                  _fmt("energy_density_Wh_per_L", "{:.1f} Wh/L"))
        c2.metric("Peak power density",
                  _fmt("peak_power_density_W_per_kg", "{:.1f} W/kg"))
        c3.metric("Cell volume", _fmt("cell_volume_L", "{:.3f} L"))

    with st.expander("Thermal", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("T max", _fmt("Tmax_K", "{:.1f} K"))
        c2.metric("T min", _fmt("T_min_K", "{:.1f} K"))
        c3.metric("T final", _fmt("T_final_K", "{:.1f} K"))
        c4.metric("T rise", _fmt("T_rise_K", "{:.1f} K"))

    # ------------------------------------------------------------------ plot browser
    st.markdown("#### Plot browser")
    _rd = Path(last["run_dir"]) if last.get("run_dir") else None
    _series_csv = (_rd / "series.csv") if _rd else None
    if _series_csv is None or not _series_csv.is_file():
        st.caption("No interactive plot data for this run (re-run to enable).")
    else:
        import pandas as pd
        import plotly.graph_objects as go

        _df = pd.read_csv(_series_csv)
        if _df.empty:
            st.caption("No interactive plot data for this run (re-run to enable).")
        else:
            _LABELS = {
                "time_s": "Time [s]",
                "voltage_V": "Voltage [V]",
                "current_A": "Current [A]",
                "discharge_capacity_Ah": "Discharge capacity [Ah]",
                "charge_capacity_Ah": "Charge capacity [Ah]",
                "throughput_capacity_Ah": "Throughput capacity [Ah]",
                "energy_Wh": "Energy [Wh]",
                "charge_energy_Wh": "Charge energy [Wh]",
                "throughput_energy_Wh": "Throughput energy [Wh]",
                "power_W": "Power [W]",
                "temperature_K": "Temperature [K]",
                "soc": "SOC",
                "specific_capacity_Ah_per_kg": "Specific capacity [Ah/kg]",
            }
            _opts = [c for c in _LABELS if c in _df.columns]

            def _label(c: str) -> str:
                return _LABELS.get(c, c)

            def _set_axes(x: str, y: str) -> None:
                st.session_state["pb_x"] = x
                st.session_state["pb_y"] = y

            _presets = [
                ("V vs t", "time_s", "voltage_V"),
                ("I vs t", "time_s", "current_A"),
                ("V vs Q", "discharge_capacity_Ah", "voltage_V"),
                ("V vs specific capacity",
                 "specific_capacity_Ah_per_kg", "voltage_V"),
                ("Energy vs Q", "discharge_capacity_Ah", "energy_Wh"),
                ("Power vs t", "time_s", "power_W"),
                ("T vs t", "time_s", "temperature_K"),
                ("SOC vs t", "time_s", "soc"),
            ]
            _pc = st.columns(len(_presets))
            for _col, (_lbl, _px, _py) in zip(_pc, _presets):
                with _col:
                    st.button(
                        _lbl, key=f"pb_preset_{_lbl}",
                        on_click=_set_axes, args=(_px, _py),
                        help=f"Plot {_label(_py)} vs {_label(_px)}",
                    )

            c1, c2, c3, c4 = st.columns(4)
            _x = c1.selectbox(
                "X variable", _opts,
                index=_opts.index(st.session_state["pb_x"])
                if st.session_state.get("pb_x") in _opts else 0,
                key="pb_x", format_func=_label)
            _y = c2.selectbox(
                "Y variable", _opts,
                index=_opts.index(st.session_state["pb_y"])
                if st.session_state.get("pb_y") in _opts else
                (_opts.index("voltage_V") if "voltage_V" in _opts else 0),
                key="pb_y", format_func=_label)
            _y2opts = ["(none)"] + _opts
            _y2 = c3.selectbox(
                "Secondary Y (optional)", _y2opts, index=0, key="pb_y2",
                format_func=lambda c: "(none)" if c == "(none)" else _label(c))
            _unit = c4.selectbox(
                "Time unit", ["s", "min", "h"], index=0, key="pb_unit")

            # downsample only the interactive chart (CSVs stay full resolution)
            _n = len(_df)
            _cap = 20000
            _d = _df.iloc[np.linspace(0, _n - 1, _cap).astype(int)] if _n > _cap else _df

            _scale = {"s": 1.0, "min": 60.0, "h": 3600.0}[_unit]
            _xvals = pd.to_numeric(_d[_x], errors="coerce").to_numpy()
            _xtitle = _label(_x)
            if _x == "time_s":
                _xvals = _xvals / _scale
                _xtitle = f"Time [{_unit}]"

            _fig = go.Figure()
            _fig.add_trace(go.Scatter(
                x=_xvals, y=pd.to_numeric(_d[_y], errors="coerce").to_numpy(),
                mode="lines", name=_label(_y)))
            if _y2 not in ("(none)", _y):
                _fig.add_trace(go.Scatter(
                    x=_xvals,
                    y=pd.to_numeric(_d[_y2], errors="coerce").to_numpy(),
                    mode="lines", name=_label(_y2), yaxis="y2"))
                _fig.update_layout(yaxis2=dict(
                    title=_label(_y2), overlaying="y", side="right"))
            _fig.update_layout(
                xaxis_title=_xtitle, yaxis_title=_label(_y),
                height=480, margin=dict(t=40, b=40),
                legend=dict(orientation="h", yanchor="bottom", y=1.02,
                            xanchor="right", x=1),
            )
            st.plotly_chart(
                _fig, width="stretch",
                config={"toImageButtonOptions": {"format": "png", "scale": 2},
                        "displaylogo": False,
                        "modeBarButtonsToRemove": ["lasso2d", "select2d"]},
            )
            st.caption(
                "Scroll to zoom, drag to pan, double-click to reset. The "
                "camera button downloads the current view as PNG. Presets set "
                "the X / Y dropdowns; you can swap either axis to any series."
            )

            # data export -- the two CSV options
            c1, c2 = st.columns(2)
            with c1:
                st.download_button(
                    "Download time-series CSV (key series)",
                    data=_series_csv.read_bytes(),
                    file_name="series.csv", mime="text/csv",
                )
            _vars_csv = (_rd / "variables.csv") if _rd else None
            with c2:
                if _vars_csv is not None and _vars_csv.is_file():
                    st.download_button(
                        "Download full-variables CSV",
                        data=_vars_csv.read_bytes(),
                        file_name="variables.csv", mime="text/csv",
                    )

    st.markdown("#### Config")
    cfg = st.session_state.config
    proto_label = (f" · protocol=`{last.get('protocol_type', '?')}`"
                   if "protocol_type" in last else "")
    st.code(
        f"analysis={last.get('analysis', cfg.analysis)}{proto_label} · "
        f"{last.get('model', cfg.model_name)} "
        f"dim={last.get('dimensionality', cfg.dimensionality)} · "
        f"thermal={last.get('thermal', cfg.thermal)} · mesh={last.get('mesh', cfg.mesh)} · "
        f"{last.get('C_rate', cfg.C_rate)}C"
    )
    _eff = last.get("effective_config")
    _warns = last.get("warnings") or []
    if _eff or _warns:
        with st.expander("Effective config & warnings"):
            if _eff:
                st.json(_eff)
            for _w in _warns:
                st.warning(_w)

    # ------------------------------------------------------------------ per-step metrics
    steps = last.get("steps")
    if steps:
        st.markdown("#### Per-step metrics")
        st.dataframe(
            [
                {
                    "cycle": r["cycle"], "step": r["step"],
                    "t_end_s": r["t_end_s"], "V_end": r["V_end"],
                    "I_end_A": r.get("I_end_A", float("nan")),
                    "Ah": r["Ah"], "Wh": r.get("Wh", float("nan")),
                    "T_end_K": r.get("T_end_K", float("nan")),
                    "solve_s": r.get("solve_s", float("nan")),
                }
                for r in steps
            ],
            width="stretch", hide_index=True,
        )
        st.caption(
            "`solve_s` = wall time spent solving that step (seconds); "
            "`Wh` = absolute energy processed during that step."
        )

    # ------------------------------------------------------------------ run log & timing
    _tl = last.get("timeline") or {}
    if _tl:
        with st.expander("Run log & timing", expanded=False):
            rows = [
                {"stage": "load config", "seconds": _tl.get("load_s")},
                {"stage": "model / mesh build", "seconds": _tl.get("build_s")},
                {"stage": "live preview", "seconds": _tl.get("preview_s")},
                {"stage": "solve", "seconds": _tl.get("solve_s")},
                {"stage": "post-processing & figures", "seconds": _tl.get("post_s")},
                {"stage": "total", "seconds": _tl.get("total_s")},
            ]
            rows = [r for r in rows if r["seconds"] is not None]
            st.dataframe(rows, width="stretch", hide_index=True)
            if last.get("run_dir"):
                _log = Path(last["run_dir"]) / "log.txt"
                if _log.is_file():
                    st.download_button(
                        "Download log.txt",
                        data=_log.read_text(encoding="utf-8"),
                        file_name="log.txt", mime="text/plain",
                    )

    # ------------------------------------------------------------------ figures
    st.markdown("#### Figures")
    run_dir = Path(last["run_dir"]) if last.get("run_dir") else None
    figs = last.get("figures", [])
    step_figs = sorted(f for f in figs if f.startswith("step_"))
    # the interactive plot browser above replaces the static discharge.png
    main_figs = [f for f in figs
                 if not f.startswith("step_") and f != "discharge.png"]

    if main_figs:
        cols = st.columns(min(len(main_figs), 2))
        for i, name in enumerate(main_figs):
            p = (run_dir / name) if run_dir else None
            if p is not None and p.is_file():
                with cols[i % 2]:
                    st.image(str(p), caption=name, width="stretch")
    else:
        st.caption("No figures were saved for this run.")

    if step_figs:
        st.markdown("#### Per-step thermal maps")
        sel = st.selectbox("Step map", step_figs, key="res_step_sel")
        p = (run_dir / sel) if run_dir else None
        if p is not None and p.is_file():
            st.image(str(p), caption=sel, width="stretch")

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
            labels = [common.saved_run_label(e) for e in saved]
            choice = st.selectbox("Saved runs", labels, key="res_saved2")
            if st.button("Load", key="res_load2"):
                common.load_result_into_session(saved[labels.index(choice)])
                st.rerun()

    hist = last.get("sizing_history", [])
    if hist:
        st.markdown("#### Sizing history (Ah delivered per iteration)")
        st.caption(f"{[f'{h:.2f}' for h in hist]}")
