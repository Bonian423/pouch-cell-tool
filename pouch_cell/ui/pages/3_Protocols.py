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

from pouch_cell.config import io as preset_io
from pouch_cell.config.protocol import Protocol, Step
from pouch_cell.ui import common

common.page_setup()

st.title("Protocol — run definition")
with common.page_body():
    cfg = st.session_state.config
    proto = st.session_state.protocol
    spec = st.session_state.spec

    KINDS = ["discharge", "charge", "rest", "hold", "loop"]
    COND_OPTIONS = {
        "discharge": ["Duration (s)", "Cut-off voltage (V)", "Current (A)",
                      "Temperature (°C)", "Capacity"],
        "charge": ["Duration (s)", "Cut-off voltage (V)", "Current (A)",
                    "Temperature (°C)", "Capacity"],
        "rest": ["Duration (s)", "Temperature (°C)"],
        "hold": ["Duration (s)", "Current (A)", "Temperature (°C)"],
    }
    COND_TYPE_NAMES = ["voltage", "current", "temperature", "capacity"]
    # run-level condition types + display labels
    RUN_COND_TYPES = ["ambient_temp", "temp_limit", "voltage", "capacity",
                      "time", "current"]
    RUN_COND_LABELS = {
        "ambient_temp": "Ambient / experiment temperature",
        "temp_limit": "Cell temperature limit",
        "voltage": "Voltage limit",
        "capacity": "Capacity",
        "time": "Time",
        "current": "Current",
    }
    # Type | Mode / Loop target | Value / ×N | Until | End value | + | ✕
    _COL_SPEC = [1.0, 1.0, 0.95, 1.0, 0.95, 0.55, 0.45]

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

    def _step_from_ui(s: dict) -> Step:
        """Build a :class:`Step` from a UI row dict (editor + save share this)."""
        if s["kind"] == "loop":
            return Step(
                kind="loop",
                loop_to=s.get("loop_to"),
                loop_count=int(s.get("loop_count", 1) or 1),
                loop_until=[dict(c) for c in s.get("loop_until", [])
                            if c.get("type")],
            )
        terms = []
        p = _primary_condition(s)
        if p:
            terms.append(p)
        terms += [dict(c) for c in s.get("extra", []) if c.get("type")]
        return Step(
            kind=s["kind"],
            c_rate=s["value"] if s["kind"] in ("discharge", "charge")
                   and s["value_mode"] == "c_rate" else None,
            current_A=s["value"] if s["kind"] in ("discharge", "charge")
                      and s["value_mode"] == "current_A" else None,
            power_W=s["value"] if s["kind"] in ("discharge", "charge")
                    and s["value_mode"] == "power_W" else None,
            hold_voltage_V=s["hold_v"] if s["kind"] == "hold" else None,
            terminations=terms,
        )

    def _default_run_condition() -> dict:
        return {"type": "voltage", "operator": "<=", "value": 2.5,
                "unit": None, "source": "volume_averaged"}

    def _render_run_conditions(items: list, prefix: str) -> None:
        """Add/remove editor for the run-level termination/boundary list."""
        remove_i = None
        for k, c in enumerate(items):
            c = dict(c)
            typ = c.get("type", "voltage")
            if typ not in RUN_COND_TYPES:
                typ = "voltage"
            r = st.columns([1.35, 0.7, 0.6, 0.85, 0.8, 0.5])
            c["type"] = r[0].selectbox(
                "Type", RUN_COND_TYPES, index=RUN_COND_TYPES.index(typ),
                format_func=lambda t: RUN_COND_LABELS.get(t, t),
                key=f"{prefix}_rc_{k}_t", label_visibility="collapsed",
            )
            typ = c["type"]
            if typ == "ambient_temp":
                c["operator"] = ">="
                c["value"] = r[1].number_input(
                    "Value", 0.0, 1e6, float(c.get("value", 298.15)),
                    key=f"{prefix}_rc_{k}_v", format="%g",
                    label_visibility="collapsed",
                )
                c["unit"] = r[2].selectbox(
                    "Unit", ["K", "C"],
                    index=0 if c.get("unit", "K") == "K" else 1,
                    key=f"{prefix}_rc_{k}_u", label_visibility="collapsed",
                )
                r[3].caption("boundary")
                r[4].caption("")
            elif typ == "temp_limit":
                c["source"] = r[1].selectbox(
                    "Source", ["volume_averaged", "hot_spot"],
                    index=0 if c.get("source", "volume_averaged")
                       == "volume_averaged" else 1,
                    key=f"{prefix}_rc_{k}_src", label_visibility="collapsed",
                )
                c["operator"] = r[2].selectbox(
                    "Op", ["<=", ">="],
                    index=0 if c.get("operator", ">=") == "<=" else 1,
                    key=f"{prefix}_rc_{k}_o", label_visibility="collapsed",
                )
                c["value"] = r[3].number_input(
                    "Value", 0.0, 1e6, float(c.get("value", 50.0)),
                    key=f"{prefix}_rc_{k}_v", format="%g",
                    label_visibility="collapsed",
                )
                c["unit"] = r[4].selectbox(
                    "Unit", ["C", "K"],
                    index=0 if c.get("unit", "C") == "C" else 1,
                    key=f"{prefix}_rc_{k}_u", label_visibility="collapsed",
                )
            elif typ == "voltage":
                c["operator"] = r[1].selectbox(
                    "Op", ["<=", ">="],
                    index=0 if c.get("operator", "<=") == "<=" else 1,
                    key=f"{prefix}_rc_{k}_o", label_visibility="collapsed",
                )
                c["value"] = r[2].number_input(
                    "Value", 0.0, 1e6, float(c.get("value", 2.5)),
                    key=f"{prefix}_rc_{k}_v", format="%g",
                    label_visibility="collapsed",
                )
                r[3].caption("V")
                r[4].caption("")
            elif typ == "capacity":
                c["operator"] = r[1].selectbox(
                    "Op", [">=", "<="],
                    index=0 if c.get("operator", ">=") == ">=" else 1,
                    key=f"{prefix}_rc_{k}_o", label_visibility="collapsed",
                )
                c["value"] = r[2].number_input(
                    "Value", 0.0, 1e6, float(c.get("value", 80.0)),
                    key=f"{prefix}_rc_{k}_v", format="%g",
                    label_visibility="collapsed",
                )
                c["unit"] = r[3].selectbox(
                    "Unit", ["%", "Ah"],
                    index=0 if c.get("unit", "%") == "%" else 1,
                    key=f"{prefix}_rc_{k}_u", label_visibility="collapsed",
                )
                r[4].caption("")
            elif typ == "time":
                c["operator"] = ">="
                c["value"] = r[1].number_input(
                    "Value", 0.0, 1e6, float(c.get("value", 3600.0)),
                    key=f"{prefix}_rc_{k}_v", format="%g",
                    label_visibility="collapsed",
                )
                r[2].caption("seconds")
                r[3].caption("")
                r[4].caption("")
            else:  # current
                c["operator"] = r[1].selectbox(
                    "Op", ["<=", ">="],
                    index=0 if c.get("operator", "<=") == "<=" else 1,
                    key=f"{prefix}_rc_{k}_o", label_visibility="collapsed",
                )
                c["value"] = r[2].number_input(
                    "Value", 0.0, 1e6, float(c.get("value", 0.05)),
                    key=f"{prefix}_rc_{k}_v", format="%g",
                    label_visibility="collapsed",
                )
                c["unit"] = r[3].selectbox(
                    "Unit", ["A", "C"],
                    index=0 if c.get("unit", "A") == "A" else 1,
                    key=f"{prefix}_rc_{k}_u", label_visibility="collapsed",
                )
                r[4].caption("")
            if r[5].button("✕", key=f"{prefix}_rc_{k}_rm"):
                remove_i = k
            items[k] = c
        if remove_i is not None:
            del items[remove_i]
        if st.button("+ Add condition", key=f"{prefix}_rc_add"):
            items.append(_default_run_condition())

    if "proto_steps" not in st.session_state:
        if proto.type == "custom" and proto.steps:
            st.session_state.proto_steps = [_step_to_ui(s) for s in proto.steps]
        else:
            st.session_state.proto_steps = [_default_step()]
    for _s in st.session_state.proto_steps:
        _migrate_step(_s)
    if "proto_run_conditions" not in st.session_state:
        st.session_state.proto_run_conditions = [
            dict(c) for c in (proto.run_conditions or [])
        ]
    if "pc_default_src" not in st.session_state:
        st.session_state.pc_default_src = (
            proto.default_temperature_source or "volume_averaged"
        )

    # ------------------------------------------------------------------ save/load
    with st.expander("Save / load protocol", expanded=False):
        c1, c2 = st.columns([1, 1.6])
        _pname = c1.text_input("Protocol name", key="pp_name")
        if c1.button("Save protocol", width="stretch") and _pname.strip():
            from pouch_cell.config.protocol import Protocol as _Proto

            _cur = st.session_state.protocol
            _steps = ([_step_from_ui(s) for s in st.session_state.proto_steps]
                      if _cur.type == "custom" else _cur.steps)
            _saved = _Proto(
                type=_cur.type,
                steps=_steps,
                cycles=1,
                period=(st.session_state.get("pc_period") or _cur.period),
                thermal_maps=bool(st.session_state.get("pc_maps", _cur.thermal_maps)),
                step_map_mode=st.session_state.get("pc_mapmode", _cur.step_map_mode),
                default_temperature_source=st.session_state.get(
                    "pc_default_src", "volume_averaged"),
                run_conditions=[dict(c) for c in st.session_state.proto_run_conditions
                                if c.get("type")],
            )
            preset_io.save_protocol(_pname.strip(), _saved)
            st.success(f"Saved protocol `{_pname.strip()}`.")
            st.rerun()
        saved_protos = preset_io.list_saved_protocols()
        if saved_protos:
            _psel = c2.selectbox(
                "Saved protocols", ["— select —"] + saved_protos, key="pp_sel",
            )
            b1, b2 = st.columns(2)
            if b1.button("Load", width="stretch") and _psel != "— select —":
                from pouch_cell.config.protocol import Protocol as _Proto

                _loaded = _Proto.from_dict(preset_io.load_protocol(_psel))
                st.session_state.protocol = _loaded
                st.session_state.proto_steps = (
                    [_step_to_ui(s) for s in _loaded.steps] if _loaded.steps
                    else [_default_step()]
                )
                st.session_state.proto_run_conditions = [
                    dict(c) for c in (_loaded.run_conditions or [])
                ]
                st.session_state.pc_default_src = (
                    _loaded.default_temperature_source or "volume_averaged"
                )
                st.rerun()
            if b2.button("Delete", width="stretch") and _psel != "— select —":
                preset_io.delete_protocol(_psel)
                st.rerun()
        else:
            c2.caption("No saved protocols yet.")

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
    _cycles = 1
    _period = proto.period or ""

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
        hdr[0].markdown("**Type**")
        hdr[1].markdown("**Mode / Loop target**")
        hdr[2].markdown("**Value / ×N**")
        hdr[3].markdown("**Until**",
                        help="First end condition to fire stops the step.")
        hdr[4].markdown("**End value**")
        hdr[5].markdown("")
        hdr[6].markdown("")

        for i, s in enumerate(steps):
            cols = st.columns(_COL_SPEC)
            _kind = s["kind"] if s["kind"] in KINDS else "discharge"
            s["kind"] = cols[0].selectbox(
                "Type", KINDS, index=KINDS.index(_kind), key=f"ps_kind_{i}",
                label_visibility="collapsed",
                help="Step type: constant-current / constant-voltage / rest, "
                     "or a **loop** marker (jump back to an earlier step and "
                     "repeat the block ×N times).",
            )
            if s["kind"] == "loop":
                # pure loop marker row: no action, just jump + repeat
                _non_loop = [j for j in range(i) if steps[j]["kind"] != "loop"]
                if not _non_loop:
                    cols[1].caption("add a step")
                    cols[2].caption("")
                else:
                    _cur = s.get("loop_to")
                    _cur = _cur if _cur in _non_loop else _non_loop[-1]
                    s["loop_to"] = cols[1].selectbox(
                        "Loop back to", _non_loop, index=_non_loop.index(_cur),
                        format_func=lambda v: f"Step {v + 1}",
                        key=f"ps_{i}_loopto", label_visibility="collapsed",
                        help="After this step, jump back to the chosen earlier "
                             "step and repeat the block ×N times.",
                    )
                    s["loop_count"] = cols[2].number_input(
                        "×N", min_value=1, max_value=100,
                        value=int(s.get("loop_count", 2) or 2),
                        key=f"ps_{i}_loopn", label_visibility="collapsed",
                        help="Total number of times the loop block runs "
                             "(1 = no loop).",
                    )
                cols[3].caption("loop")
                cols[4].caption("")
            else:
                if s["kind"] in ("discharge", "charge"):
                    s["value_mode"] = cols[1].selectbox(
                        "Mode", ["c_rate", "current_A", "power_W"],
                        index=["c_rate", "current_A", "power_W"].index(s["value_mode"]),
                        key=f"ps_vm_{i}", label_visibility="collapsed",
                        help="Input mode: C-rate, absolute current (A) or power (W). "
                             "The sign is set by the step type.",
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
                s["loop_to"] = None
                s["loop_until"] = []

            if cols[5].button("+", key=f"ps_plus_{i}",
                              help="Extra end conditions & loop exit"):
                s["show_extra"] = not s.get("show_extra", False)
            if cols[6].button("✕", key=f"ps_rm_{i}", on_click=_remove_step,
                              args=(i,)):
                pass

            if s.get("show_extra"):
                if s["kind"] == "loop":
                    with st.expander(f"Step {i + 1} — loop exit condition",
                                     expanded=True):
                        st.markdown("**Loop exit condition** (post-hoc; stops the "
                                    "loop early — first to fire wins)")
                        _render_cond_list(s, "loop_until", f"ps{i}lu")
                else:
                    with st.expander(f"Step {i + 1} — extra conditions",
                                     expanded=True):
                        st.markdown("**Extra end conditions** (OR-ed with the main one)")
                        _render_cond_list(s, "extra", f"ps{i}")

        st.button("+ Add step", on_click=_add_step)
        st.caption(
            "**Loop**: add a step and set its Type to **loop** — it jumps back "
            "to the chosen earlier step and repeats that block ×N times (1 = no "
            "loop). Loop rows are never solved themselves. Add a loop targeting "
            "step 1 to cycle the whole protocol."
        )

        _period = st.text_input(
            "Output period", value=_period, key="pc_period",
            help="e.g. '10 seconds' / '1 minute'; blank = auto.",
        )

        # ---- run-level conditions (termination / boundary) ----------------
        st.markdown("#### Run conditions (termination / boundary)")
        st.caption(
            "Conditions that set the environment or stop the whole run. "
            "Temperature / current / capacity-Ah are checked at step ends "
            "(post-hoc); voltage / capacity-% / time also stop the solver "
            "cleanly. First to fire wins."
        )
        st.selectbox(
            "Default temperature source",
            ["volume_averaged", "hot_spot"],
            index=0 if st.session_state.get("pc_default_src", "volume_averaged")
                       == "volume_averaged" else 1,
            key="pc_default_src",
            help="Used by per-step temperature conditions (each cell-temperature "
                 "limit below can override). Hot-spot = max over the 2+1D y-z "
                 "field (needs 2+1D `x-lumped`).",
        )
        run_conds = st.session_state.proto_run_conditions
        _render_run_conditions(run_conds, "pcrc")

        custom_steps = [_step_from_ui(s) for s in steps]

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
        cycles=1,
        period=(_period.strip() or None) if p_type_id == "custom" else None,
        thermal_maps=bool(thermal_maps),
        step_map_mode=step_map_mode,
        default_temperature_source=(
            st.session_state.get("pc_default_src", "volume_averaged")
            if p_type_id == "custom" else "volume_averaged"),
        run_conditions=([dict(c) for c in run_conds if c.get("type")]
                        if p_type_id == "custom" else []),
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
                spec.capacity_Ah, new_proto.default_temperature_source
            )
            st.session_state["proto_preview"] = {
                "steps": [f"{j + 1}. {s.to_string(spec.capacity_Ah)}"
                          for j, s in enumerate(flat)],
                "n_cycles": len(cyc),
                "period": new_proto.period,
                "n_conditions": len(new_proto.run_conditions),
                "default_temperature_source": new_proto.default_temperature_source,
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
            f"{preview['n_conditions']} run condition(s) · "
            f"src={preview['default_temperature_source']}"
        )

    # keep the legacy C-rate/duration in sync so the Results/History summary reads well
    if p_type_id == "discharge" and custom_steps:
        cfg.C_rate = custom_steps[0].c_rate or cfg.C_rate
        cfg.duration_s = custom_steps[0].duration_s or cfg.duration_s

    if c2.button("Run protocol", type="primary", width="stretch",
                 disabled=bool(_blocked)):
        common.launch_run()
        st.rerun()

