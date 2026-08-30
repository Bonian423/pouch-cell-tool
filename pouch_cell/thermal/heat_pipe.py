"""Localized heat-pipe cooling on the top edge (2+1D ``x-lumped`` solves).

A copper heat pipe runs ACROSS THE FULL WIDTH of the cell (along y), right
below the top edge (``z = height``) -- a horizontal band of height
``heat_pipe_height`` -- so it sits beside both tabs.  The folded tabs +
thermal paste + pipe are lumped into an effective coefficient ``heat_pipe_h``
rejecting to ``heat_pipe_temperature_K``.

Implemented with the standard 2+1D ``x-lumped`` machinery: the edge/surface
cooling references ``T_amb(y, z, t)`` and ``h_edge(y, z)``, so both are made
space-varying -- high (and chilled) only on the band.
"""
from __future__ import annotations

import pybamm


def heat_pipe_overrides(spec, h_base: float, T_base: float) -> dict:
    """Parameter overrides for localized heat-pipe cooling on the top edge."""
    pipe_h = spec.heat_pipe_h
    pipe_T = spec.heat_pipe_temperature_K
    height = spec.height
    pipe_height = spec.heat_pipe_height

    # Built with pybamm comparison operators (smooth Heaviside steps) rather
    # than numpy, because function-valued parameters are evaluated with
    # *symbolic* children during processing and must return pybamm symbols.
    # The current-collector domain is y in [0, width], so a band defined only
    # by its z (height) extent automatically spans the full cell width.
    def on_pipe(y, z):
        return z >= (height - pipe_height)

    def T_amb(y, z, t):
        p = on_pipe(y, z)
        return p * pipe_T + (1.0 - p) * T_base

    def h_edge(y, z):
        p = on_pipe(y, z)
        return p * pipe_h + (1.0 - p) * h_base

    return {
        "Ambient temperature [K]": T_amb,
        "Edge heat transfer coefficient [W.m-2.K-1]": h_edge,
    }


# Backwards-compatible private alias (the old simulation.py name).
_heat_pipe_overrides = heat_pipe_overrides
