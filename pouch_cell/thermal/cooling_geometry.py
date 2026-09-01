"""User-defined 2D cooling geometry on the pouch face (2+1D ``x-lumped``).

The 2+1D ``x-lumped`` thermal model evaluates surface / edge cooling with
*space-varying* coefficients (``h_cc(y,z)``, ``h_edge(y,z)``, ``T_amb(y,z,t)``),
so a localised cooling region (a cold-plate patch on the large faces, or the
old heat-pipe band on the top edge) is expressed by making those parameters
functions of (y, z) -- high / chilled on the patch, base elsewhere.  The patch
is applied to **both** large faces (the negative- and positive-collector
sides), symmetric, matching a physical double-sided cold plate.

Regions are plain serialisable dicts (stored in
``PouchCellSpec.cooling_regions``).  There are **two categories**:

* ``category = "surface"`` — a **2D patch on the large cell faces** (applied
  to **both** faces): ``{"shape": "rect"|"ellipse", "y0", "z0", "w", "h",
  "r", "h_patch", "T_patch"}``.
* ``category = "edge"`` — a **pseudo-1D patch along one cell edge** (applied
  to the perimeter ``h_edge``): ``{"edge": "top"|"bottom"|"left"|"right",
  "along_start", "along_end", "depth", "h_patch", "T_patch"}`` where
  ``along_start/along_end`` are the segment limits along the edge (m) and
  ``depth`` is the band width inwards (m).

The legacy ``target: "face"|"edge"`` field is still accepted (migrated on the
fly): ``face`` -> ``surface``, ``edge`` -> ``edge`` (old edge rects keep the
rect geometry).

This module absorbs the old :mod:`pouch_cell.thermal.heat_pipe` module, which
is kept as a thin backwards-compatible shim (the heat pipe is just the
"top-edge band" preset here).
"""
from __future__ import annotations

import pybamm


def region_category(region: dict) -> str:
    """The category of a region: ``"surface"`` or ``"edge"`` (migrates the
    legacy ``target`` field)."""
    cat = region.get("category")
    if cat in ("surface", "edge"):
        return cat
    if region.get("target") == "edge":
        return "edge"
    return "surface"


def _rect_ellipse_predicate(y, z, region: dict):
    """The legacy rect / ellipse in-plane predicate (surface patches)."""
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


def _edge_predicate(y, z, region: dict, height: float, width: float):
    """Pseudo-1D band along one edge (the band spans part of the edge)."""
    edge = str(region.get("edge", "top")).lower()
    a0 = min(float(region.get("along_start", 0.0)),
             float(region.get("along_end", 0.05)))
    a1 = max(float(region.get("along_start", 0.0)),
             float(region.get("along_end", 0.05)))
    d = max(0.0, float(region.get("depth", 0.005)))
    if edge == "bottom":
        return (y >= a0) * (y <= a1) * (z >= 0.0) * (z <= d)
    if edge == "left":
        return (z >= a0) * (z <= a1) * (y >= 0.0) * (y <= d)
    if edge == "right":
        return (z >= a0) * (z <= a1) * (y >= width - d) * (y <= width)
    # top
    return (y >= a0) * (y <= a1) * (z >= height - d) * (z <= height)


def region_predicate(y, z, region: dict, height: float = 0.15,
                     width: float = 0.1):
    """A pybamm expression that is ~1 inside the region, ~0 outside.

    Built from pybamm comparison operators (smooth Heavisides) -- function-
    valued parameters are evaluated with *symbolic* children, so numpy
    closures would fail (the same constraint the heat pipe had).
    """
    if region_category(region) == "edge" and region.get("edge"):
        return _edge_predicate(y, z, region, height, width)
    return _rect_ellipse_predicate(y, z, region)


def region_overrides(spec, regions, h_base: float, T_base: float) -> dict:
    """Parameter overrides for a list of cooling regions on the y-z face.

    ``surface`` regions boost the current-collector surface ``h`` (both
    faces) and chill ``T_amb`` on the patch; ``edge`` regions boost the
    perimeter ``h_edge`` (the pseudo-1D edge bands).  Every value is layered
    on top of the uniform base scalars so the rest of the face keeps the
    chosen cooling.
    """
    regions = [r for r in (regions or []) if r]
    if not regions:
        return {}
    height = float(getattr(spec, "height", 0.15))
    width = float(getattr(spec, "width", 0.1))
    surface_regs = [r for r in regions if region_category(r) == "surface"]
    edge_regs = [r for r in regions if region_category(r) == "edge"]

    def _on(r, y, z):
        return region_predicate(y, z, r, height=height, width=width)

    def _T_amb(y, z, t):
        T = T_base
        for r in regions:
            p = _on(r, y, z)
            T = T + (float(r.get("T_patch", T_base)) - T_base) * p
        return T

    out: dict = {"Ambient temperature [K]": _T_amb}
    if surface_regs:
        def _h_cc(y, z):
            h = h_base
            for r in surface_regs:
                p = _on(r, y, z)
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
                p = _on(r, y, z)
                h = h + (float(r.get("h_patch", h_base)) - h_base) * p
            return h

        out["Edge heat transfer coefficient [W.m-2.K-1]"] = _h_edge
    return out


# -- preset gallery -------------------------------------------------------- #
PRESET_NAMES = ("top-edge band (heat pipe)", "whole-face cold plate",
                "centre patch", "corner patch")


def preset_regions(name: str, spec) -> list[dict]:
    """Named cooling-geometry presets (each a ready-to-edit region list).

    ``"top-edge band (heat pipe)"`` reproduces the old top-edge heat pipe as a
    pseudo-1D edge band.
    """
    key = str(name).strip().lower()
    w = float(getattr(spec, "width", 0.1))
    h = float(getattr(spec, "height", 0.15))
    if key in ("top-edge band (heat pipe)", "top-edge band", "heat pipe",
               "heat_pipe", "heatpipe", "top_edge_band"):
        band = 0.005  # 0.5 cm band below the top edge (old heat_pipe_height)
        return [{
            "category": "edge", "edge": "top",
            "along_start": 0.0, "along_end": w, "depth": band,
            "h_patch": 2000.0, "T_patch": 288.15,
        }]
    if key in ("whole-face cold plate", "whole-face", "whole_face",
               "cold plate", "cold_plate"):
        return [{
            "category": "surface", "shape": "rect",
            "y0": w / 2.0, "z0": h / 2.0, "w": w, "h": h,
            "h_patch": 500.0, "T_patch": 288.15,
        }]
    if key in ("centre patch", "centre", "center", "centre patch (ellipse)"):
        return [{
            "category": "surface", "shape": "ellipse",
            "y0": w / 2.0, "z0": h / 2.0, "r": min(w, h) * 0.2,
            "h_patch": 500.0, "T_patch": 288.15,
        }]
    if key in ("corner patch", "corner"):
        return [{
            "category": "surface", "shape": "rect",
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
