"""Command-line interface for the 3D pouch cell modelling tool.

Examples
--------
Print the cell design and exit::

    python -m pouch_cell --info

Run a 3D DFN discharge of the stock cell (2+1D potential pair, x-lumped
thermal).  Note: 2+1D DFN is computationally expensive -- 120 s of discharge
can take several minutes of wall-clock time::

    python -m pouch_cell

Tab-driven resistive-heating analysis.  DFN/SPMe 2+1D are DAE-limited to ~5 s
(IDA_ERR_FAIL min step size); use ``--model SPM`` for 60 s+ tab runs::

    python -m pouch_cell --tab-analysis
    python -m pouch_cell --tab-analysis --model SPM --duration 60

Run a named preset or a config JSON::

    python -m pouch_cell --preset default_9Ah
    python -m pouch_cell --config presets/my_design.json

Launch the Streamlit UI::

    python -m pouch_cell --ui
"""
from __future__ import annotations

import argparse
import subprocess
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from . import registry  # noqa: E402
from .config.design import PouchCellSpec  # noqa: E402
from .config import io as preset_io  # noqa: E402
from .config.run import RunConfig  # noqa: E402
from .core.solvers import make_solver  # noqa: E402


def _parse_c_rate(value: str) -> float:
    return float(value.strip().lower().removesuffix("c"))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pouch-cell",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--info", action="store_true",
                   help="print the cell design and exit")
    p.add_argument("--ui", action="store_true",
                   help="launch the Streamlit UI and exit")
    p.add_argument("--preset", default=None,
                   help="run a named preset from the presets/ directory")
    p.add_argument("--config", default=None,
                   help="run a RunConfig JSON file")
    p.add_argument("--save-preset", default=None, metavar="NAME",
                   help="save the current configuration as a named preset")
    p.add_argument("--model", default="DFN", choices=registry.options("model"),
                   help="electrochemical model (default DFN)")
    p.add_argument("--dimensionality", type=int, default=2, choices=[0, 1, 2],
                   help="current-collector dimensionality for 2+1D models")
    p.add_argument("--thermal", default="x-lumped",
                   choices=registry.options("thermal"),
                   help="thermal submodel (2+1D models only)")
    p.add_argument("--parameter-set", default="Chen2020",
                   choices=registry.options("parameter_set"))
    p.add_argument("--mesh", default="draft",
                   help="mesh preset: draft | standard | fine | coarse_21d | micro_21d")
    p.add_argument("--solver", default="default", choices=registry.options("solver"),
                   help="DAE solver (default: model default = IDAKLUSolver)")
    p.add_argument("--initial-soc", type=float, default=1.0,
                   help="initial state of charge (0-1)")
    p.add_argument("--discharge", type=_parse_c_rate, default=1.0,
                   help="discharge C-rate, e.g. '1C' or '0.5'")
    p.add_argument("--duration", type=float, default=120.0,
                   help="discharge duration in seconds (default 120)")
    p.add_argument("--cutoff", type=float, default=None,
                   help="lower voltage cutoff (V) - run until this is reached")
    p.add_argument("--cooling", default=None, choices=[None] + registry.options("cooling"),
                   help="cooling preset (natural/forced_air/cold_plate/...)")
    p.add_argument("--heat-pipe", action="store_true",
                   help="enable the top-edge heat-pipe cooling (2+1D x-lumped)")
    p.add_argument("--out", default="pouch_output",
                   help="output directory for figures (default pouch_output)")
    p.add_argument("--no-size", action="store_true",
                   help="disable automatic electrode sizing (use spec thicknesses)")
    p.add_argument("--tab-analysis", action="store_true",
                   help="run the tab-driven resistive-heating analysis "
                        "(2+1D, x-lumped thermal) instead of a plain discharge")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.ui:
        import shutil
        from pathlib import Path
        app = Path(__file__).resolve().parent / "ui" / "Overview.py"
        print(f"Launching Streamlit UI: {app}")
        return subprocess.call([sys.executable, "-m", "streamlit", "run", str(app)])

    # --- load the config: preset / JSON file / defaults + flags ----------
    if args.preset:
        cfg = preset_io.load_preset(args.preset)
        print(f"Loaded preset '{args.preset}'.")
    elif args.config:
        import json
        from pathlib import Path
        cfg = RunConfig(**json.loads(Path(args.config).read_text(encoding="utf-8")))
        print(f"Loaded config '{args.config}'.")
    else:
        cfg = RunConfig()
    # CLI flags override the loaded config
    cfg.model_name = args.model
    cfg.dimensionality = args.dimensionality
    cfg.thermal = args.thermal
    cfg.parameter_set = args.parameter_set
    cfg.mesh = args.mesh
    cfg.solver = args.solver
    cfg.initial_soc = args.initial_soc
    cfg.C_rate = args.discharge
    cfg.duration_s = args.duration
    cfg.cutoff_V = args.cutoff
    cfg.size_to_capacity = not args.no_size
    if args.cooling:
        cfg.cooling = args.cooling
    if args.tab_analysis:
        cfg.analysis = "tab"
    spec = cfg.spec()
    if args.heat_pipe:
        spec.heat_pipe_enabled = True

    # a 0D model cannot use the x-lumped thermal submodel; fall back to lumped
    if cfg.dimensionality == 0 and cfg.thermal == "x-lumped":
        cfg.thermal = "lumped"

    if args.save_preset:
        cfg.design = spec.as_dict()
        path = preset_io.save_preset(args.save_preset, cfg)
        print(f"Saved preset to {path}")

    if args.info:
        print(spec.report())
        return 0

    # --- run --------------------------------------------------------------
    try:
        cfg.validate()
    except ValueError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2

    if cfg.analysis == "tab":
        from .core.analysis import tab_heating_analysis

        # DFN/SPMe 2+1D are DAE-limited to ~5 s
        if cfg.model_name in ("DFN", "SPMe") and cfg.duration_s > 5:
            print("NOTE: DFN/SPMe 2+1D are DAE-limited to ~5 s; clamping duration.")
            cfg.duration_s = 5
        sim, sol, fig = tab_heating_analysis(
            spec=spec,
            C_rate=cfg.C_rate,
            duration_s=cfg.duration_s or 5,
            mesh=cfg.mesh,
            model_name=cfg.model_name,
            cooling=cfg.cooling,
            parameter_set=cfg.parameter_set,
            solver=make_solver(cfg.solver),
            size_to_capacity=cfg.size_to_capacity,
        )
        print(sim.summary())
        import os
        os.makedirs(args.out, exist_ok=True)
        fig.savefig(f"{args.out}/tab_heating.png", dpi=110, bbox_inches="tight")
        print(f"Saved {args.out}/tab_heating.png")
        return 0

    from .core.simulation import PouchCellSimulation

    sim = PouchCellSimulation(
        spec=spec,
        model_name=cfg.model_name,
        dimensionality=cfg.dimensionality,
        thermal=cfg.thermal,
        parameter_set=cfg.parameter_set,
        initial_soc=cfg.initial_soc,
        mesh=cfg.mesh,
        solver=make_solver(cfg.solver),
        cooling=cfg.cooling,
        size_to_capacity=cfg.size_to_capacity,
    )
    sol = sim.discharge(C_rate=cfg.C_rate, duration_s=cfg.duration_s,
                        cutoff_V=cfg.cutoff_V)
    print(sim.summary())

    import os
    os.makedirs(args.out, exist_ok=True)
    from . import plotting
    fig = plotting.plot_discharge(sol, spec)
    fig.savefig(f"{args.out}/discharge.png", dpi=110, bbox_inches="tight")
    if cfg.dimensionality == 2:
        plotting.plot_temperature_map(sol)
        plt.savefig(f"{args.out}/temperature.png", dpi=110, bbox_inches="tight")
    print(f"Saved figures to {args.out}/")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
