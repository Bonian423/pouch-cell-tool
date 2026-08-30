"""Protocols page -- define how the cell is run.

Single discharge / single charge / custom multi-step protocol built from the
PyBaMM ``Experiment`` step strings:

    "Discharge at 1C for 10 minutes"
    "Charge at 0.5 C until 4.2 V"
    "Rest for 5 minutes"
    "Hold at 4.2 V until 0.45 A"

The active protocol is stored in ``session_state.protocol``; pressing **Run**
(footer or sidebar) launches it through the worker.
"""
import streamlit as st

from pouch_cell.config.protocol import Protocol, Step
from pouch_cell.ui import common

common.init_state()
common.render_sidebar()

st.title("Protocol — run definition")
cfg = st.session_state.config
proto = st.session_state.protocol
spec = st.session_state.spec

# ------------------------------------------------------------------ helpers
def _default_step() -> dict:
    return {
        "kind": "discharge", "value_mode": "c_rate", "value": 1.0,
        "end_mode": "Duration (s)", "end_value": 60.0,
        "hold_v": 4.2, "cutoff_c": 0.05,
    }


def _add_step() -> None:
    st.session_state.proto_steps.append(_default_step())


def _remove_step(i: int) -> None:
    steps = st.session_state.proto_steps
    if len(steps) > 1:
        del steps[i]


if "proto_steps" not in st.session_state:
    st.session_state.proto_steps = [_default_step()]

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
    custom_steps = [
        Step(
            kind="discharge", c_rate=c_rate,
            duration_s=end_val if "Duration" in end_mode else None,
            cutoff_V=end_val if "Cut-off" in end_mode else None,
        )
    ]

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
    custom_steps = [Step(kind="charge", c_rate=c_rate, cutoff_V=upper)]
    if cv_hold:
        custom_steps.append(Step(kind="hold", hold_voltage_V=upper,
                                 cutoff_current_C=cv_cutoff))
    if rest > 0:
        custom_steps.append(Step(kind="rest", duration_s=rest))

else:  # custom multi-step
    st.markdown("#### Steps")
    steps = st.session_state.proto_steps
    for i, s in enumerate(steps):
        cols = st.columns([1.1, 1.1, 1.1, 1.2, 0.6])
        s["kind"] = cols[0].selectbox(
            "Kind", ["discharge", "charge", "rest", "hold"],
            index=["discharge", "charge", "rest", "hold"].index(s["kind"]),
            key=f"ps_kind_{i}",
        )
        if s["kind"] in ("discharge", "charge"):
            s["value_mode"] = cols[1].selectbox(
                "Value", ["c_rate", "current_A", "power_W"],
                index=["c_rate", "current_A", "power_W"].index(s["value_mode"]),
                key=f"ps_vm_{i}",
            )
            s["value"] = cols[2].number_input(
                {"c_rate": "C-rate", "current_A": "Current (A)",
                 "power_W": "Power (W)"}[s["value_mode"]],
                min_value=0.0, max_value=1e6, value=float(s["value"]),
                key=f"ps_val_{i}", format="%g",
            )
            s["end_mode"] = cols[3].selectbox(
                "Until", ["Duration (s)", "Cut-off (V)"],
                index=0 if s["end_mode"].startswith("Duration") else 1,
                key=f"ps_em_{i}",
            )
            s["end_value"] = cols[3].number_input(
                "Value", min_value=0.0, max_value=1e6,
                value=float(s["end_value"]), key=f"ps_ev_{i}", format="%g",
                label_visibility="collapsed",
            )
        elif s["kind"] == "rest":
            s["end_value"] = cols[3].number_input(
                "Rest duration (s)", min_value=0.0, max_value=1e6,
                value=float(s["end_value"] or 60.0), key=f"ps_ev_{i}", format="%g",
            )
            s["end_mode"] = "Duration (s)"
        else:  # hold
            s["hold_v"] = cols[1].number_input(
                "Hold voltage (V)", 3.0, 4.5, float(s["hold_v"] or 4.2),
                key=f"ps_hv_{i}",
            )
            s["end_mode"] = cols[2].selectbox(
                "Until", ["Cut-off current (C)", "Duration (s)"],
                index=0 if s["end_mode"].startswith("Cut-off current") else 1,
                key=f"ps_em_{i}",
            )
            s["end_value"] = cols[3].number_input(
                "Value", min_value=0.0, max_value=1e6,
                value=float(s["end_value"] or 0.05),
                key=f"ps_ev_{i}", format="%g",
            )
        cols[4].button("Remove", key=f"ps_rm_{i}", on_click=_remove_step, args=(i,))

    st.button("+ Add step", on_click=_add_step)
    st.caption("Steps repeat for every cycle. Remove the last button keeps ≥1 step.")

    c1, c2, c3 = st.columns(3)
    _cycles = c1.number_input(
        "Cycles", 1, 1000, int(_cycles), 1, key="pc_cycles"
    )
    _period = c2.text_input(
        "Output period (e.g. '10 seconds' / '1 minute', blank = auto)",
        value=_period, key="pc_period",
    )
    _termination = c3.text_input(
        "Termination (comma-separated, e.g. '80% capacity' / '4.25 V')",
        value=_termination, key="pc_term",
    )
    _temperature = st.number_input(
        "Experiment temperature (K, 0 = use model initial temperature)",
        0.0, 400.0, _temperature, 0.5, key="pc_temp",
    )
    for i, s in enumerate(steps):
        custom_steps.append(
            Step(
                kind=s["kind"],
                c_rate=s["value"] if s["kind"] in ("discharge", "charge")
                       and s["value_mode"] == "c_rate" else None,
                current_A=s["value"] if s["kind"] in ("discharge", "charge")
                          and s["value_mode"] == "current_A" else None,
                power_W=s["value"] if s["kind"] in ("discharge", "charge")
                        and s["value_mode"] == "power_W" else None,
                duration_s=(s["end_value"] if s["kind"] in ("discharge", "charge", "rest")
                            and s["end_mode"].startswith("Duration") else
                            s["end_value"] if s["kind"] == "hold"
                            and s["end_mode"].startswith("Duration") else None),
                cutoff_V=s["end_value"] if s["kind"] in ("discharge", "charge")
                         and s["end_mode"].startswith("Cut-off") else None,
                hold_voltage_V=s["hold_v"] if s["kind"] == "hold" else None,
                cutoff_current_C=s["end_value"] if s["kind"] == "hold"
                                 and s["end_mode"].startswith("Cut-off current") else None,
            )
        )

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

# ------------------------------------------------------------------ DAE warning
if thermal_maps and cfg.model_name in ("DFN", "SPMe") and cfg.dimensionality == 2:
    st.warning(
        "DFN/SPMe on the 2+1D mesh are DAE-limited to a few seconds "
        "(`IDA_ERR_FAIL`). For multi-step protocols with thermal maps, "
        "**SPM** is the reliable choice (auto-selected when needed)."
    )

# ------------------------------------------------------------------ preview + run
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
)
st.session_state.protocol = new_proto

st.divider()
c1, c2 = st.columns([1, 2])
if c1.button("Validate & preview", width="stretch"):
    try:
        strs = new_proto.step_strings(spec.capacity_Ah)
        cyc = new_proto.experiment_cycles(spec.capacity_Ah)
        st.session_state["proto_preview"] = {
            "steps": strs, "n_cycles": len(cyc),
            "temperature_K": new_proto.temperature_K,
            "termination": new_proto.termination,
            "period": new_proto.period,
        }
    except Exception as err:  # noqa: BLE001
        st.session_state["proto_preview_error"] = repr(err)
        st.session_state.pop("proto_preview", None)
preview = st.session_state.get("proto_preview")
if preview:
    st.markdown("**Parsed PyBaMM steps**")
    st.code("\n".join(preview["steps"]))
    st.caption(
        f"{preview['n_cycles']} cycle(s) · period={preview['period']} · "
        f"T={preview['temperature_K']} K · termination={preview['termination']}"
    )

# keep the legacy C-rate/duration in sync so the Results/History summary reads well
if p_type_id == "discharge" and custom_steps:
    cfg.C_rate = custom_steps[0].c_rate or cfg.C_rate
    cfg.duration_s = custom_steps[0].duration_s or cfg.duration_s

if c2.button("Run protocol", type="primary", width="stretch"):
    common.launch_run()
    st.rerun()
