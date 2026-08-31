# 3D PyBaMM Pouch Cell Modelling Tool

A PyBaMM-based 3D modelling tool for a **9 Ah lithium-ion pouch cell** built from
**20 stacks of electrodes and separators**:

| Parameter        | Value                          |
|------------------|--------------------------------|
| Chemistry        | NCM811 cathode / graphite anode|
| Capacity         | 9 Ah (auto-sized)              |
| Footprint        | 15 cm (z) x 9 cm (y)           |
| Outer thickness  | 1 cm (x, incl. packaging)      |
| Stack            | 20 electrode pairs in parallel |
| Tabs             | two 2 cm x 2 cm tabs: negative at (y = 2 cm), positive at (y = 7 cm), both on the top edge (z = 15 cm) |

```
pouch_cell/                     # the tool package (installable: pip install -e .)
├── config/                     # single source of truth for every knob
│   ├── design.py               # PouchCellSpec (geometry, stack, tabs, heat pipe)
│   ├── run.py                  # RunConfig (model, mesh, SOC, C-rate, duration…)
│   ├── thermal.py              # ThermalConfig (cooling / heat-pipe UI knobs)
│   └── io.py                   # save/load named presets (JSON)
├── core/                       # pure PyBaMM engine (no UI/CLI coupling)
│   ├── model.py                # build SPM / SPMe / DFN (2+1D) and SPM_3D (true 3D)
│   ├── parameters.py           # build PyBaMM ParameterValues (Chen2020 NMC811/graphite)
│   ├── sizing.py               # auto-size electrode thickness to hit the target Ah
│   ├── simulation.py           # PouchCellSimulation (run loop, mesh resolution)
│   ├── experiment.py           # one-call runner from a RunConfig + metrics
│   ├── sweep.py                # parallel C-rate sweeps
│   └── analysis.py             # tab-driven resistive-heating analysis
├── thermal/                    # cooling presets + heat-pipe localization
├── registry.py                 # pluggable option registries (models/thermal/…)
├── cli.py                      # python -m pouch_cell
├── ui/                         # Streamlit UI (Overview.py + pages/ + worker.py)
└── plotting.py                 # stack diagram, discharge plots, 2D/3D maps
cell_spec.py / parameters.py / model.py / sizing.py / simulation.py
                                # legacy re-export shims (notebook stays compatible)
run_pouch_cell.py               # thin CLI shim (python -m pouch_cell)
presets/*.json                  # named design+run presets
Pouch_Cell_3D_Tool.ipynb        # interactive demonstration notebook
```

## Quick start — Streamlit UI

Install the dependencies and launch the UI:

```bash
pip install -r requirements.txt      # or: pip install -e .
python -m pouch_cell --ui            # launches the Streamlit app
```

The UI has five pages: **Design** (geometry + auto-sizing), **Model & Run**,
**Thermal** (cooling preset / ambient / heat pipe / per-face h), **Results**
(metrics + figures) and **History** (comparison table + CSV export).  Tweak the
sidebar quick knobs (model, mesh, C-rate, duration, initial SOC), press
**Run**, and long solves run in a background process with a progress bar and a
**Cancel** button.  Named configurations are saved as JSON presets.

Command line (same engine):

```bash
python -m pouch_cell --info                          # print the cell design
python -m pouch_cell                                 # 2+1D DFN discharge (slow)
python -m pouch_cell --tab-analysis --model SPM --duration 60
python -m pouch_cell --preset default_9Ah            # run a named preset
```

## How the 20-stack is modelled

A pouch cell of 20 parallel electrode pairs is electrically equivalent to a
**single representative layer** whose current-collector cross-sectional area is
20x larger.  PyBaMM captures this exactly through the parameter

```
"Number of electrodes connected in parallel to make a cell" = 20
```

which multiplies the current-collector area ``A_cc = L_y * L_z * n_parallel``.
The applied current density ``I / A_cc`` then reflects 20 layers sharing the
total current -- see ``pouch_cell/cell_spec.py`` for details.  This is the
approach recommended by PyBaMM itself (it internally assumes a single-layer
pouch cell; pybamm-team/PyBaMM#1777).

## Tab placement & resistive (Ohmic) heating

Tab placement matters: the two **2 cm x 2 cm tabs** draw current from the
surrounding current collector, so the in-plane current density concentrates near
each tab and the **resistive (Ohmic) heating** `Q = i^2 / sigma` peaks right
there, creating local hot spots.  In the 9 Ah cell the in-plane collector
current peaks at ~1-3 x 10^7 A/m^2 at the tabs (vs a few x 10^5 A/m^2 in the
bulk), making the current-collector Ohmic heating ~15-35x higher at the tabs.

This is captured by the **2+1D SPMe** model (potential-pair current collectors + `x-lumped` thermal) -- the physically complete electrochemistry (it includes the electrolyte transport that the SPM shortcut omits).  One call produces the 2x2 analysis figure:

```python
from pouch_cell import PouchCellSpec, PouchCellSimulation

spec = PouchCellSpec()
sim, sol, fig = PouchCellSimulation.tab_heating_analysis(
    spec, C_rate=1.0, duration_s=30)   # coarse mesh, uniform-profile particles
fig.savefig("tab_heating.png")
```

The four panels show the in-plane current density in each current collector
(computed from `|i_cc| = sigma_cc * |grad phi_cc|`), the total current-collector
Ohmic heating `Q = i^2/sigma`, and the resulting x-lumped temperature field --
tab positions are marked in red.

> The current-concentration and resistive-heating maps are robust (they are
> derived from the current-collector potential field).  Because this now uses
> **SPMe**, the electrolyte transport that caused the fast SPM 2+1D's voltage
> collapse / inflated temperature is included, so the temperature panel is
> physical.  The trade-off is runtime: 2+1D SPMe takes minutes per minute of
> simulated discharge (see the performance note below).

Or from the command line:

```bash
python -m pouch_cell --tab-analysis --model SPM --duration 60
```

## Getting started

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

### Notebook

Open `Pouch_Cell_3D_Tool.ipynb` and run all cells.  It walks through the cell
design, the 20-stack schematic, a full 1C discharge, and 3D visualisations.

### Command line

```bash
# 2+1D DFN (default, most detailed electrochemistry; SLOW - minutes of wall time)
python -m pouch_cell --duration 120

# tab-driven resistive-heating analysis (2+1D DFN, coarse mesh)
python -m pouch_cell --tab-analysis --duration 5

# quick 1D DFN design/calibration: full 1C discharge to cutoff (~1-2 s)
python -m pouch_cell --dimensionality 0 --discharge 1C --cutoff 2.5

# fast genuine-3D thermal (SPM electrochemistry; optional)
python -m pouch_cell --model SPM_3D --duration 120

# print the cell design and exit
python -m pouch_cell --info
```

Figures are written to `pouch_output/`.

> **Performance note.** The 2+1D "potential pair" pouch model (``DFN`` with
> `dimensionality=2`) is the most detailed electrochemistry and is the
> default, but it is slow in current PyBaMM releases -- minutes per minute of
> simulated discharge, even on a coarse mesh with uniform-profile particles.
> It is the default because it resolves the full electrolyte transport (the
> fast SPM shortcut omits it and shows a voltage-collapse / inflated-
> temperature artifact; SPMe is the reduced-order intermediate).  For fast
> runs use `dimensionality=0` (1D DFN, ~1-2 s full discharge) for
> design/calibration, or `--model SPM_3D` for genuine-3D thermal.

### Solver & mesh (runtime tuning)

The **solver choice barely affects runtime** -- the default
`pybamm.IDAKLUSolver` is the fastest option.  `pybamm.CasadiSolver` is
deprecated in PyBaMM 26.8 and gives no speed-up here, so there is normally no
reason to change it.  If you do want to, pass `solver=` to
`PouchCellSimulation(...)` / `tab_heating_analysis(...)` (it is forwarded to
`pybamm.Simulation`), or use the CLI flag:

```bash
python -m pouch_cell --solver idaklu           # default (explicit)
python -m pouch_cell --solver casadi-fast      # deprecated but available
```

### Mesh density

The 2+1D mesh presets are set to **2x mesh density** (``draft`` = x8 / r12 /
y24 z36, ``standard`` = x16 / r20 / y40 z60, ``fine`` = x24 / r30 / y64 z96,
and the tab-analysis presets ``coarse_21d`` / ``micro_21d`` are doubled too).
This raises the spatial fidelity of the 2+1D "3D pouch" models -- the DFN tab
tab-analysis at the smallest ``micro_21d`` now takes ~1 min for 5 s of
discharge (was ~5 s).  Pass a custom ``var_pts`` dict to override.

The true-3D FEM presets (``draft_3d`` / ``standard_3d`` / ``fine_3d``) are
**not** doubled: at ``draft_3d = 0.0025`` (2x) the ``SPM_3D`` solve is
intractable in PyBaMM 26.8 -- a 15 s discharge took >18 min wall.  Pass a
custom element size (e.g. ``mesh=0.0025``) for finer 3D FEM if you can wait.

### Acceleration options (verified on PyBaMM 26.8)

Assessed against the four mechanisms in the PyBaMM docs:

| Method | Works here? | Notes |
|---|---|---|
| **Parallel parameter sweeps** | **Yes** (0D/1D) | `PouchCellSimulation.parallel_sweep(C_rates=..., nproc=...)` runs a C-rate sweep in one IDAKLU multi-input solve across `nproc` workers. Speed-up grows with model cost. **Not** available for the 2+1D potential-pair models (an input current breaks their current-collector boundary-condition discretisation -- verified). |
| **OpenMP single-solve** | **No** | `num_threads` maps to `num_solvers` (multi-input parallelism only); the single-solve `NVECTOR_OPENMP` path is not implemented in PyBaMM 26.8. Verified: `num_threads=2` on one 2+1D DFN solve was *slower* (thread overhead). |
| **GPU (JAX)** | **No** | Requires a CUDA/JAX install (fragile on Windows); `pybamm.JaxSolver` does not support **events**, which breaks the `until 2.5 V` experiment cutoffs; the JAX-backed IDAKLU GPU backend is experimental. |
| **Events** | Already used | IDAKLU's Sundials event handling powers the experiment cutoffs -- a reason to keep IDAKLU (the pure-JAX solver lacks events). |
| **t_eval / t_interp** | Yes (direct solves) | `sim.solve(t_eval, t_interp=...)` integrates only to the coarse `t_eval` stops and interpolates dense output at `t_interp` without stopping. |

```python
# parallel C-rate sweep on the fast 1D DFN design model
sols, rates = PouchCellSimulation.parallel_sweep(
    C_rates=(0.5, 1.0, 2.0), duration_s=60, nproc=4)

# 2+1D C-rate sweep via process-level parallelism (works for any model)
res, rates = PouchCellSimulation.parallel_sweep(
    C_rates=(0.5, 1.0), duration_s=5, processes=2,
    model_name="DFN", dimensionality=2, thermal="x-lumped", mesh="micro_21d")
# -> [(0.5, final_V), (1.0, final_V)]
```

**Compatibility:** the parallel sweep, events and `t_interp` are orthogonal
and combine freely (all under the IDAKLU solver).  GPU/JAX is incompatible
with the experiment/event workflow.  Bottom line: none of these methods remove
the ~5-10 s DAE wall of the 2+1D models or the FEM cost of `SPM_3D` -- those
are intrinsic to PyBaMM 26.8; the practical accelerations are parallel sweeps
and `t_interp` (dense output without extra solver stops).

### More acceleration levers (implemented)

- **`output_variables=[...]`** -- restrict the returned solution to the
  variables you need.  The 2+1D and `SPM_3D` solutions otherwise return the
  complete (very large) state vector; this cuts memory and post-processing
  time without changing the integration.  Pass to `PouchCellSimulation(...)`.
- **`store_first_last=True`** -- store only the first/last sample of each
  integration window (memory-light; trades away dense time output).
- **`period="10 seconds"`** on `discharge(...)` / `run_experiment(...)` --
  control the spacing of saved output points; a coarser period saves fewer
  points and reduces post-processing cost (the model is still integrated
  fully).  Verified: 28 -> 4 saved points, identical final voltage.
- **Process-level parallelism** -- `parallel_sweep(..., processes=N)` solves
  each C-rate in its own process (fixed current, no input parameter), so it
  works for the 2+1D models too (the multi-input path does not).  Callers
  under a notebook kernel are fine; standalone scripts must guard with
  `if __name__ == "__main__":` (Windows spawn).

### Why tab analysis is limited to ~5 s (and how to go further)

DFN/SPMe 2+1D has a **hard numerical wall**: it integrates 1-5 s of 1C
discharge in seconds, then hits `SolverError: IDA_ERR_FAIL` (DAE minimum step
size) at ~5-10 s.  This was verified systematically -- **no** solver setting
(looser `rtol`/`atol`, `suppress_algebraic_error`, `max_error_test_failures`),
`thermal="isothermal"`, a smaller mesh, or chaining short experiment steps gets
past it.  It is intrinsic to the 2+1D potential-pair + electrolyte-transport
DAE in PyBaMM 26.8.

`tab_heating_analysis` therefore defaults to a 5 s discharge on the smallest
`micro_21d` mesh (2x density, ~1 min wall time) and does **not** auto-size the
electrodes to 9 Ah (the auto-sizer's thinner electrodes make the 2+1D DAE
noticeably stiffer).  The tab current-concentration is a transient visible
within the first seconds, so a 5 s run captures the full spatial distribution.

For **longer tab runs (60 s+)**, use the same potential-pair architecture with
SPM electrochemistry:

```python
sim_tab, sol_tab, fig_tab = PouchCellSimulation.tab_heating_analysis(
    spec, C_rate=1.0, duration_s=60, model_name="SPM")   # ~1 s wall
```

or on the CLI:

```bash
python -m pouch_cell --tab-analysis --model SPM --duration 60
```

SPM 2+1D has no electrolyte transport, so it runs 60 s in about a second.  Its
temperature **magnitudes** are inflated (hot-spot *locations* are correct), so
use it for the long-time spatial trend, not quantitative temperatures.  For
genuine-3D long runs use `SPM_3D`.

### Python API

```python
from pouch_cell import PouchCellSpec, PouchCellSimulation, plotting

spec = PouchCellSpec()               # configurable multi-stack pouch (defaults in PouchCellSpec)

# --- 2+1D DFN: the default, most detailed electrochemical 3D model ---
sim = PouchCellSimulation(spec)                    # model_name defaults to DFN
sol = sim.discharge(C_rate=1.0, duration_s=120)    # slow: minutes of wall time
plotting.plot_current_density_map(sol)
plotting.plot_temperature_map(sol)

# --- tab-driven resistive-heating analysis (2+1D DFN) ---
# defaults: 5 s discharge on the smallest 2x-density mesh -> ~1 min wall.
# Longer than ~10 s hits IDA_ERR_FAIL (DAE min step size); see "Solver & mesh".
sim_tab, sol_tab, fig_tab = PouchCellSimulation.tab_heating_analysis(
    spec, C_rate=1.0)   # or duration_s=5, mesh="micro_21d"

# --- fast 1D DFN calibration (full discharge, ~1-2 s) ---
sim1d = PouchCellSimulation(spec, model_name="DFN", dimensionality=0,
                            thermal="lumped", mesh="draft")
sol1d = sim1d.discharge(C_rate=1.0)
plotting.plot_discharge(sol1d, spec)

# --- optional: genuine 3D FEM thermal (uses SPM electrochemistry; fast) ---
sim3 = PouchCellSimulation(spec, model_name="SPM_3D", mesh="draft")
sol3 = sim3.discharge(C_rate=1.0, duration_s=60)
plotting.plot_3d_cross_section(sol3, plane="yz")
```

## Models

| `model_name` | Description | Speed |
|--------------|-------------|-------|
| `DFN` (default) | Doyle–Fuller–Newman -- most detailed (full electrolyte transport); the default for all electrochemical runs | 1D fast (~1-2 s); 2+1D slow (min/min) |
| `SPMe` | Single Particle Model **with electrolyte** (reduced-order intermediate) | 1D fast; 2+1D slow (min/min) |
| `SPM_3D` | Genuine 3D finite-element thermal, SPM electrochemistry | fast (s-min) |
| `SPM` | Single Particle Model (no electrolyte transport -- fast but shows a 2+1D voltage-collapse artifact) | 1D fast; 2+1D medium |
| `DFN` | Doyle–Fuller–Newman, most detailed | 1D medium; 2+1D very slow |

All models default to the **SPMe** electrochemical description where relevant.
`SPM` and `SPM_3D` remain available for fast/3D-thermal purposes only.

For the 2+1D models, `dimensionality` selects the current-collector resolution
(2 = in-plane y and z, 1 = along z only, 0 = lumped).  `thermal` selects
`isothermal`, `lumped`, or `x-lumped` (in-plane temperature map).

> `thermal="lumped"` is not compatible with `dimensionality=2` in current
> PyBaMM (the lumped temperature is not broadcast over the 2D current
> collector); use `x-lumped` for 2D.

## Design inputs

All parameters live in `PouchCellSpec`.  Electrode thicknesses are **automatically
sized** (`size_to_capacity=True`) so the cell delivers the requested `capacity_Ah`
to the lower voltage cut-off, keeping the N/P ratio fixed.  Disable with
`PouchCellSimulation(..., size_to_capacity=False)`.

Chemistry: the `Chen2020` parameter set is used (its `nmc_LGM50` positive
electrode is NCM811 and `graphite_LGM50` negative electrode is graphite).
`OKane2022` is also available (NCM811 with a graphite/SiOx-blend anode and
degradation parameters).

## Thermal dissipation & active cooling

Dissipation is modelled with Newton's law of cooling ``Q = h * A * (T - T_amb)``
using a uniform heat-transfer coefficient ``h`` (default 5 W/m^2/K, natural
convection) and a uniform ambient temperature.  The ``cooling=`` option on
``PouchCellSimulation`` wraps the underlying PyBaMM parameters:

* **preset strings** set the uniform ``h``: ``"natural"`` (5),
  ``"forced_air"`` / ``"fan"`` (50), ``"liquid_cold_plate"`` / ``"cold_plate"``
  (500) W/m^2/K;
* **a dict** accepts ``heat_transfer_coefficient_W_m2K`` and
  ``ambient_temperature_K`` convenience keys **plus any PyBaMM parameter
  override** -- e.g. per-face coefficients for the true-3D model
  (``"bottom"``/``"top"``/``"left"``/``"right"``/``"front"``/``"back"``
  aliases) or a time-dependent coolant.

```python
# fan / forced convection on every surface
sim = PouchCellSimulation(spec, cooling="forced_air")

# chilled 15 C ambient + a liquid cold plate on the bottom face (SPM_3D)
sim = PouchCellSimulation(spec, model_name="SPM_3D", mesh="draft",
                          cooling={"ambient_temperature_K": 288.15,
                                   "bottom": 500.0, "top": 5.0})

# active cooling that switches on after 10 min (time-dependent ambient)
sim = PouchCellSimulation(
    spec, cooling={"Ambient temperature [K]":
                   lambda t: 288.15 if t < 600 else 298.15})
```

Which coefficient each thermal submodel reads: ``lumped`` (1D) uses the *Total*
coefficient + cooling surface area; ``x-lumped`` (2+1D) uses the current-
collector surface, edge and tab coefficients; ``SPM_3D`` uses the per-face
coefficients.  ``Ambient temperature [K]`` may be a function of space
``(y, z)`` and time (PyBaMM evaluates ``T_amb(y, z, t)``), so time-varying
active cooling is modelled through it.  The overrides are applied to ``param``
before solving and reach every thermal submodel.

``cooling=`` is also accepted by ``tab_heating_analysis(...)`` (it reaches the
``x-lumped`` thermal of the 2+1D model).  Verified: on a 60 s SPM 2+1D tab run
the final tab hot-spot temperature drops from **319.8 K** (natural) to
**301.5 K** with ``cooling="forced_air"``.

### Heat-pipe cooling of the tabs (full-width band below the top edge)

``PouchCellSpec`` carries an optional heat-pipe model for the tab region.
When ``heat_pipe_enabled=True``, a copper heat pipe runs **across the full
width** of the cell (along y), right below the top edge (``z = height``) -- a
horizontal band ``heat_pipe_height`` (0.5 cm) tall -- so it sits beside both
tabs.  It rejects to ``heat_pipe_temperature_K`` through an effective
``heat_pipe_h`` that lumps the folded tab + thermal paste + pipe + fin:

```python
from dataclasses import replace
spec_hp = replace(spec, heat_pipe_enabled=True)  # 0.5 cm-tall full-width band, h=2000, 288 K
sim, sol, fig = PouchCellSimulation.tab_heating_analysis(
    spec_hp, C_rate=1.0, duration_s=60, mesh="micro_21d", model_name="SPM")
```

Implementation: the 2+1D ``x-lumped`` thermal solves the in-plane heat
equation, so the pipe is applied as *space-varying* parameters --
``Ambient temperature [K]`` is set to the pipe temperature on the band (base
ambient elsewhere) and ``Edge heat transfer coefficient [W.m-2.K-1]`` is set
to ``heat_pipe_h`` on the band (base ``h`` elsewhere).  The localization uses
smooth PyBaMM Heaviside steps in ``(y, z)``.  It applies automatically to any
``dimensionality=2, thermal="x-lumped"`` solve (including
``tab_heating_analysis``); other thermal submodels are unaffected.

Verified on a 60 s SPM 2+1D tab run (h=2000 W/m^2/K, 288 K band): both tab
temperatures drop by ~20 K (negative **319.2 K -> 299.2 K**, positive
**319.4 K -> 299.7 K**) and the face hot-spot by **319.8 K -> 312.3 K**.

## Notes & limitations

* PyBaMM models one **representative** layer; the 20 parallel stacks are
  accounted for via the parallel-electrode scaling described above (this is the
  standard, physically-correct treatment for identical parallel layers).
* The outer 1 cm thickness includes packaging; the electrochemically active
  stack is ~3.5 mm (20 x ~175 um unit cells) plus shared current collectors.
* **SPMe is the default electrochemical model** everywhere (including the tab
  analysis), because it includes electrolyte transport.  The 2+1D SPMe is slow
  (minutes per minute of simulated discharge); use `dimensionality=0` for fast
  1D design/calibration.
* `SPM_3D` (genuine 3D FEM thermal) uses SPM electrochemistry and spans a
  single representative layer unless `full_stack_3d=True`.
* `SPM` is only offered for fast runs; in 2+1D it shows a voltage-collapse /
  inflated-temperature artifact (no electrolyte transport), so prefer SPMe.
