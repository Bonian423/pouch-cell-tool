"""Protocols page -- define how the cell is run.

Single discharge / single charge / custom multi-step protocol.  Every step
ends when **any** of its end conditions fires (time / voltage / current /
temperature / capacity -- Neware-style OR semantics).  Steps can **loop back**
to an earlier step (repeat N times, optionally until a condition) and the
protocol has an optional run-level temperature stop (evaluated post-hoc, since
PyBaMM has no experiment-level temperature termination).

The active protocol is stored in ``session_state.protocol``; pressing **Run**
(footer or sidebar) launches it through the worker.
"""
import streamlit as st

from pouch_cell.config.protocol import Protocol, Step
from pouch_cell.ui import common

common.page_setup()

st.title("Protocol — run definition")
with common.page_body():
    cfg = st.session_state.config
    proto = st.session_state.protocol
    spec = st.session_state.spec

    KINDS = ["discharge", "charge", "rest", "hold"]
    COND_OPTIONS = {
        "discharge": ["Duration (s)", "Cut-off voltage (V)", "Current (A)",
                      "Temperature (°C)", "Capacity"],
        "charge": ["Duration (s)", "Cut-off voltage (V)", "Current (A)",
                   "Temperature (°C)", "Capacity"],
        "rest": ["Duration (s)", "Temperature (°C)"],
        "hold": ["Duration (s)", "Current (A)", "Temperature (°C)"],
    }
    COND_TYPE_NAMES = ["voltage", "current", "temperature", "capacity"]
    # Kind | Input mode | Value | Until | End value | Loop back to | ×N | + | ✕
    _COL_SPEC = [1.0, 1.0, 0.95, 1.0, 0.95, 1.0, 0.65, 0.55, 0.45]

    # ------------------------------------------------------------------ helpers
    def _default_step() -> dict:
        return {
            "kind": "discharge", "value_mode": "c_rate", "value": 1.0,
            "end_type": "Duration (s)", "end_value": 60.0, "end_unit": None,
            "hold_v": 4.2,
            "extra": [], "loop_to": None, "loop_count": 2, "loop_until": [],
            "show_extra": False,
        }

    def _step_to_ui(s: Step) -> dict:
        """Convert a Step back into a UI row dict (restoring a saved protocol)."""
        terms = list(s.terminations or [])
        p = terms[0] if terms else {"type": "time", "operator": ">=", "value": 60.0}
        ui = _default_step()
        ui.update({
            "kind": s.kind,
            "value_mode": ("c_rate" if s.c_rate is not None else
                           "current_A" if s.current_A is not None else "power_W"),
            "value": (s.c_rate if s.c_rate is not None else
                      s.current_A if s.current_A is not None else
                      s.power_W if s.power_W is not None else 1.0),
            "hold_v": s.hold_voltage_V or 4.2,
            "loop_to": s.loop_to, "loop_count": max(1, int(s.loop_count or 1)),
            "loop_until": [dict(c) for c in (s.loop_until or [])],
            "extra": [dict(c) for c in terms[1:]],
        })
        t = p.get("type", "time")
        if t == "time":
            ui["end_type"], ui["end_value"] = "Duration (s)", float(p.get("value", 60.0))
        elif t == "voltage":
            ui["end_type"], ui["end_value"] = "Cut-off voltage (V)", float(p.get("value", 2.5))
        elif t == "current":
            ui["end_type"], ui["end_value"] = "Current (A)", float(p.get("value", 0.05))
            if p.get("unit") == "C":  # legacy C-rate -> approx amps
                ui["end_value"] = round(float(p.get("value", 0.05)) * 9.0, 3)
        elif t == "temperature":
            ui["end_type"] = "Temperature (°C)"
            ui["end_value"] = (float(p.get("value", 25.0)) if p.get("unit") == "C"
                               else round(float(p.get("value", 298.15)) - 273.15, 2))
        elif t == "capacity":
            ui["end_type"], ui["end_value"] = "Capacity", float(p.get("value", 1.0))
            ui["end_unit"] = p.get("unit", "Ah")
        return ui

    def _migrate_step(s: dict) -> None:
        s.setdefault("value_mode", "c_rate")
        s.setdefault("value", 1.0)
        s.setdefault("hold_v", 4.2)
        s.setdefault("extra", [])
        s.setdefault("loop_to", None)
        s.setdefault("loop_count", 2)
        s.setdefault("loop_until", [])
        s.setdefault("show_extra", False)
        if "end_mode" in s and "end_type" not in s:
            em = s.pop("end_mode")
            if "Cut-off current" in em:
                s["end_type"], s["end_unit"] = "Current (A)", None
            elif "Cut-off" in em:
                s["end_type"], s["end_unit"] = "Cut-off voltage (V)", None
            else:
                s["end_type"], s["end_unit"] = "Duration (s)", None
        s.setdefault("end_type", "Duration (s)")
        s.setdefault("end_value", 60.0)
        s.setdefault("end_unit", None)

    def _add_step() -> None:
        st.session_state.proto_steps.append(_default_step())

    def _remove_step(i: int) -> None:
        steps = st.session_state.proto_steps
        if len(steps) > 1:
            del steps[i]

    def _primary_condition(s: dict) -> dict | None:
        et = s["end_type"]
        val = float(s["end_value"] or 0.0)
        kind = s["kind"]
        if et == "Duration (s)":
            return {"type": "time", "operator": ">=", "value": val}
        if et == "Cut-off voltage (V)":
            return {"type": "voltage",
                    "operator": "<=" if kind == "discharge" else ">=",
                    "value": val}
        if et == "Current (A)":
            return {"type": "current", "operator": "<=", "value": val}
        if et == "Temperature (°C)":
            return {"type": "temperature",
                    "operator": "<=" if kind == "rest" else ">=",
                    "value": val, "unit": "C"}
        if et == "Capacity":
            return {"type": "capacity", "operator": ">=", "value": val,
                    "unit": s.get("end_unit") or "Ah"}
        return None

    def _render_cond_list(s: dict, list_key: str, prefix: str) -> None:
        """Add/remove editor for the OR-ed condition list under ``list_key``."""
        items = s.setdefault(list_key, [])
        remove_i = None
        for k, c in enumerate(items):
            c = dict(c)
            r = st.columns([1.3, 0.75, 1.0, 0.9, 0.5])
            typ = c.get("type", "voltage")
            c["type"] = r[0].selectbox(
                "Type", COND_TYPE_NAMES,
                index=COND_TYPE_NAMES.index(typ) if typ in COND_TYPE_NAMES else 0,
                key=f"{prefix}_{list_key}_{k}_t", label_visibility="collapsed",
            )
            c["operator"] = r[1].selectbox(
                "Op", ["<=", ">="],
                index=0 if c.get("operator", "<=") == "<=" else 1,
                key=f"{prefix}_{list_key}_{k}_o", label_visibility="collapsed",
                help="≤ : stop when the variable falls to the value; ≥ : stop when it rises.",
            )
            c["value"] = r[2].number_input(
                "Value", min_value=0.0, max_value=1e6,
                value=float(c.get("value", 1.0)), key=f"{prefix}_{list_key}_{k}_v",
                format="%g", label_visibility="collapsed",
            )
            if c["type"] == "temperature":
                c["unit"] = r[3].selectbox(
                    "Unit", ["C", "K"], index=0 if c.get("unit", "C") == "C" else 1,
                    key=f"{prefix}_{list_key}_{k}_u", label_visibility="collapsed",
                )
            elif c["type"] == "capacity":
                c["unit"] = r[3].selectbox(
                    "Unit", ["Ah", "%"], index=0 if c.get("unit", "Ah") == "Ah" else 1,
                    key=f"{prefix}_{list_key}_{k}_u", label_visibility="collapsed",
                )
            else:
                r[3].caption("")
            if r[4].button("✕", key=f"{prefix}_{list_key}_{k}_rm"):
                remove_i = k
            items[k] = c
        if remove_i is not None:
            del items[remove_i]
        if st.button(f"+ Add condition", key=f"{prefix}_{list_key}_add"):
            items.append({"type": "voltage", "operator": "<=", "value": 1.0})

    if "proto_steps" not in st.session_state:
        if proto.type == "custom" and proto.steps:
            st.session_state.proto_steps = [_step_to_ui(s) for s in proto.steps]
        else:
            st.session_state.proto_steps = [_default_step()]
    for _s in st.session_state.proto_steps:
        _migrate_step(_s)

    # ------------------------------------------------------------------ type
    p_type = st.radio(
        "Run type",
        ["Single discharge", "Single charge", "Custom multi-step"],
        index={"discharge": 0, "charge": 1, "custom": 2}.get(proto.type, 2),
        horizontal=True, key="p_type_radio",
    )
    p_type_id = {"Single discharge": "discharge",
                 "Single charge": "charge",
                 "Custom multi-step": "custom"}[p_type]

    # protocol options (custom branch overwrites these via widgets)
    _cycles = int(proto.cycles)
    _period = proto.period or ""
    _termination = ", ".join(proto.termination)
    _temperature = float(proto.temperature_K or 0.0)
    _t_stop = (float(proto.temperature_stop) - 273.15) if proto.temperature_stop else 0.0
    _t_src = proto.temperature_source or "volume_averaged"

    # ------------------------------------------------------------------ builders
    custom_steps: list[Step] = []

    if p_type_id == "discharge":
        c1, c2 = st.columns(2)
        c_rate = c1.number_input(
            "Discharge C-rate", 0.05, 10.0, 1.0, 0.05, key="pd_crate",
        )
        end_mode = c2.radio(
            "End condition", ["Duration (s)", "Cut-off voltage (V)"],
            horizontal=True, key="pd_end",
        )
        end_val = st.number_input(
            "Duration (s) or cut-off (V)",
            min_value=0.0, max_value=1e6,
            value=60.0 if "Duration" in end_mode else spec.lower_cutoff_V,
            step=10.0, key="pd_endval",
        )
        terms = ([{"type": "time", "operator": ">=", "value": end_val}]
                 if "Duration" in end_mode else
                 [{"type": "voltage", "operator": "<=", "value": end_val}])
        custom_steps = [Step(kind="discharge", c_rate=c_rate, terminations=terms)]

    elif p_type_id == "charge":
        c1, c2, c3 = st.columns(3)
        c_rate = c1.number_input("Charge C-rate", 0.05, 10.0, 0.5, 0.05, key="pc_crate")
        upper = c2.number_input(
            "Upper cut-off (V)", 3.0, 4.5, spec.upper_cutoff_V, 0.05, key="pc_vmax",
        )
        cv_hold = c3.checkbox("CV hold", value=True, key="pc_cv")
        c1b, c2b, c3b = st.columns(3)
        cv_cutoff = c1b.number_input(
            "CV end current (C)", 0.01, 1.0, 0.05, 0.01, key="pc_cvc",
        )
        rest = c2b.number_input(
            "Rest after (s, 0 = none)", 0.0, 3600.0, 0.0, 10.0, key="pc_rest",
        )
        custom_steps = [
            Step(kind="charge", c_rate=c_rate,
                 terminations=[{"type": "voltage", "operator": ">=", "value": upper}])
        ]
        if cv_hold:
            custom_steps.append(Step(
                kind="hold", hold_voltage_V=upper,
                terminations=[{"type": "current", "operator": "<=",
                               "value": cv_cutoff, "unit": "C"}],
            ))
        if rest > 0:
            custom_steps.append(Step(
                kind="rest",
                terminations=[{"type": "time", "operator": ">=", "value": rest}],
            ))

    else:  # custom multi-step
        st.markdown("#### Steps")
        steps = st.session_state.proto_steps

        # fixed-height header row so every step row aligns regardless of label text
        hdr = st.columns(_COL_SPEC)
        hdr[0].markdown("**Kind**")
        hdr[1].markdown("**Input mode**")
        hdr[2].markdown("**Value**")
        hdr[3].markdown("**Until**", help="First end condition to fire stops the step")
        hdr[4].markdown("**End value**")
        hdr[5].markdown("**Loop back to**",
                        help="After this step, jump back to an earlier step and "
                             "repeat the block ×N times.")
        hdr[6].markdown("**×N**")
        hdr[7].markdown("")
        hdr[8].markdown("")

        for i, s in enumerate(steps):
            cols = st.columns(_COL_SPEC)
            s["kind"] = cols[0].selectbox(
                "Kind", KINDS, index=KINDS.index(s["kind"]), key=f"ps_kind_{i}",
                label_visibility="collapsed",
                help="Step type: constant-current / constant-voltage / rest.",
            )
            if s["kind"] in ("discharge", "charge"):
                s["value_mode"] = cols[1].selectbox(
                    "Mode", ["c_rate", "current_A", "power_W"],
                    index=["c_rate", "current_A", "power_W"].index(s["value_mode"]),
                    key=f"ps_vm_{i}", label_visibility="collapsed",
                    help="Input mode: C-rate, absolute current (A) or power (W). "
                         "The sign is set by the step kind.",
                )
                s["value"] = cols[2].number_input(
                    "Value", min_value=0.0, max_value=1e6, value=float(s["value"]),
                    key=f"ps_val_{i}", format="%g", label_visibility="collapsed",
                    help="Magnitude of the input.",
                )
            elif s["kind"] == "hold":
                cols[1].caption("")
                s["hold_v"] = cols[2].number_input(
                    "Hold voltage (V)", 3.0, 4.5, float(s["hold_v"] or 4.2),
                    key=f"ps_hv_{i}", label_visibility="collapsed",
                    help="Constant-voltage (CV) hold level.",
                )
            else:  # rest
                cols[1].caption("Rest —")
                cols[2].caption("zero current")

            opts = COND_OPTIONS[s["kind"]]
            if s["end_type"] not in opts:
                s["end_type"] = opts[0]
            s["end_type"] = cols[3].selectbox(
                "Until", opts, index=opts.index(s["end_type"]), key=f"ps_em_{i}",
                label_visibility="collapsed",
                help="End condition — the step stops when ANY condition fires "
                     "(OR semantics). Extra conditions go in the per-step editor.",
            )
            s["end_value"] = cols[4].number_input(
                "End value", min_value=0.0, max_value=1e6,
                value=float(s["end_value"] or 0.0), key=f"ps_ev_{i}", format="%g",
                label_visibility="collapsed",
            )

            # loop: jump back to an earlier step + repeat count (in the row)
            loop_opts = [None] + list(range(i))
            _cur = s.get("loop_to")
            _cur = _cur if _cur in loop_opts else None
            s["loop_to"] = cols[5].selectbox(
                "Loop back to", loop_opts, index=loop_opts.index(_cur),
                format_func=lambda v: "— no loop —" if v is None else f"Step {v + 1}",
                key=f"ps_{i}_loopto", label_visibility="collapsed",
                help="After this step, jump back to the chosen earlier step and "
                     "repeat the block (total times set in ×N).",
            )
            s["loop_count"] = cols[6].number_input(
                "×N", min_value=1, max_value=100,
                value=int(s.get("loop_count", 2) or 2),
                key=f"ps_{i}_loopn", label_visibility="collapsed",
                help="Total number of times the loop block runs (1 = no loop).",
            )

            if cols[7].button("+", key=f"ps_plus_{i}",
                              help="Extra end conditions & loop exit"):
                s["show_extra"] = not s.get("show_extra", False)
            if cols[8].button("✕", key=f"ps_rm_{i}", on_click=_remove_step,
                              args=(i,)):
                pass

            if s.get("show_extra"):
                with st.expander(f"Step {i + 1} — extra conditions & loop exit",
                                 expanded=True):
                    st.markdown("**Extra end conditions** (OR-ed with the main one)")
                    _render_cond_list(s, "extra", f"ps{i}")
                    if s.get("loop_to") is not None:
                        st.markdown("**Loop exit condition** (post-hoc; stops the "
                                    "loop early — first to fire wins)")
                        _render_cond_list(s, "loop_until", f"ps{i}lu")

        st.button("+ Add step", on_click=_add_step)
        st.caption(
            "Steps repeat for every cycle. **Loop**: pick an earlier step in "
            "'Loop back to' and set ×N (total times the block runs; 1 = no "
            "loop). The last ✕ is disabled to keep ≥1 step."
        )

        c1, c2, c3 = st.columns(3)
        _cycles = c1.number_input("Cycles", 1, 1000, int(_cycles), 1, key="pc_cycles")
        _period = c2.text_input(
            "Output period", value=_period, key="pc_period",
            help="e.g. '10 seconds' / '1 minute'; blank = auto.",
        )
        _termination = c3.text_input(
            "Termination", value=_termination, key="pc_term",
            help="Comma-separated, e.g. '80% capacity' / '4.25 V' (capacity / "
                 "voltage / time only).",
        )
        t1, t2, t3 = st.columns(3)
        _temperature = t1.number_input(
            "Experiment T (K)", 0.0, 400.0, _temperature, 0.5, key="pc_temp",
            help="0 = use the model's initial temperature.",
        )
        _t_stop = t2.number_input(
            "Stop run at T (°C)", 0.0, 200.0, _t_stop, 1.0, key="pc_tstop",
            help="Run-level safety stop when the cell temperature reaches this "
                 "value (post-hoc — PyBaMM can't terminate on temperature).",
        )
        _t_src = t3.selectbox(
            "Temperature source", ["volume_averaged", "hot_spot"],
            index=0 if _t_src == "volume_averaged" else 1, key="pc_tsrc",
            help="Volume-averaged (works in every model) or hot-spot = max over "
                 "the 2+1D y-z field (needs 2+1D `x-lumped`).",
        )

        for i, s in enumerate(steps):
            terms = []
            p = _primary_condition(s)
            if p:
                terms.append(p)
            terms += [dict(c) for c in s.get("extra", []) if c.get("type")]
            custom_steps.append(Step(
                kind=s["kind"],
                c_rate=s["value"] if s["kind"] in ("discharge", "charge")
                       and s["value_mode"] == "c_rate" else None,
                current_A=s["value"] if s["kind"] in ("discharge", "charge")
                          and s["value_mode"] == "current_A" else None,
                power_W=s["value"] if s["kind"] in ("discharge", "charge")
                        and s["value_mode"] == "power_W" else None,
                hold_voltage_V=s["hold_v"] if s["kind"] == "hold" else None,
                terminations=terms,
                loop_to=s.get("loop_to"),
                loop_count=int(s.get("loop_count", 1) or 1),
                loop_until=[dict(c) for c in s.get("loop_until", []) if c.get("type")],
            ))

    # ------------------------------------------------------------------ common options
    st.markdown("#### Maps & output")
    c1, c2, c3 = st.columns(3)
    thermal_maps = c1.checkbox(
        "Save thermal maps (end of each step)",
        value=bool(proto.thermal_maps), key="pc_maps",
    )
    step_map_mode = c2.radio(
        "Per-step map mode", ["every", "cycle_last"],
        index=0 if proto.step_map_mode == "every" else 1,
        horizontal=True, key="pc_mapmode",
    )
    c3.caption("Maps require a 2+1D model (auto-selected).")

    # ------------------------------------------------------------------ protocol object
    new_proto = Protocol(
        type=p_type_id,
        steps=custom_steps,
        cycles=int(_cycles) if p_type_id == "custom" else 1,
        period=(_period.strip() or None) if p_type_id == "custom" else None,
        termination=([t.strip() for t in _termination.split(",") if t.strip()]
                     if p_type_id == "custom" else []),
        temperature_K=(_temperature if p_type_id == "custom" and _temperature > 0 else None),
        thermal_maps=bool(thermal_maps),
        step_map_mode=step_map_mode,
        temperature_stop=(_t_stop + 273.15) if p_type_id == "custom" and _t_stop > 0 else None,
        temperature_source=_t_src if p_type_id == "custom" else "volume_averaged",
    )
    st.session_state.protocol = new_proto

    # ------------------------------------------------------------------ effective readout
    if thermal_maps:
        # show what the run will ACTUALLY use (thermal maps force SPM 2+1D x-lumped)
        st.info(common.effective_readout(cfg, new_proto))
    elif cfg.model_name in ("DFN", "SPMe") and cfg.dimensionality == 2:
        st.warning(
            "DFN/SPMe on the 2+1D mesh are DAE-limited to a few seconds "
            "(`IDA_ERR_FAIL`). For longer multi-step runs, **SPM** is the "
            "reliable choice."
        )

    st.divider()
    _blocked = common.hard_blocked()
    if _blocked:
        st.error("Run is blocked — fix these before continuing:")
        for _v in _blocked:
            st.caption("• " + _v.message)

    c1, c2 = st.columns([1, 2])
    if c1.button("Validate & preview", width="stretch", disabled=bool(_blocked)):
        try:
            flat, _infos = new_proto.expand()
            cyc = new_proto.experiment_cycles(
                spec.capacity_Ah, new_proto.temperature_source
            )
            st.session_state["proto_preview"] = {
                "steps": [f"{j + 1}. {s.to_string(spec.capacity_Ah)}"
                          for j, s in enumerate(flat)],
                "n_cycles": len(cyc),
                "temperature_K": new_proto.temperature_K,
                "termination": new_proto.termination,
                "period": new_proto.period,
                "temperature_stop": new_proto.temperature_stop,
                "temperature_source": new_proto.temperature_source,
            }
            st.session_state.pop("proto_preview_error", None)
        except Exception as err:  # noqa: BLE001
            st.session_state["proto_preview_error"] = repr(err)
            st.session_state.pop("proto_preview", None)
    _preview_err = st.session_state.get("proto_preview_error")
    if _preview_err:
        st.error(f"Couldn't build the protocol preview: `{_preview_err}`")
    preview = st.session_state.get("proto_preview")
    if preview:
        st.markdown("**Parsed steps (one cycle, loops unrolled)**")
        st.code("\n".join(preview["steps"]))
        st.caption(
            f"{preview['n_cycles']} cycle(s) · period={preview['period']} · "
            f"T={preview['temperature_K']} K · termination={preview['termination']} · "
            f"stop@T={preview['temperature_stop']} K · src={preview['temperature_source']}"
        )

    # keep the legacy C-rate/duration in sync so the Results/History summary reads well
    if p_type_id == "discharge" and custom_steps:
        cfg.C_rate = custom_steps[0].c_rate or cfg.C_rate
        cfg.duration_s = custom_steps[0].duration_s or cfg.duration_s

    if c2.button("Run protocol", type="primary", width="stretch",
                 disabled=bool(_blocked)):
        common.launch_run()
        st.rerun()

