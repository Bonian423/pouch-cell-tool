"""Thermal page -- cooling preset, ambient, custom 2D cooling geometry,
per-face h, thermal-map preview and a parameter-override reference ordered
(i) curated -> (iii) examples -> (ii) full table last.
"""
import json

import streamlit as st

from pouch_cell.thermal.cooling_geometry import (
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
    # cooling is defined per region below; the uniform whole-face preset is no
    # longer exposed (the face outside the regions uses natural convection)
    thermal.cooling = None
    thermal.heat_transfer_coefficient_W_m2K = None
    if cfg.thermal == "isothermal":
        st.caption(
            "Cooling has no effect with the `isothermal` thermal model."
        )
    amb = st.number_input(
        "Ambient temperature (K)", 250.0, 350.0,
        float(thermal.ambient_temperature_K or spec.ambient_temperature_K),
        0.5, key="t_amb",
    )
    thermal.ambient_temperature_K = amb
    st.caption(
        "Cooling is defined per cooling region below; the rest of the face "
        "uses natural convection (h = 5 W/m²/K)."
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
            "perimeter cooling). Each region has a **geometry preset** (fills "
            "shape/size from the cell dimensions) and a **cooling method** "
            "(fills h and, where the method has one, a patch temperature). "
            "The face outside the regions uses natural convection. Blue = "
            "surface patch, green = edge band (on the thermal maps)."
        )
        if not spec.cooling_regions:
            st.caption("No cooling regions defined yet — add one below.")

        _GEO_PRESETS = ["— custom —", "top-edge band", "whole-face", "patch"]
        _GEO_KEYS = ["category", "shape", "y0", "z0", "w", "h", "r",
                     "edge", "along_start", "along_end", "depth"]
        _GEO_INPUT_KEYS = ["shape", "y0", "z0", "w", "h", "r", "edge",
                           "along_start", "along_end", "depth", "cat"]
        _COOL_METHODS = ["— custom —", "natural", "forced_air",
                         "liquid_cold_plate"]

        def _apply_geo_preset(i: int) -> None:
            chosen = st.session_state.get(f"t_cg_{i}_gpreset")
            if not chosen or chosen == "— custom —":
                return
            reg = spec.cooling_regions[i]
            _geo = preset_regions(chosen, spec)[0]
            for _k in _GEO_KEYS:
                reg.pop(_k, None)
            reg.update({_k: _geo.get(_k) for _k in _GEO_KEYS if _k in _geo})
            reg["geo_preset"] = chosen
            reg["_reset_geo"] = True
            st.rerun()

        def _mark_geo_custom(i: int) -> None:
            spec.cooling_regions[i]["geo_preset"] = None

        def _apply_cool_method(i: int) -> None:
            chosen = st.session_state.get(f"t_cg_{i}_cmethod")
            reg = spec.cooling_regions[i]
            if chosen == "natural":
                reg.update({"cool_method": "natural", "h_patch": 5.0})
                reg.pop("T_patch", None)
            elif chosen == "forced_air":
                reg.update({"cool_method": "forced_air", "h_patch": 50.0})
                reg.pop("T_patch", None)
            elif chosen == "liquid_cold_plate":
                reg.update({"cool_method": "liquid_cold_plate",
                            "h_patch": 500.0, "T_patch": 288.15})
            else:
                reg["cool_method"] = None
            reg["_reset_cool"] = True
            st.rerun()

        def _mark_cool_custom(i: int) -> None:
            spec.cooling_regions[i]["cool_method"] = None

        for i, r in enumerate(spec.cooling_regions):
            r.setdefault("geo_preset", None)
            r.setdefault("cool_method", None)
            # a preset was just applied: clear stale geometry / h-T widget keys
            # BEFORE those widgets are instantiated this run
            if r.pop("_reset_geo", False):
                for _k in _GEO_INPUT_KEYS:
                    sk = f"t_cg_{i}_{_k}"
                    if sk in st.session_state:
                        del st.session_state[sk]
            if r.pop("_reset_cool", False):
                for _k in ("hp", "T"):
                    sk = f"t_cg_{i}_{_k}"
                    if sk in st.session_state:
                        del st.session_state[sk]
            _cat = region_category(r)
            _cat_label = ("2D surface patch" if _cat == "surface"
                          else "Pseudo-1D edge patch")
            with st.expander(f"Region {i + 1} — {_cat_label}", expanded=True):
                # ---- row 1: geometry preset | category | cooling method ----
                c0a, c0b, c0c = st.columns([1.1, 1.2, 1.2])
                _gk = f"t_cg_{i}_gpreset"
                if r.get("geo_preset") is None and _gk in st.session_state:
                    del st.session_state[_gk]
                _gidx = (_GEO_PRESETS.index(r["geo_preset"])
                         if r["geo_preset"] in _GEO_PRESETS else 0)
                c0a.selectbox(
                    "Geometry preset", _GEO_PRESETS, index=_gidx, key=_gk,
                    on_change=_apply_geo_preset, args=(i,),
                    help="Pre-fill this region's shape/size from the cell "
                         "dimensions (top-edge band = the old heat pipe). "
                         "Editing the geometry below switches back to custom.",
                )
                c0b.selectbox(
                    "Category",
                    ["2D surface patch", "Pseudo-1D edge patch"],
                    index=0 if _cat == "surface" else 1,
                    key=f"t_cg_{i}_cat", on_change=_mark_geo_custom, args=(i,),
                    help="2D surface patch = rect/ellipse on the large faces "
                         "(both faces). Pseudo-1D edge patch = a band along "
                         "one cell edge (perimeter cooling).",
                )
                r["category"] = "surface" if _cat == "2D surface patch" else "edge"
                r.pop("target", None)
                _ck = f"t_cg_{i}_cmethod"
                if r.get("cool_method") in (None, "— custom —") and _ck in st.session_state:
                    del st.session_state[_ck]
                _midx = (_COOL_METHODS.index(r["cool_method"])
                         if r["cool_method"] in _COOL_METHODS else 0)
                c0c.selectbox(
                    "Cooling method", _COOL_METHODS, index=_midx, key=_ck,
                    on_change=_apply_cool_method, args=(i,),
                    help="Fills this region's h (and a patch temperature where "
                         "the method has one). Pick 'custom' to enter values "
                         "by hand; editing h/T below switches to custom.",
                )
                # ---- row 2: geometry fields ----
                c1, c2 = st.columns(2)
                if r["category"] == "surface":
                    c2.caption("Applied to BOTH large faces.")
                    c1b, c2b, c3b = st.columns(3)
                    r["shape"] = c1b.selectbox(
                        "Shape", ["rect", "ellipse"],
                        index=0 if r.get("shape", "rect") == "rect" else 1,
                        key=f"t_cg_{i}_shape", on_change=_mark_geo_custom,
                        args=(i,),
                    )
                    r["y0"] = c2b.number_input(
                        "y0 (cm)", 0.0, 50.0, float(r.get("y0", 0.05)) * 100.0,
                        0.5, key=f"t_cg_{i}_y0", on_change=_mark_geo_custom,
                        args=(i,),
                    ) / 100.0
                    r["z0"] = c3b.number_input(
                        "z0 (cm)", 0.0, 50.0, float(r.get("z0", 0.05)) * 100.0,
                        0.5, key=f"t_cg_{i}_z0", on_change=_mark_geo_custom,
                        args=(i,),
                    ) / 100.0
                    if r.get("shape") == "ellipse":
                        r["r"] = c1b.number_input(
                            "radius (cm)", 0.1, 50.0,
                            float(r.get("r", 0.01)) * 100.0, 0.5,
                            key=f"t_cg_{i}_r", on_change=_mark_geo_custom,
                            args=(i,),
                        ) / 100.0
                        r.pop("w", None)
                        r.pop("h", None)
                    else:
                        r["w"] = c1b.number_input(
                            "width (cm)", 0.1, 50.0,
                            float(r.get("w", 0.05)) * 100.0, 0.5,
                            key=f"t_cg_{i}_w", on_change=_mark_geo_custom,
                            args=(i,),
                        ) / 100.0
                        r["h"] = c2b.number_input(
                            "height (cm)", 0.1, 50.0,
                            float(r.get("h", 0.05)) * 100.0, 0.5,
                            key=f"t_cg_{i}_h", on_change=_mark_geo_custom,
                            args=(i,),
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
                        key=f"t_cg_{i}_edge", on_change=_mark_geo_custom,
                        args=(i,),
                    )
                    r["along_start"] = c2b.number_input(
                        "Along start (cm)", 0.0, 50.0,
                        float(r.get("along_start", 0.0)) * 100.0, 0.5,
                        key=f"t_cg_{i}_astart", on_change=_mark_geo_custom,
                        args=(i,),
                    ) / 100.0
                    r["along_end"] = c3b.number_input(
                        "Along end (cm)", 0.0, 50.0,
                        float(r.get("along_end", 0.05)) * 100.0, 0.5,
                        key=f"t_cg_{i}_aend", on_change=_mark_geo_custom,
                        args=(i,),
                    ) / 100.0
                    r["depth"] = c1b.number_input(
                        "Band depth (cm)", 0.1, 10.0,
                        float(r.get("depth", 0.005)) * 100.0, 0.1,
                        key=f"t_cg_{i}_depth", on_change=_mark_geo_custom,
                        args=(i,),
                    ) / 100.0
                    c2b.caption("Along = distance along the edge (0 = corner); "
                                "depth = band width into the cell.")
                    for _k in ("shape", "y0", "z0", "w", "h", "r"):
                        r.pop(_k, None)
                # ---- row 3: h / T (the cooling method fills these) ----
                c1c, c2c = st.columns(2)
                r["h_patch"] = c1c.number_input(
                    "Patch h (W/m²/K)", 0.0, 100000.0,
                    float(r.get("h_patch", 5.0)), 50.0, key=f"t_cg_{i}_hp",
                    on_change=_mark_cool_custom, args=(i,),
                )
                r["T_patch"] = c2c.number_input(
                    "Patch temperature (K)", 250.0, 350.0,
                    float(r.get("T_patch", 288.15)), 0.5, key=f"t_cg_{i}_T",
                    on_change=_mark_cool_custom, args=(i,),
                )
                if st.button("Remove region", key=f"t_cg_{i}_rm"):
                    del spec.cooling_regions[i]
                    st.rerun()
        if st.button("+ Add cooling region"):
            spec.cooling_regions.append({
                "category": "surface", "shape": "rect",
                "y0": spec.width / 2.0, "z0": spec.height / 2.0,
                "w": spec.width * 0.2, "h": spec.height * 0.2,
                "h_patch": 500.0, "T_patch": 288.15,
                "cool_method": "liquid_cold_plate", "geo_preset": None,
            })
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
