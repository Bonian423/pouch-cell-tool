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
def init_state() -> None:
    """Seed ``st.session_state`` with the UI defaults (once)."""
    if "spec" not in st.session_state:
        st.session_state.spec = PouchCellSpec()
    if "config" not in st.session_state:
        # a fast first run: 1D DFN discharge to the cut-off
        st.session_state.config = RunConfig(
            model_name="DFN",
            dimensionality=0,
            thermal="lumped",
            mesh="draft",
            C_rate=1.0,
            duration_s=600.0,
            analysis="discharge",
            size_to_capacity=True,
        )
    if "thermal" not in st.session_state:
        st.session_state.thermal = ThermalConfig()
    if "protocol" not in st.session_state:
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
    idx = models.index(cfg.model_name) if cfg.model_name in models else 0
    cfg.model_name = st.selectbox("Model", models, index=idx, key="sb_model")

    mesh_opts = registry.options("mesh_3d" if cfg.model_name == "SPM_3D" else "mesh_21d")
    midx = mesh_opts.index(cfg.mesh) if cfg.mesh in mesh_opts else 0
    cfg.mesh = st.selectbox("Mesh", mesh_opts, index=midx, key="sb_mesh")

    cfg.initial_soc = st.slider(
        "Initial SOC", 0.0, 1.0, float(cfg.initial_soc), 0.05, key="sb_soc"
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

    Every page calls this first.  While a run is in flight it polls the worker
    and re-runs the page so the progress updates live.
    """
    init_state()
    st.sidebar.title("Pouch cell")

    with st.sidebar.expander("Quick run", expanded=True):
        _quick_knobs()
    _presets()

    st.sidebar.divider()
    if st.session_state.run_state == "running":
        st.sidebar.warning("Solving…")
        if st.sidebar.button("Cancel", width="stretch"):
            cancel_run()
            st.rerun()
    else:
        if st.sidebar.button("Run", type="primary", width="stretch"):
            launch_run()
            st.rerun()

    if st.session_state.run_state == "running":
        data = poll_run()
        elapsed = float(data.get("elapsed_s", 0.0))
        frac = min(0.03 + (elapsed % 45.0) / 45.0 * 0.94, 0.97) if elapsed else 0.03
        st.sidebar.progress(frac)
        st.sidebar.caption(
            f"stage: {data.get('stage', 'starting')} · {elapsed:.0f} s elapsed"
        )
        time.sleep(0.4)
        st.rerun()

    # brief status footer
    last = st.session_state.last_result
    if last and st.session_state.run_state == "idle":
        if "error" in last:
            st.sidebar.error(f"Last run failed: {last['error'][:120]}")
        else:
            st.sidebar.caption(
                f"last: V={last.get('final_V', float('nan')):.3f} V · "
                f"{last.get('delivered_Ah', float('nan')):.2f} Ah · "
                f"Tmax={last.get('Tmax_K', float('nan')):.1f} K"
            )


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
