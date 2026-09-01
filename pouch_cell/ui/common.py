"""Shared session-state helpers for the Streamlit UI (sidebar, run, presets)."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import streamlit as st

from .. import registry
from ..config import io as preset_io
from ..config.design import PouchCellSpec
from ..config.protocol import Protocol
from ..config.run import RunConfig
from ..config.thermal import ThermalConfig
from ..core.constraints import (
    Violation,
    constraint_violations,
    is_full_cell_parameter_set,
    mesh_default,
    normalise_config,
    resolve_effective,
    sanity_check_output_variables,
    viable_mesh,
    viable_thermal,
)

_WORKER_MODULE = "pouch_cell.ui.worker"
HISTORY_FILE = preset_io.PROJECT_ROOT / "pouch_output" / "history.jsonl"
UI_STATE_FILE = preset_io.PROJECT_ROOT / "pouch_output" / "ui_state.json"

# Drop the Design-page widget keys when loading a spec so they re-seed from it
# (otherwise stale widget values trigger a spurious auto-size).
_DESIGN_KEYS = (
    "d_height", "d_width", "d_thickness", "d_nstacks", "d_capacity",
    "d_L_n", "d_L_p", "d_L_s", "d_L_cn", "d_L_cp",
    "d_tab_w", "d_tab_neg", "d_tab_pos", "d_manual",
)


# --------------------------------------------------------------------------- #
# Session state
# --------------------------------------------------------------------------- #
# Guard rules live in pouch_cell/core/constraints.py (single source of truth).
# viable_thermal / viable_mesh / normalise_config / mesh_default are re-exported
# from there (imported above) so page code can keep using common.*.


def _default_config() -> RunConfig:
    """A fast first-run default: 1D DFN discharge to the cut-off."""
    return RunConfig(
        model_name="DFN", dimensionality=0, thermal="lumped", mesh="draft",
        C_rate=1.0, duration_s=600.0, analysis="discharge", size_to_capacity=True,
    )


def save_state() -> None:
    """Persist the current UI settings so a later session can restore them.

    Called at the end of every page's ``render_sidebar()`` (cheap, ~2 KB), so
    whatever the user last tweaked is what a fresh session opens with.
    """
    from dataclasses import asdict

    try:
        s = st.session_state
        UI_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "spec": s.spec.as_dict(),
            "config": s.config.as_dict(),
            "thermal": asdict(s.thermal),
            "protocol": s.protocol.as_dict(),
        }
        UI_STATE_FILE.write_text(json.dumps(data, default=str), encoding="utf-8")
    except Exception:  # noqa: BLE001 - persistence is best-effort
        pass


def _load_ui_state() -> dict:
    """Read the persisted UI settings (empty dict if none / corrupt)."""
    try:
        if UI_STATE_FILE.is_file():
            return json.loads(UI_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return {}


def init_state() -> None:
    """Seed ``st.session_state`` with the last-saved state (or UI defaults)."""
    saved = _load_ui_state()
    if "spec" not in st.session_state:
        spec = saved.get("spec")
        st.session_state.spec = (PouchCellSpec.from_dict(spec) if spec
                                 else PouchCellSpec())
    if "config" not in st.session_state:
        cfg = saved.get("config")
        if cfg:
            try:
                st.session_state.config = RunConfig(**cfg)
                normalise_config(st.session_state.config)
            except Exception:  # noqa: BLE001 - stale state -> defaults
                st.session_state.config = _default_config()
        else:
            st.session_state.config = _default_config()
    if "thermal" not in st.session_state:
        th = saved.get("thermal")
        try:
            st.session_state.thermal = ThermalConfig(**th) if th else ThermalConfig()
        except Exception:  # noqa: BLE001
            st.session_state.thermal = ThermalConfig()
    if "protocol" not in st.session_state:
        proto = saved.get("protocol")
        try:
            st.session_state.protocol = (
                Protocol.from_dict(proto) if proto else Protocol.discharge_protocol()
            )
        except Exception:  # noqa: BLE001
            st.session_state.protocol = Protocol.discharge_protocol()
    if "history" not in st.session_state:
        st.session_state.history = []
    if "saved_count" not in st.session_state:
        st.session_state.saved_count = 0
    if "last_result" not in st.session_state:
        st.session_state.last_result = None
    if "run_dir" not in st.session_state:
        st.session_state.run_dir = None
    if "proc" not in st.session_state:
        st.session_state.proc = None
    if "run_state" not in st.session_state:
        st.session_state.run_state = "idle"
    if "sizing_key" not in st.session_state:
        s = st.session_state.spec
        st.session_state.sizing_key = (s.capacity_Ah, s.height, s.width, s.n_stacks)


def apply_config(cfg: RunConfig) -> None:
    """Load a :class:`RunConfig` (e.g. from a preset) into the session.

    Structurally-broken presets (unknown model / parameter set, out-of-range
    values) are rejected with an error; stale-but-fixable combinations are
    auto-corrected and reported in the Compatibility panel.
    """
    from ..core.constraints import validate_structural

    try:
        validate_structural(cfg)
    except ValueError as err:
        st.session_state["preset_error"] = str(err)
        return
    fixed = normalise_config(cfg)
    if fixed:
        note_corrections(
            [f"auto-corrected {f} → {getattr(cfg, f)}" for f in fixed]
        )
    st.session_state.pop("preset_error", None)
    st.session_state.config = cfg
    st.session_state.spec = cfg.spec()
    # uniform cooling presets are no longer used by the UI (cooling is
    # region-based); don't re-seed them from a saved config
    st.session_state.thermal = ThermalConfig()
    if cfg.protocol:
        st.session_state.protocol = Protocol.from_dict(cfg.protocol)
    s = st.session_state.spec
    st.session_state.sizing_key = (s.capacity_Ah, s.height, s.width, s.n_stacks)
    # Drop the Design-page widget keys so they re-seed from the loaded spec
    # (otherwise stale values would trigger a spurious auto-size).
    for _k in _DESIGN_KEYS:
        st.session_state.pop(_k, None)


# --------------------------------------------------------------------------- #
# Guard helpers (single source of truth: core/constraints.py)
# --------------------------------------------------------------------------- #
def note_corrections(messages: list[str]) -> None:
    """Record auto-corrections (deduped, newest first, capped) for the panel."""
    if not messages:
        return
    corr = st.session_state.setdefault("corrections", [])
    for m in messages:
        if m not in corr:
            corr.insert(0, m)
    del corr[6:]


def sync_mesh(cfg, widget_key: str | None = None) -> list[str]:
    """Keep ``cfg.mesh`` a valid option for ``cfg.model_name``.

    Remembers the mesh used per model family (true-3D vs 2+1D) so switching
    ``SPM_3D`` <-> other restores the last-used mesh of that family instead of
    always resetting to the default.  If ``widget_key`` is given it is written
    before instantiation (the Streamlit write-before-instantiate pattern).
    """
    s = st.session_state
    meshes = viable_mesh(cfg.model_name)
    fam = "3d" if cfg.model_name == "SPM_3D" else "21d"
    mem = s.setdefault("mesh_memory", {})
    if cfg.mesh not in meshes:
        remembered = mem.get(fam)
        cfg.mesh = remembered if remembered in meshes else mesh_default(cfg.model_name)
        if widget_key is not None:
            s[widget_key] = cfg.mesh
        note_corrections([f"auto-corrected mesh → {cfg.mesh}"])
    mem[fam] = cfg.mesh
    return meshes


def _compat() -> dict:
    """Current constraint state: blocked / warnings / infos / corrections."""
    cfg = st.session_state.config
    vios = constraint_violations(
        cfg,
        protocol=st.session_state.get("protocol"),
        spec=st.session_state.get("spec"),
        cooling=getattr(st.session_state.get("thermal"), "cooling", None),
    )
    return {
        "blocked": [v for v in vios if v.kind == "blocked"],
        "warnings": [v for v in vios if v.kind == "warning"],
        "infos": [v for v in vios if v.kind == "info"],
        "corrections": list(st.session_state.get("corrections", [])),
    }


def hard_blocked() -> list[Violation]:
    """Violations that must be fixed before a run can start."""
    return _compat()["blocked"]


def _compat_panel() -> None:
    """Sidebar compatibility panel (only when there is something to say)."""
    comp = _compat()
    preset_error = st.session_state.get("preset_error")
    if not (comp["blocked"] or comp["warnings"] or comp["infos"]
            or comp["corrections"] or preset_error):
        return
    with st.sidebar.expander("Compatibility", expanded=bool(comp["blocked"])):
        if preset_error:
            st.error(f"Preset not loaded: {preset_error}")
        for c in comp["corrections"]:
            st.caption(f"↻ {c}")
        for v in comp["infos"]:
            st.info(v.message)
        for v in comp["warnings"]:
            st.warning(v.message)
        for v in comp["blocked"]:
            st.error(v.message)


def effective_readout(cfg, proto=None) -> str:
    """One-line 'what will actually run' readout (thermal maps may override)."""
    proto = proto or st.session_state.get("protocol")
    eff = resolve_effective(cfg, proto)
    overridden = (
        eff["model"] != cfg.model_name
        or eff["dimensionality"] != cfg.dimensionality
        or eff["thermal"] != cfg.thermal
        or eff["mesh"] != cfg.mesh
    )
    base = (f"Will run as **{eff['model']}** · dim {eff['dimensionality']} · "
            f"**{eff['thermal']}** · mesh `{eff['mesh']}`")
    return base + (" — thermal maps override your selections." if overridden else ".")


def check_variable_names(names: list[str]) -> list[str]:
    """Strict, on-demand check: return names missing from a quick SPM model."""
    try:
        import pybamm

        model = pybamm.lithium_ion.SPM()
        param = pybamm.ParameterValues(model.default_parameter_values)
        sim = pybamm.Simulation(model, parameter_values=param)
        sim.build()  # ~1 s; exposes model.variables with their exact names
        known = set(sim.model.variables)
    except Exception:  # noqa: BLE001
        return ["(could not build a reference SPM model — check names at run time)"]
    return [n for n in (names or []) if n not in known]


# --------------------------------------------------------------------------- #
# Run orchestration (subprocess worker)
# --------------------------------------------------------------------------- #
def launch_run() -> None:
    """Write the payload and start the worker subprocess (non-blocking).

    Hard-blocked combinations (invalid output variables, degenerate initial
    state, broken presets) are rejected here rather than spawning a worker
    that would immediately fail; guard warnings + auto-corrections are carried
    into the run record for reproducibility.
    """
    comp = _compat()
    if comp["blocked"]:
        st.session_state["launch_blocked"] = [v.message for v in comp["blocked"]]
        return
    st.session_state.pop("launch_blocked", None)

    spec = st.session_state.spec
    cfg = st.session_state.config
    thermal = st.session_state.thermal
    proto = st.session_state.protocol
    cfg.design = spec.as_dict()          # keep presets in sync
    cfg.cooling = thermal.to_cooling()   # fold the thermal page into cooling=
    cfg.protocol = proto.as_dict()       # the run type lives on the protocol

    runs_root = preset_io.PROJECT_ROOT / "pouch_output" / "runs"
    run_dir = runs_root / f"run_{int(time.time())}"
    run_dir.mkdir(parents=True, exist_ok=True)
    payload_path = run_dir / "payload.json"
    warnings = [v.message for v in comp["warnings"]] + comp["corrections"]
    payload_path.write_text(
        json.dumps(
            {
                "spec": spec.as_dict(),
                "config": cfg.as_dict(),
                "warnings": warnings,
            },
            default=str,
        ),
        encoding="utf-8",
    )
    proc = subprocess.Popen(
        [
            sys.executable, "-m", _WORKER_MODULE,
            "--config", str(payload_path),
            "--outdir", str(run_dir),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    st.session_state.proc = proc
    st.session_state.run_dir = str(run_dir)
    st.session_state.run_state = "running"


def poll_run() -> dict:
    """Read the worker's progress file; finalise the run when it is done."""
    if not st.session_state.run_dir:
        return {"status": "starting"}
    prog = Path(st.session_state.run_dir) / "progress.json"
    if prog.is_file():
        try:
            data = json.loads(prog.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            data = {}
    else:
        data = {"status": "starting"}

    if data.get("status") in ("done", "error"):
        res = Path(st.session_state.run_dir) / "result.json"
        result = json.loads(res.read_text(encoding="utf-8")) if res.is_file() else {}
        result["run_dir"] = st.session_state.run_dir
        st.session_state.last_result = result
        st.session_state.history.append(result)
        st.session_state.run_state = "idle"
        st.session_state.proc = None
    return data


def cancel_run() -> None:
    """Terminate the running worker subprocess."""
    proc = st.session_state.get("proc")
    if proc is not None:
        try:
            proc.terminate()
        except Exception:  # noqa: BLE001
            pass
    st.session_state.proc = None
    st.session_state.run_state = "idle"


# --------------------------------------------------------------------------- #
# History persistence (pouch_output/history.jsonl)
# --------------------------------------------------------------------------- #
def save_run(result: dict) -> Path:
    """Append one completed run to the JSONL history file (returns its path)."""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {"saved_at": time.strftime("%Y-%m-%d %H:%M:%S"), "result": result}
    with open(HISTORY_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, default=str) + "\n")
    return HISTORY_FILE


def save_session() -> int:
    """Persist any not-yet-saved in-session runs to JSONL. Returns rows saved."""
    history = st.session_state.history
    n = 0
    for result in history[st.session_state.saved_count:]:
        save_run(result)
        n += 1
    st.session_state.saved_count = len(history)
    return n


def load_saved_runs() -> list[dict]:
    """Read all previously saved runs from JSONL (newest last)."""
    if not HISTORY_FILE.is_file():
        return []
    out: list[dict] = []
    with open(HISTORY_FILE, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def delete_saved_run(idx: int) -> None:
    """Remove the ``idx``-th saved entry (0-based, ``load_saved_runs`` order)."""
    entries = load_saved_runs()
    if idx < 0 or idx >= len(entries):
        return
    del entries[idx]
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e, default=str) + "\n")


def load_result_into_session(entry: dict) -> None:
    """Make a saved run the 'current' result so Results can review it."""
    result = entry.get("result", entry)
    st.session_state.last_result = result
    st.session_state.run_dir = result.get("run_dir")


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
def _quick_knobs() -> None:
    cfg = st.session_state.config
    models = registry.options("model")
    # read the intended model first (write-before-instantiate for the mesh guard)
    intended_model = st.session_state.get("sb_model", cfg.model_name)
    if intended_model not in models:
        intended_model = models[0]
    cfg.model_name = intended_model
    meshes = sync_mesh(cfg, "sb_mesh")
    fixed = normalise_config(cfg)
    if "mesh" in fixed:
        st.session_state["sb_mesh"] = cfg.mesh
    if fixed:
        note_corrections(
            [f"auto-corrected {f} → {getattr(cfg, f)}" for f in fixed]
        )
    cfg.model_name = st.selectbox(
        "Model", models, index=models.index(cfg.model_name), key="sb_model"
    )
    midx = meshes.index(cfg.mesh) if cfg.mesh in meshes else 0
    cfg.mesh = st.selectbox("Mesh", meshes, index=midx, key="sb_mesh")
    init_mode = st.radio(
        "Initial state by", ["SOC", "Voltage"], horizontal=True,
        index=0 if cfg.initial_voltage is None else 1, key="sb_init_mode",
    )
    if init_mode == "SOC":
        cfg.initial_soc = st.slider(
            "Initial SOC", 0.0, 1.0, float(cfg.initial_soc), 0.05, key="sb_soc"
        )
        cfg.initial_voltage = None
    else:
        cur_v = float(cfg.initial_voltage) if cfg.initial_voltage else 4.0
        cur_v = min(max(cur_v, 2.5), 4.25)
        cfg.initial_voltage = st.slider(
            "Initial voltage (V)", 2.5, 4.25, cur_v, 0.01, key="sb_voltage",
            help="Start the cell at this open-circuit voltage (overrides SOC).",
        )
        st.caption("Voltage mode overrides Initial SOC.")


def _status_text(data: dict) -> str:
    """Human status line from a worker progress.json dict (stage + step)."""
    parts = [str(data.get("stage") or "starting")]
    if data.get("cycle") and data.get("cycle_total"):
        parts.append(f"cycle {data['cycle']}/{data['cycle_total']}")
    if data.get("step") and data.get("step_total"):
        parts.append(f"step {data['step']}/{data['step_total']}")
    if data.get("experiment_time") is not None:
        parts.append(f"t={float(data['experiment_time']):.0f}s sim")
    if data.get("elapsed_s") is not None:
        parts.append(f"{float(data['elapsed_s']):.0f}s wall")
    return " · ".join(parts)


# public alias for use from page scripts
status_text = _status_text


@st.fragment(run_every=1.0)
def _run_panel() -> None:
    """Sidebar Run / Cancel + live status.

    A self-refreshing fragment: it re-runs every second while a run is in
    flight so the stage / cycle / step stay live, WITHOUT re-running the whole
    page -- so the user can keep browsing and tweaking every tab.  When the
    run finishes the fragment triggers one full re-run so Results shows it.
    """
    if st.session_state.run_state == "running":
        data = poll_run()
        st.sidebar.warning("Running…")
        st.sidebar.caption(_status_text(data))
        if st.sidebar.button("Cancel", width="stretch"):
            cancel_run()
            st.rerun()
        if st.session_state.run_state == "idle":
            st.rerun()  # finished -> refresh so the current page shows results
    else:
        blocked = _compat()["blocked"]
        if blocked:
            st.sidebar.error("Run is blocked — fix the items in **Compatibility**.")
        if st.sidebar.button(
            "Run", type="primary", width="stretch", disabled=bool(blocked)
        ):
            launch_run()
            st.rerun()
        last = st.session_state.last_result
        if last:
            if last.get("error"):
                st.sidebar.error(f"Last run failed: {last['error'][:120]}")
            else:
                st.sidebar.caption(
                    f"last: V={last.get('final_V', float('nan')):.3f} V · "
                    f"{last.get('delivered_Ah', float('nan')):.2f} Ah · "
                    f"Tmax={last.get('Tmax_K', float('nan')):.1f} K"
                )
                eff = last.get("effective_config")
                warns = last.get("warnings") or []
                if eff:
                    st.sidebar.caption(
                        f"ran as {eff.get('model')} · dim "
                        f"{eff.get('dimensionality')} · {eff.get('thermal')} · "
                        f"mesh `{eff.get('mesh')}`"
                        + (f" · {len(warns)} warning(s)" if warns else "")
                    )


def _presets() -> None:
    with st.sidebar.expander("Presets", expanded=False):
        names = preset_io.list_presets()
        sel = st.selectbox("Load preset", ["— none —"] + names, key="sb_preset_sel")
        if st.button("Load", width="stretch") and sel != "— none —":
            apply_config(preset_io.load_preset(sel))
            st.rerun()
        save_name = st.text_input("Save current as", key="sb_save_preset_name")
        if st.button("Save", width="stretch") and save_name:
            cfg = st.session_state.config
            cfg.design = st.session_state.spec.as_dict()
            cfg.protocol = st.session_state.protocol.as_dict()
            path = preset_io.save_preset(save_name, cfg)
            st.sidebar.success(f"Saved {path.name}")


def render_sidebar() -> None:
    """Render the shared sidebar (quick knobs + presets + Run/Cancel + status).

    Every page calls this first.  Run status lives in a self-refreshing
    fragment so a run never blanks the page or blocks other tabs.
    """
    init_state()
    st.sidebar.title("Pouch cell")

    with st.sidebar.expander("Quick run", expanded=True):
        _quick_knobs()
    _presets()

    st.sidebar.divider()
    _compat_panel()
    _run_panel()  # Run/Cancel + live status (fragment, updates every second)
    save_state()  # persist whatever the user just tweaked


def summary_markdown() -> str:
    """Short markdown blurb about the current design for the overview page."""
    spec = st.session_state.spec
    cfg = st.session_state.config
    return (
        f"**{spec.n_stacks} × {spec.height * 100:.0f} × {spec.width * 100:.0f} cm "
        f"({spec.capacity_Ah:.1f} Ah)**\n\n"
        f"`{cfg.model_name}` · dim {cfg.dimensionality} · `{cfg.thermal}` · "
        f"`{cfg.mesh}`\n\n"
        f"{spec.report()}"
    )


# --------------------------------------------------------------------------- #
# Persistent right-side panel (replaces the Overview tab)
# --------------------------------------------------------------------------- #
_SETTING_LABELS = {
    # run config
    "model_name": "Model", "dimensionality": "Dim", "thermal": "Thermal",
    "mesh": "Mesh", "parameter_set": "Parameter set", "solver": "Solver",
    "analysis": "Analysis", "initial_soc": "Initial SOC",
    "initial_voltage": "Initial voltage", "C_rate": "C-rate",
    "duration_s": "Duration (s)", "size_to_capacity": "Auto-size",
    "particle": "Particle", "full_stack_3d": "Full-stack 3D",
    "store_first_last": "Store first/last", "output_variables": "Output vars",
    # spec
    "height": "Height (z)", "width": "Width (y)",
    "thickness_total": "Thickness", "n_stacks": "Stacks",
    "capacity_Ah": "Capacity (Ah)", "n_series": "Series cells",
    "tab_width": "Tab width", "neg_tab_y_centre": "Neg tab y",
    "pos_tab_y_centre": "Pos tab y", "ambient_temperature_K": "Ambient T (K)",
    "lower_cutoff_V": "Lower cut-off", "upper_cutoff_V": "Upper cut-off",
    "cooling_regions": "Cooling regions",
    "L_cn": "L_cn (Cu)", "L_n": "L_n (neg)", "L_s": "L_s (sep)",
    "L_p": "L_p (pos)", "L_cp": "L_cp (Al)",
    "negative_electrode": "Negative electrode",
    "positive_electrode": "Positive electrode",
    # thermal
    "cooling": "Cooling", "heat_transfer_coefficient_W_m2K": "h override",
    "per_face_h": "Per-face h", "extra_overrides": "Raw overrides",
    # protocol
    "type": "Protocol type", "cycles": "Cycles", "period": "Period",
    "thermal_maps": "Thermal maps", "step_map_mode": "Map mode",
    "run_conditions": "Run conditions",
    "default_temperature_source": "Temp source (default)",
}


def _fmt_setting(key: str, value) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, float):
        if key.startswith("L_"):  # layer thickness in metres -> µm
            return f"{value * 1e6:.1f} µm"
        if key in ("initial_soc",):
            return f"{value:.2f}"
        return f"{value:g}"
    if isinstance(value, (list, dict)):
        return f"{len(value)} × {key.replace('_', ' ')}"
    return str(value)


def diff_settings(spec, cfg, thermal, proto) -> list[tuple[str, str]]:
    """Key settings that differ from the fresh-install defaults.

    Compares the live session dataclasses (so sidebar quick-knob changes are
    caught too) and returns ``(label, value)`` pairs for display.
    """
    default_cfg = _default_config()
    default_spec = PouchCellSpec()
    default_th = ThermalConfig()
    default_proto = Protocol.discharge_protocol()
    rows: list[tuple[str, str]] = []

    def _add(field: str, cur, default, label_map):
        if cur == default:
            return
        rows.append((label_map.get(field, field.replace("_", " ").title()),
                     _fmt_setting(field, cur)))

    from dataclasses import fields as _dfields

    for f in sorted(_dfields(RunConfig), key=lambda x: x.name):
        if f.name == "design":
            continue
        _add(f.name, getattr(cfg, f.name), getattr(default_cfg, f.name),
             _SETTING_LABELS)
    for f in sorted(_dfields(PouchCellSpec), key=lambda x: x.name):
        _add(f.name, getattr(spec, f.name), getattr(default_spec, f.name),
             _SETTING_LABELS)
    for f in ("cooling", "ambient_temperature_K",
              "heat_transfer_coefficient_W_m2K"):
        _add(f, getattr(thermal, f), getattr(default_th, f), _SETTING_LABELS)
    if thermal.per_face_h:
        rows.append(("Per-face h", f"{len(thermal.per_face_h)} face(s)"))
    if thermal.extra_overrides:
        rows.append(("Raw overrides", f"{len(thermal.extra_overrides)} key(s)"))
    for f in ("type", "cycles", "period", "thermal_maps", "step_map_mode",
              "default_temperature_source"):
        _add(f, getattr(proto, f), getattr(default_proto, f), _SETTING_LABELS)
    if len(proto.run_conditions or []) != len(default_proto.run_conditions or []):
        rows.append(("Run conditions", f"{len(proto.run_conditions or [])}"))
    if len(proto.steps) != len(default_proto.steps):
        rows.append(("Steps", f"{len(proto.steps)}"))
    n_ov = len(cfg.extra_overrides or {})
    if n_ov:
        rows.append(("Electrochem overrides", f"{n_ov} key(s)"))
    # de-dup keys that may appear from both spec + cfg
    seen: set = set()
    out: list[tuple[str, str]] = []
    for k, v in rows:
        if k in seen:
            continue
        seen.add(k)
        out.append((k, v))
    return out


def render_persistent_panel() -> None:
    """Render the persistent right-side panel (replaces the Overview tab).

    Order: cell schematic with its legend to the right (small font), then the
    compact "run condition" block, then the user-changed parameters in tight
    type.  Always reflects the CURRENT session config.  Call inside the right
    column of ``page_body()``.
    """
    spec = st.session_state.spec
    cfg = st.session_state.config
    thermal = st.session_state.get("thermal") or ThermalConfig()
    proto = st.session_state.get("protocol") or Protocol.discharge_protocol()

    try:
        import matplotlib.pyplot as plt

        from .. import plotting

        fig = plotting.plot_cell_schematic(spec)
        c_fig, c_leg = st.columns([1.55, 1], vertical_alignment="center")
        with c_fig:
            st.pyplot(fig, width="stretch")
        with c_leg:
            st.markdown(
                '<div style="font-size:11px;line-height:1.35;">'
                '<span style="display:inline-block;width:9px;height:9px;'
                'background:#e53935;border:1px solid #444;margin-right:5px;">'
                '</span>tabs<br>'
                '<span style="display:inline-block;width:9px;height:9px;'
                'background:#1f77b4;border:1px solid #444;margin-right:5px;">'
                '</span>cooling area<br>'
                '<span style="display:inline-block;width:9px;height:9px;'
                'background:#1a1a1a;border:1px solid #666;margin-right:5px;">'
                '</span>cell<br>'
                '<span style="color:#777;">&#8211; &#8211; dimensions</span>'
                '</div>',
                unsafe_allow_html=True,
            )
        plt.close(fig)
    except Exception:  # noqa: BLE001 - schematic is best-effort
        st.caption("(schematic unavailable)")
    st.caption(
        f"**{spec.n_stacks} × {spec.height * 100:.0f} × {spec.width * 100:.0f} cm**  \n"
        f"thickness {spec.thickness_total * 1e3:.0f} mm · **{spec.capacity_Ah:.1f} Ah**"
    )

    # --- run condition (compact) -------------------------------------------
    eff = resolve_effective(cfg, proto)
    st.divider()
    st.caption(
        f"**Run condition:** `{eff['model']}` · dim {eff['dimensionality']} · "
        f"`{eff['thermal']}` · `{eff['mesh']}` · `{cfg.parameter_set}` · "
        f"SOC {cfg.initial_soc:.0%} · `{cfg.solver}`"
    )

    # --- changed parameters (compact) --------------------------------------
    st.divider()
    st.markdown("**Changed parameters**")
    rows = diff_settings(spec, cfg, thermal, proto)
    if not rows:
        st.caption("All defaults — nothing changed.")
    else:
        st.caption(
            "  \n".join(f"• **{label}:** {value}" for label, value in rows)
        )

    stopped = (st.session_state.get("last_result") or {}).get("stopped")
    if stopped:
        st.caption(f"Last run stopped: {stopped.get('message', '')}")


def page_setup() -> None:
    """Call at the very top of every page: state + sidebar.

    ``st.set_page_config`` is set ONCE in the entrypoint router
    (``ui/Overview.py``) — Streamlit forbids calling it more than once, so
    pages must not call it.
    """
    init_state()
    render_sidebar()


def page_body():
    """Open the ``[main | persistent panel]`` layout and render the panel.

    Pages wrap their body in ``with page_body():``; the returned value is the
    left (main) column so subsequent widgets land to the left of the panel.
    """
    left, right = st.columns([3.4, 1], gap="medium")
    with right:
        render_persistent_panel()
    return left
