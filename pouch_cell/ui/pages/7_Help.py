"""Help page -- one section per tab, generated from the registry + notes."""
import streamlit as st

from pouch_cell import registry
from pouch_cell.ui import common

common.page_setup()

st.title("Help")
with common.page_body():
    st.markdown(
        "This tool simulates a **9 Ah NCM 811 / graphite pouch cell** (20 "
        "stacks, 15 × 9 × 1 cm) with the **Doyle–Fuller–Newman (DFN)** family "
        "of models from [PyBaMM](https://pybamm.org). The workflow is: pick a "
        "**model** and **parameter set** (Model & Run), define the **geometry** "
        "(Design), set **cooling / cooling geometry** (Thermal), choose the "
        "**protocol** (Protocols), then **Run** and review in **Results** / "
        "**History**."
    )
    st.caption(
        "**Right panel** (on every page): a live cell schematic — red = tabs, "
        "blue = cooling area (both surface patches and edge bands), black = "
        "cell, dashed = dimensions — the **run condition** (model · dim · "
        "thermal · mesh · parameter set · SOC · solver) and the **changed "
        "parameters**."
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
        "seconds (`IDA_ERR_FAIL`). For tab / protocol runs with thermal maps, "
        "SPM is the reliable choice and is auto-selected when needed."
    )

    # ------------------------------------------------------------------ Design
    st.markdown("## 2 · Design")
    st.markdown(
        """
    - **Footprint / stack / capacity** set the pouch geometry. Changing
      capacity, footprint or stack count triggers an **auto-size** solve that
      re-thins the electrodes to hit the target capacity (turn **Manual
      thicknesses** on to disable it).
    - **Unit-cell layers** — negative electrode `L_n`, positive `L_p`,
      separator `L_s`, collectors `L_cn` / `L_cp` (µm).
    - **Tabs** sit on the top edge (2 × 2 cm by default); their positions drive
      where current concentrates and heats up.
    - **Electrochemistry overrides** — curated knobs (porosity, particle
      radius, Bruggeman, conductivity, ...) plus a searchable full parameter
      table. Edits go into the solve's `ParameterValues` via `extra_overrides`.
    - **Save / import custom parameter sets** sits at the **top** of the page:
      save the current overrides as a named set (picked as the parameter set
      on Model & Run), or import a saved set back into the editor.
    """
    )

    # ------------------------------------------------------------------ Thermal
    st.markdown("## 3 · Thermal")
    st.markdown(
        """
    - **Ambient temperature (K)** sets the environment temperature for the
      whole cell.
    - **Cooling is region-based** — each cooling region carries its own
      **cooling method** that fills its heat-transfer coefficient (and, where
      the method has one, a patch temperature):
      - `natural` → h = 5 W/m²/K (ambient temperature)
      - `forced_air` → h = 50 W/m²/K (ambient temperature)
      - `liquid_cold_plate` → h = 500 W/m²/K, patch T = 288.15 K
      The rest of the face uses natural convection (h = 5 W/m²/K).
    - **Custom cooling geometry** — localised regions on the pouch face,
      applied in 2+1D `x-lumped` solves, in two categories:
      - **2D surface patch** — a rect / ellipse on the large faces (both
        faces).
      - **Pseudo-1D edge patch** — a band along one edge (top / bottom /
        left / right) with an adjustable **along**-length and **band depth**.
      Each region also has a **geometry preset** (`top-edge band` /
      `whole-face` / `patch`) that fills its shape and size from the cell
      dimensions — the **top-edge band** reproduces the old heat pipe. In the
      right-panel illustration both categories are drawn the same blue
      ("cooling area"); the Thermal editor keeps surface = blue / edge =
      green so you can tell them apart while editing.
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
    The run type is defined here and serialised into PyBaMM **Experiment**
    steps:

    ```
    Discharge at 1C for 10 minutes
    Charge at 0.5 C until 4.2 V
    Rest for 5 minutes
    Hold at 4.2 V until 0.45 A
    ```

    - **Single discharge / Single charge** — the quick CC / CC-CV presets.
    - **Custom multi-step** — every step ends when **any** of its end
      conditions fires (time / voltage / current / temperature / capacity).
      Add steps and set their **Type** in the table:
      - `discharge` / `charge` — constant current (C-rate, A or W), `hold` —
        constant voltage, `rest` — zero current.
      - **`loop`** — a pure control marker: pick an earlier step to **loop
        back to** and set **×N** (total times the block repeats). The repeated
        block is the steps between the target and the loop row; loop rows are
        never solved themselves. Nested and sequential loops are allowed, and
        repeating the whole protocol is just a loop targeting step 1 (there is
        no separate cycles box).
    - **Run conditions** — a universal termination / boundary editor: add
      multiple conditions, each with its own settings:
      - **Ambient / experiment temperature** — sets the environment
        temperature.
      - **Cell temperature limit** — stops the run at a cell temperature;
        choose the **source** (volume-averaged or hot-spot). The **Default
        temperature source** selector appears when a temperature condition is
        present and also serves per-step temperature conditions.
      - **Voltage limit / Capacity / Time / Current** — stop the whole run.
        Voltage / capacity-% / time also stop the solver cleanly; the rest are
        checked at step ends (post-hoc).
    - **Save / load protocol** — at the top of the page; persists to
      `pouch_output/protocols/`.
    - **Thermal maps** — when on, a 2+1D model is auto-selected and per-step
      maps are saved (`step_<cycle>_<step>.png`).
    """
    )

    # ------------------------------------------------------------------ Results
    st.markdown("## 5 · Results")
    st.markdown(
        """
    - **Metrics** — final voltage, delivered capacity, T max / T final.
    - **Per-step table** — for protocols, cycle · step · end time · end
      voltage · capacity per step, plus the **wall time spent solving each
      step** (`solve_s`).
    - **Run log & timing** — an expander with the stage-by-stage wall-time
      breakdown (load / build / live preview / solve / post-processing) and a
      downloadable `log.txt` — useful when a run feels slow.
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
    - **Save session** persists to `pouch_output/history.jsonl`; saved runs can
      be loaded into Results or deleted.
    - Compare `Tmax_K` and `final_V` across cooling / cooling-geometry / mesh
      variants.
    """
    )

    st.divider()
    st.markdown(
        "**Parameter sets** available:\n\n"
        + "\n".join(
            f"- `{name}` — "
            f"{registry.parameter_set_meta(name).get('chemistry', '')} "
            f"({registry.parameter_set_meta(name).get('kind', '')}) — "
            f"{registry.parameter_set_meta(name).get('description', '')}"
            for name in registry.options("parameter_set")
        )
    )
