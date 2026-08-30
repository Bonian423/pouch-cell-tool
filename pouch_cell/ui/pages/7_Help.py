"""Help page -- one section per tab, generated from the registry + notes."""
import streamlit as st

from pouch_cell import registry
from pouch_cell.ui import common

common.init_state()
common.render_sidebar()

st.title("Help")

st.markdown(
    "This tool simulates a **9 Ah NCM 811 / graphite pouch cell** (20 stacks, "
    "15 × 9 × 1 cm) with the **Doyle–Fuller–Newman (DFN)** family of models "
    "from [PyBaMM](https://pybamm.org). The workflow is: pick a **model** and "
    "**parameter set** (Model & Run), define the **geometry** (Design), set "
    "**cooling / heat pipe** (Thermal), choose the **protocol** (Protocols), "
    "then **Run** and review in **Results** / **History**."
)

# ------------------------------------------------------------------ Model & Run
st.markdown("## 1 · Model & Run")
st.markdown(
    """
| Option | Meaning |
|---|---|
| **Model** | DFN (full porous-electrode) · SPMe (single particle + electrolyte) · SPM (single particle, fastest) · SPM_3D (true 3D FEM, very slow) |
| **Dimensionality** | 0 = through-plane only · 1 = pseudo-2D · **2 = 2+1D** with in-plane current collectors (needed for tab / thermal maps) |
| **Thermal** | isothermal · lumped · x-lumped (through-thickness resolved + in-plane for dim 2) · x-full (dim 0) |
| **Mesh** | 2+1D presets are **2× the original mesh density**; `micro_21d` is the lightest 2+1D mesh (r=1, uniform-profile particles) |
| **Solver** | default (Casadi) · idaklu · casadi-fast / casadi-safe |
"""
)
st.caption(
    "**2+1D limit**: DFN/SPMe on the 2+1D mesh are DAE-limited to a few "
    "seconds (`IDA_ERR_FAIL`). For tab / protocol runs with thermal maps, SPM "
    "is the reliable choice and is auto-selected when needed."
)

# ------------------------------------------------------------------ Design
st.markdown("## 2 · Design")
st.markdown(
    """
- **Footprint / stack / capacity** set the pouch geometry. Changing capacity,
  footprint or stack count triggers an **auto-size** solve that re-thins the
  electrodes to hit the target capacity (turn **Manual thicknesses** on to
  disable it).
- **Unit-cell layers** — negative electrode `L_n`, positive `L_p`, separator
  `L_s`, collectors `L_cn` / `L_cp` (µm).
- **Tabs** sit on the top edge (2 × 2 cm by default); their positions drive
  where current concentrates and heats up.
- **Electrochemistry overrides** — curated knobs (porosity, particle radius,
  Bruggeman, conductivity, ...) plus a searchable full parameter table. Edits
  go into the solve's `ParameterValues` via `extra_overrides`.
"""
)

# ------------------------------------------------------------------ Thermal
st.markdown("## 3 · Thermal")
st.markdown(
    """
- **Cooling presets** map to a uniform surface heat-transfer coefficient
  (W/m²/K):
"""
)
for name, h in registry.COOLING_PRESETS.items():
    st.markdown(f"  - `{name}` → **{h} W/m²/K**")
st.markdown(
    """
- **Heat pipe** — a copper band across the full width just below the top edge,
  modelled as a high-h sink at the tabs (lowers tab hot-spot temperature).
- **Thermal map preview** runs a quick SPM 2+1D solve to show temperature /
  current-density / Ohmic-heating maps before committing to a full run.
- **Parameter overrides** — (i) curated knobs → (iii) copy-ready examples →
  (ii) full searchable table (last).
"""
)

# ------------------------------------------------------------------ Protocols
st.markdown("## 4 · Protocols")
st.markdown(
    """
The run type is defined here and serialised into PyBaMM **Experiment** steps:

```
Discharge at 1C for 10 minutes
Charge at 0.5 C until 4.2 V
Rest for 5 minutes
Hold at 4.2 V until 0.45 A
```

- **Single discharge** — CC discharge to a duration or cut-off.
- **Single charge** — CC-CV charge (optional rest).
- **Custom multi-step** — add/remove steps, repeat for **N cycles**, set an
  output **period**, an overall **termination** (e.g. `80% capacity`), and an
  experiment **temperature**.
- **Thermal maps** — when on, a 2+1D model is auto-selected and per-step maps
  are saved (`step_<cycle>_<step>.png`).
"""
)

# ------------------------------------------------------------------ Results
st.markdown("## 5 · Results")
st.markdown(
    """
- **Metrics** — final voltage, delivered capacity, T max / T final.
- **Per-step table** — for protocols, cycle · step · end time · end voltage ·
  capacity per step.
- **Figures** — discharge curve, `thermal_maps.png`, per-step maps (with a
  selector), `vt.csv` (V/T time series to download).
- **Saved runs** can be loaded back here for review without re-running.
"""
)

# ------------------------------------------------------------------ History
st.markdown("## 6 · History")
st.markdown(
    """
- Session table of every run in this server session (cleared on restart).
- **Save session** persists to `pouch_output/history.jsonl`; saved runs can be
  loaded into Results or deleted.
- Compare `Tmax_K` and `final_V` across cooling / heat-pipe / mesh variants.
"""
)

st.divider()
st.markdown(
    "**Parameter sets** available:\n\n"
    + "\n".join(
        f"- `{name}` — {registry.PARAMETER_SET_INFO.get(name, '')}"
        for name in registry.options("parameter_set")
    )
)
