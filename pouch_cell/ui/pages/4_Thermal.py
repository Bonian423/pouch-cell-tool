"""Thermal page -- cooling preset, ambient, custom 2D cooling geometry,
per-face h, thermal-map preview and a parameter-override reference ordered
(i) curated -> (iii) examples -> (ii) full table last.
"""
import json

import streamlit as st

from pouch_cell import registry
from pouch_cell.thermal.cooling_geometry import (
    PRESET_NAMES,
    preset_regions,
    region_category,
)
from pouch_cell.ui import common
from pouch_cell.ui.params import (
    CURATED_THERMAL_PARAMS,
    EXAMPLE_OVERRIDES,
    example_json,
    quick_thermal_preview,
    render_curated_editors,
    render_param_table,
)

common.page_setup()

st.title("Thermal & cooling")
with common.page_body():
    spec = st.session_state.spec
    thermal = st.session_state.thermal
    cfg = st.session_state.config

    # ------------------------------------------------------------- cooling
    st.markdown("#### Cooling")
    _cooling_disabled = cfg.thermal == "isothermal"
    cool_opts = ["— none —"] + registry.options("cooling")
    c_val = thermal.cooling if isinstance(thermal.cooling, str) else "— none —"
    idx = cool_opts.index(c_val) if c_val in cool_opts else 0
    sel = st.selectbox(
        "Cooling preset", cool_opts, index=idx, key="t_preset",
        disabled=_cooling_disabled,
        help="Cooling only has an effect with a non-isothermal thermal model.",
    )
    thermal.cooling = None if sel == "— none —" else sel
    if _cooling_disabled:
        st.caption(
            "Cooling has no effect with the `isothermal` thermal model — the "
            "preset is preserved for when you switch back."
        )

    c1, c2 = st.columns(2)
    amb = c1.number_input(
        "Ambient temperature (K)", 250.0, 350.0,
        float(thermal.ambient_temperature_K or spec.ambient_temperature_K),
        0.5, key="t_amb",
    )
    thermal.ambient_temperature_K = amb
    h_ov = c2.number_input(
        "Heat-transfer coefficient override (W/m²/K, 0 = preset/natural)",
        0.0, 5000.0, float(thermal.heat_transfer_coefficient_W_m2K or 0.0),
        10.0, key="t_h",
    )
    thermal.heat_transfer_coefficient_W_m2K = h_ov or None

    if thermal.cooling:
        st.caption(
            f"Preset `{thermal.cooling}` h = "
            f"{registry.get('cooling', thermal.cooling)} W/m²/K"
        )

    # ------------------------------------------------------------- cooling geometry
    st.markdown("#### Custom cooling geometry (2D patches)")
    _cg_applicable = cfg.dimensionality == 2 and cfg.thermal == "x-lumped"
    if not _cg_applicable:
        st.caption(
            "Custom cooling geometry only applies in 2+1D `x-lumped` solves — "
            "with the current `{model}` · dim {dim} · `{th}` it would be "
            "ignored. Set **dim 2** + **`x-lumped`** on the Model & Run page to "
            "enable it.".format(model=cfg.model_name, dim=cfg.dimensionality,
                                th=cfg.thermal)
        )
    else:
        st.caption(
            "Define cooling regions in **two categories**: a **2D surface "
            "patch** (rect/ellipse on the large faces, applied to **both**) "
            "or a **pseudo-1D edge patch** (a band along one cell edge, "
            "perimeter cooling). **Presets** pre-fill ready-to-edit regions "
            "— the **top-edge band** is the old heat pipe. Blue = surface "
            "patch, green = edge band (shown on the thermal maps)."
        )
        if not spec.cooling_regions:
            st.caption("No cooling regions defined yet — pick a preset or add one.")
        pcols = st.columns(len(PRESET_NAMES))
        for ci, pname in enumerate(PRESET_NAMES):
            if pcols[ci].button(pname, key=f"t_cg_preset_{ci}", width="stretch"):
                spec.cooling_regions = preset_regions(pname, spec)
                st.rerun()
        for i, r in enumerate(spec.cooling_regions):
            _cat = region_category(r)
            _cat_label = ("2D surface patch" if _cat == "surface"
                          else "Pseudo-1D edge patch")
            with st.expander(f"Region {i + 1} — {_cat_label}", expanded=True):
                c1, c2 = st.columns(2)
                _cat = c1.selectbox(
                    "Category",
                    ["2D surface patch", "Pseudo-1D edge patch"],
                    index=0 if _cat == "surface" else 1,
                    key=f"t_cg_{i}_cat",
                    help="2D surface patch = rect/ellipse on the large faces "
                         "(both faces). Pseudo-1D edge patch = a band along "
                         "one cell edge (perimeter cooling).",
                )
                r["category"] = "surface" if _cat == "2D surface patch" else "edge"
                r.pop("target", None)
                if r["category"] == "surface":
                    c2.caption("Applied to BOTH large faces.")
                    c1b, c2b, c3b = st.columns(3)
                    r["shape"] = c1b.selectbox(
                        "Shape", ["rect", "ellipse"],
                        index=0 if r.get("shape", "rect") == "rect" else 1,
                        key=f"t_cg_{i}_shape",
                    )
                    r["y0"] = c2b.number_input(
                        "y0 (cm)", 0.0, 50.0, float(r.get("y0", 0.05)) * 100.0,
                        0.5, key=f"t_cg_{i}_y0",
                    ) / 100.0
                    r["z0"] = c3b.number_input(
                        "z0 (cm)", 0.0, 50.0, float(r.get("z0", 0.05)) * 100.0,
                        0.5, key=f"t_cg_{i}_z0",
                    ) / 100.0
                    if r.get("shape") == "ellipse":
                        r["r"] = c1b.number_input(
                            "radius (cm)", 0.1, 50.0,
                            float(r.get("r", 0.01)) * 100.0, 0.5,
                            key=f"t_cg_{i}_r",
                        ) / 100.0
                        r.pop("w", None)
                        r.pop("h", None)
                    else:
                        r["w"] = c1b.number_input(
                            "width (cm)", 0.1, 50.0,
                            float(r.get("w", 0.05)) * 100.0, 0.5,
                            key=f"t_cg_{i}_w",
                        ) / 100.0
                        r["h"] = c2b.number_input(
                            "height (cm)", 0.1, 50.0,
                            float(r.get("h", 0.05)) * 100.0, 0.5,
                            key=f"t_cg_{i}_h",
                        ) / 100.0
                        r.pop("r", None)
                    c2b.caption("centre (y0, z0) in cm: y across width, z up "
                                "the height, tabs at the top.")
                else:
                    c2.caption("Pseudo-1D band along one cell edge.")
                    c1b, c2b, c3b = st.columns(3)
                    _edges = ["top", "bottom", "left", "right"]
                    _cur_edge = r.get("edge", "top")
                    _cur_edge = _cur_edge if _cur_edge in _edges else "top"
                    r["edge"] = c1b.selectbox(
                        "Edge", _edges, index=_edges.index(_cur_edge),
                        key=f"t_cg_{i}_edge",
                    )
                    r["along_start"] = c2b.number_input(
                        "Along start (cm)", 0.0, 50.0,
                        float(r.get("along_start", 0.0)) * 100.0, 0.5,
                        key=f"t_cg_{i}_astart",
                    ) / 100.0
                    r["along_end"] = c3b.number_input(
                        "Along end (cm)", 0.0, 50.0,
                        float(r.get("along_end", 0.05)) * 100.0, 0.5,
                        key=f"t_cg_{i}_aend",
                    ) / 100.0
                    r["depth"] = c1b.number_input(
                        "Band depth (cm)", 0.1, 10.0,
                        float(r.get("depth", 0.005)) * 100.0, 0.1,
                        key=f"t_cg_{i}_depth",
                    ) / 100.0
                    c2b.caption("Along = distance along the edge (0 = corner); "
                                "depth = band width into the cell.")
                    for _k in ("shape", "y0", "z0", "w", "h", "r"):
                        r.pop(_k, None)
                c1c, c2c = st.columns(2)
                r["h_patch"] = c1c.number_input(
                    "Patch h (W/m²/K)", 0.0, 100000.0,
                    float(r.get("h_patch", 500.0)), 50.0, key=f"t_cg_{i}_hp",
                )
                r["T_patch"] = c2c.number_input(
                    "Patch temperature (K)", 250.0, 350.0,
                    float(r.get("T_patch", 288.15)), 0.5, key=f"t_cg_{i}_T",
                )
                if st.button("Remove region", key=f"t_cg_{i}_rm"):
                    del spec.cooling_regions[i]
                    st.rerun()
        if st.button("+ Add blank region"):
            spec.cooling_regions.append(
                {"shape": "rect", "target": "face", "y0": 0.05, "z0": 0.05,
                 "w": 0.05, "h": 0.05, "h_patch": 500.0, "T_patch": 288.15}
            )
            st.rerun()

    # ------------------------------------------------------------- per-face h
    if cfg.model_name == "SPM_3D":
        st.markdown("#### Per-face heat-transfer coefficients (SPM_3D)")
        cols = st.columns(3)
        for i, face in enumerate(["left", "right", "front", "back", "bottom", "top"]):
            with cols[i % 3]:
                cur = thermal.per_face_h.get(face, 5.0)
                thermal.per_face_h[face] = st.number_input(
                    f"{face.capitalize()} face h", 0.0, 5000.0, float(cur),
                    5.0, key=f"t_face_{face}",
                )

    # ------------------------------------------------------------- quick thermal map
    st.markdown("#### Thermal map preview")
    st.caption(
        "Run a fast coarse 2+1D SPM solve and draw the temperature / "
        "current-density / Ohmic-heating maps right here, so you can iterate "
        "on cooling and geometry settings before a full run. Pick a "
        "**protocol step** to draw the map at the end of that step instead of "
        "a fresh 5-second discharge."
    )
    st.caption(
        "The preview **always** runs `SPM` · 2+1D · `x-lumped` on a coarse "
        "mesh (a fast approximation) — it ignores the model/dim/thermal "
        "selections above."
    )
    proto = st.session_state.protocol
    _step_labels = ["Fresh 5 s discharge"] + [
        f"step {i + 1}: {s.to_string(spec.capacity_Ah)}"
        for i, s in enumerate(proto.steps)
    ]
    prev_step = st.selectbox("Preview at", _step_labels, key="t_prev_step")

    c1, c2 = st.columns([1, 3])
    if c1.button("Generate thermal map", type="primary"):
        if not common.is_full_cell_parameter_set(cfg.parameter_set):
            st.error(
                "This parameter set isn't a full lithium-ion cell set "
                "(half-cell / composite / MSMR / ECM / Na-ion) — the thermal "
                "preview needs a full-cell set. Pick one on the Model & Run page."
            )
        else:
            with st.spinner("Running quick 2+1D solve…"):
                if prev_step == "Fresh 5 s discharge":
                    st.session_state["quick_map"] = quick_thermal_preview(
                        spec, cfg, thermal
                    )
                else:
                    idx = _step_labels.index(prev_step) - 1
                    st.session_state["quick_map"] = quick_thermal_preview(
                        spec, cfg, thermal, steps=proto.steps, step_idx=idx
                    )
    qm = st.session_state.get("quick_map")
    if qm:
        if qm.get("ok"):
            st.image(qm["figure"], caption=f"Thermal preview ({qm.get('note', '')})", width="stretch")
            if qm.get("warning"):
                st.warning(qm["warning"])
            m = qm.get("metrics", {})
            st.caption(
                f"final V = {m.get('final_V', float('nan')):.3f} V · "
                f"Tmax = {m.get('Tmax_K', float('nan')):.1f} K"
            )
        else:
            st.error(f"Quick preview failed: {qm.get('error')}")

    # ------------------------------------------------------------- raw override
    st.markdown("#### Raw PyBaMM parameter overrides (advanced)")
    default_raw = (json.dumps(thermal.extra_overrides, indent=2)
                   if thermal.extra_overrides else "")
    raw = st.text_area(
        "JSON dict of parameter overrides (e.g. "
        '`{"Ambient temperature [K]": 288.15}`)',
        value=default_raw, key="t_raw", height=110,
    )
    try:
        parsed = json.loads(raw) if raw.strip() else {}
        thermal.extra_overrides = parsed if isinstance(parsed, dict) else {}
        if raw.strip() and not isinstance(parsed, dict):
            st.error("Overrides must be a JSON object.")
    except json.JSONDecodeError as err:
        st.error(f"Invalid JSON: {err}")
        thermal.extra_overrides = {}

    # ------------------------------------------------------------- override reference
    with st.expander("Parameter overrides — reference & examples", expanded=False):
        tab_curated, tab_examples, tab_table = st.tabs(
            ["Curated knobs", "Copy-ready examples", "Full parameter table"]
        )
        with tab_curated:  # (i) curated dict for the selected model
            render_curated_editors(
                cfg.parameter_set, thermal.extra_overrides,
                curated=CURATED_THERMAL_PARAMS,
                section_title="Thermal / material knobs",
            )
            st.caption(
                "Edits here are folded into the solve's `ParameterValues` "
                "(via the raw overrides dict above)."
            )
        with tab_examples:  # (iii) copy-ready examples
            st.caption("Click **Use** to load an example into the raw override box.")
            for label, _d in EXAMPLE_OVERRIDES:
                c1, c2 = st.columns([3, 1])
                c1.markdown(f"**{label}**")
                if c2.button("Use", key=f"ex_{label[:20]}"):
                    thermal.extra_overrides.update(_d)
                    st.rerun()
                st.code(example_json(label), language="json")
        with tab_table:  # (ii) full searchable table -- last
            render_param_table(cfg.parameter_set, thermal.extra_overrides)
            if st.button("Reset ALL thermal overrides"):
                thermal.extra_overrides.clear()
                st.rerun()

    st.divider()
    st.code(
        f"cooling = {thermal.to_cooling()}\n"
        f"cooling_regions = {len(spec.cooling_regions)} region(s)"
    )
