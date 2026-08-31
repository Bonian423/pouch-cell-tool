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
# Viable model/thermal/mesh combinations (so only working combos can be picked).
def viable_thermal(dim: int) -> list[str]:
    """Thermal submodels that are valid for a given dimensionality."""
    if dim == 0:
        return ["isothermal", "lumped", "x-full"]
    return ["isothermal", "lumped", "x-lumped"]


def viable_mesh(model_name: str) -> list[str]:
    """Mesh presets that work with a model (true-3D FEM vs 2+1D)."""
    return registry.options("mesh_3d" if model_name == "SPM_3D" else "mesh_21d")


def normalise_config(cfg) -> list[str]:
    """Force a viable (model, thermal, mesh, particle) combination in place.

    Returns the names of the fields that were corrected.  Call this before
    rendering dependent widgets so a widget's stored value is always a valid
    option (and the underlying config never holds a broken combination).
    """
    fixed: list[str] = []
    th = viable_thermal(cfg.dimensionality)
    if cfg.thermal not in th:
        cfg.thermal = "lumped"
        fixed.append("thermal")
    meshes = viable_mesh(cfg.model_name)
    if cfg.mesh not in meshes:
        cfg.mesh = meshes[0]
        fixed.append("mesh")
    # r=1 meshes (micro/coarse 2+1D) require uniform-profile particles
    if cfg.mesh in ("micro_21d", "coarse_21d") and cfg.particle != "uniform profile":
        cfg.particle = "uniform profile"
        fixed.append("particle")
    return fixed


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
        st.session_state.spec = PouchCellSpec(**spec) if spec else PouchCellSpec()
    if "config" not in st.session_state:
        cfg = saved.get("config")
        if cfg:
            try:
                st.session_state.config = RunConfig(**cfg)
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
    """Load a :class:`RunConfig` (e.g. from a preset) into the session."""
    st.session_state.config = cfg
    st.session_state.spec = cfg.spec()
    st.session_state.thermal = ThermalConfig(cooling=cfg.cooling)
    if cfg.protocol:
        st.session_state.protocol = Protocol.from_dict(cfg.protocol)
    s = st.session_state.spec
    st.session_state.sizing_key = (s.capacity_Ah, s.height, s.width, s.n_stacks)
    # Drop the Design-page widget keys so they re-seed from the loaded spec
    # (otherwise stale values would trigger a spurious auto-size).
    for _k in _DESIGN_KEYS:
        st.session_state.pop(_k, None)


# --------------------------------------------------------------------------- #
# Run orchestration (subprocess worker)
# --------------------------------------------------------------------------- #
def launch_run() -> None:
    """Write the payload and start the worker subprocess (non-blocking)."""
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
    payload_path.write_text(
        json.dumps(
            {"spec": spec.as_dict(), "config": cfg.as_dict()},
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
    meshes = viable_mesh(cfg.model_name)
    if cfg.mesh not in meshes:
        # safe: sb_mesh is not instantiated yet on this run
        st.session_state["sb_mesh"] = meshes[0]
        cfg.mesh = meshes[0]
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
        if st.sidebar.button("Run", type="primary", width="stretch"):
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
