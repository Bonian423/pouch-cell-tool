"""User-defined 2D cooling geometry on the pouch face (2+1D ``x-lumped``).

The 2+1D ``x-lumped`` thermal model evaluates surface / edge cooling with
*space-varying* coefficients (``h_cc(y,z)``, ``h_edge(y,z)``, ``T_amb(y,z,t)``),
so a localised cooling region (a cold-plate patch on the large faces, or the
old heat-pipe band on the top edge) is expressed by making those parameters
functions of (y, z) -- high / chilled on the patch, base elsewhere.  The patch
is applied to **both** large faces (the negative- and positive-collector
sides), symmetric, matching a physical double-sided cold plate.

Regions are plain serialisable dicts (stored in
``PouchCellSpec.cooling_regions``)::

    {"shape": "rect" | "ellipse",
     "target": "face" | "edge",      # face = CC surface h (both faces) + T_amb
     "y0": m, "z0": m,               # centre (y in [0,width], z in [0,height])
     "w": m, "h": m,                 # rect full width/height
     "r": m,                         # ellipse radius
     "h_patch": W/m2/K, "T_patch": K}

This module absorbs the old :mod:`pouch_cell.thermal.heat_pipe` module, which
is kept as a thin backwards-compatible shim (the heat pipe is just the
"top-edge band" preset here).
"""
from __future__ import annotations

import pybamm


def region_predicate(y, z, region: dict):
    """A pybamm expression that is ~1 inside the region, ~0 outside.

    Built from pybamm comparison operators (smooth Heavisides) -- function-
    valued parameters are evaluated with *symbolic* children, so numpy
    closures would fail (the same constraint the heat pipe had).
    """
    shape = region.get("shape", "rect")
    y0 = float(region.get("y0", 0.0))
    z0 = float(region.get("z0", 0.0))
    if shape == "ellipse":
        r = float(region.get("r", 0.01))
        return ((y - y0) ** 2 + (z - z0) ** 2) <= r ** 2
    w = float(region.get("w", 0.05))
    h = float(region.get("h", 0.05))
    y_lo, y_hi = y0 - w / 2.0, y0 + w / 2.0
    z_lo, z_hi = z0 - h / 2.0, z0 + h / 2.0
    return (y >= y_lo) * (y <= y_hi) * (z >= z_lo) * (z <= z_hi)


def region_overrides(spec, regions, h_base: float, T_base: float) -> dict:
    """Parameter overrides for a list of cooling regions on the y-z face.

    ``face`` regions boost the current-collector surface ``h`` (both faces)
    and chill ``T_amb`` on the patch; ``edge`` regions boost the perimeter
    ``h_edge`` (the old heat-pipe band).  Every value is layered on top of the
    uniform base scalars so the rest of the face keeps the chosen cooling.
    """
    regions = [r for r in (regions or []) if r]
    if not regions:
        return {}
    face_regs = [r for r in regions if r.get("target", "face") == "face"]
    edge_regs = [r for r in regions if r.get("target") == "edge"]

    def _T_amb(y, z, t):
        T = T_base
        for r in regions:
            p = region_predicate(y, z, r)
            T = T + (float(r.get("T_patch", T_base)) - T_base) * p
        return T

    out: dict = {"Ambient temperature [K]": _T_amb}
    if face_regs:
        def _h_cc(y, z):
            h = h_base
            for r in face_regs:
                p = region_predicate(y, z, r)
                h = h + (float(r.get("h_patch", h_base)) - h_base) * p
            return h

        out["Negative current collector surface heat transfer coefficient "
            "[W.m-2.K-1]"] = _h_cc
        out["Positive current collector surface heat transfer coefficient "
            "[W.m-2.K-1]"] = _h_cc
    if edge_regs:
        def _h_edge(y, z):
            h = h_base
            for r in edge_regs:
                p = region_predicate(y, z, r)
                h = h + (float(r.get("h_patch", h_base)) - h_base) * p
            return h

        out["Edge heat transfer coefficient [W.m-2.K-1]"] = _h_edge
    return out


# -- preset gallery -------------------------------------------------------- #
PRESET_NAMES = ("top-edge band (heat pipe)", "whole-face cold plate",
                "centre patch", "corner patch")


def preset_regions(name: str, spec) -> list[dict]:
    """Named cooling-geometry presets (each a ready-to-edit region list).

    ``"top-edge band (heat pipe)"`` reproduces the old top-edge heat pipe.
    """
    key = str(name).strip().lower()
    w = float(getattr(spec, "width", 0.1))
    h = float(getattr(spec, "height", 0.15))
    if key in ("top-edge band (heat pipe)", "top-edge band", "heat pipe",
               "heat_pipe", "heatpipe", "top_edge_band"):
        band = 0.005  # 0.5 cm band below the top edge (old heat_pipe_height)
        return [{
            "shape": "rect", "target": "edge",
            "y0": w / 2.0, "z0": h - band / 2.0, "w": w, "h": band,
            "h_patch": 2000.0, "T_patch": 288.15,
        }]
    if key in ("whole-face cold plate", "whole-face", "whole_face",
               "cold plate", "cold_plate"):
        return [{
            "shape": "rect", "target": "face",
            "y0": w / 2.0, "z0": h / 2.0, "w": w, "h": h,
            "h_patch": 500.0, "T_patch": 288.15,
        }]
    if key in ("centre patch", "centre", "center", "centre patch (ellipse)"):
        return [{
            "shape": "ellipse", "target": "face",
            "y0": w / 2.0, "z0": h / 2.0, "r": min(w, h) * 0.2,
            "h_patch": 500.0, "T_patch": 288.15,
        }]
    if key in ("corner patch", "corner"):
        return [{
            "shape": "rect", "target": "face",
            "y0": 0.02, "z0": 0.02, "w": 0.04, "h": 0.04,
            "h_patch": 500.0, "T_patch": 288.15,
        }]
    raise ValueError(f"Unknown cooling-geometry preset '{name}'.")


# Backwards-compatible aliases: the old heat-pipe band is the "heat_pipe"
# preset, exposed as before for code that imported heat_pipe_overrides.
def heat_pipe_overrides(spec, h_base: float, T_base: float) -> dict:
    """(Legacy) the old top-edge heat-pipe band, as cooling-region overrides."""
    return region_overrides(spec, preset_regions("heat_pipe", spec),
                            h_base, T_base)


_heat_pipe_overrides = heat_pipe_overrides
