"""Plotting helpers for the 3D pouch cell tool."""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pybamm

from .cell_spec import PouchCellSpec

# --------------------------------------------------------------------------- #
# Stack schematic
# --------------------------------------------------------------------------- #
_LAYER_COLORS = {
    "cc_neg": "#b87333",  # copper
    "negative": "#7f7f7f",
    "separator": "#d9d9d9",
    "positive": "#4d4d4d",
    "cc_pos": "#c0c0c0",  # aluminium
}


def stack_diagram(spec: PouchCellSpec, ax=None, max_layers: int | None = None):
    """Draw a schematic cross-section of the 20-layer pouch stack.

    Each electrode pair is shown as negative electrode / separator / positive
    electrode; current collectors appear between pairs and on the outside.
    """
    n = spec.n_stacks
    if max_layers is None or max_layers >= n:
        max_layers = n

    unit = spec.L_n + spec.L_s + spec.L_p
    L_cn = spec.L_cn
    L_cp = spec.L_cp
    total = unit * n + (n + 1) * (L_cn + L_cp) / 2

    if ax is None:
        fig, ax = plt.subplots(figsize=(7, 5))
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.02 * total, 1.02 * total)
    ax.axis("off")

    y = 0.0
    # outer negative current collector
    y = _draw_layer(ax, y, L_cp / 2, "cc_pos", "Al")
    for i in range(max_layers):
        y = _draw_layer(ax, y, L_cn / 2 + L_cn / 2, "cc_neg", "Cu")
        y = _draw_layer(ax, y, spec.L_n, "negative", "neg.")
        y = _draw_layer(ax, y, spec.L_s, "separator", "sep.")
        y = _draw_layer(ax, y, spec.L_p, "positive", "pos.")
        y = _draw_layer(ax, y, L_cp / 2 + L_cp / 2, "cc_pos", "Al")
        if i + 1 < max_layers:
            ax.annotate(
                "", xy=(0.5, y), xytext=(0.5, y - unit),
                arrowprops=dict(arrowstyle="<->", color="0.4", lw=1),
            )

    if max_layers < n:
        ax.text(
            0.5, y + unit / 2, f"$\u22ee$\n({n - max_layers} more pairs)",
            ha="center", va="center", fontsize=9, color="0.3",
        )

    ax.text(
        0.5, -0.03 * total,
        f"{spec.n_stacks} electrode pairs in parallel  |  "
        f"nominal {spec.capacity_Ah:.0f} Ah  |  "
        f"{spec.height * 1e2:.0f} cm x {spec.width * 1e2:.0f} cm x "
        f"{spec.thickness_total * 1e3:.0f} mm",
        ha="center", fontsize=9,
    )
    return ax


def _draw_layer(ax, y, thickness, key, label):
    """Draw one horizontal layer and return the next y-position."""
    if thickness <= 0:
        return y
    ax.add_patch(
        plt.Rectangle((0.05, y), 0.9, thickness, facecolor=_LAYER_COLORS[key],
                      edgecolor="black", lw=0.5)
    )
    if label:
        ax.text(0.5, y + thickness / 2, label, ha="center", va="center",
                fontsize=6, color="white" if key != "separator" else "black")
    return y + thickness


# --------------------------------------------------------------------------- #
# Generic discharge plots
# --------------------------------------------------------------------------- #
def plot_discharge(
    sol: pybamm.Solution,
    spec: PouchCellSpec | None = None,
    variables=("Voltage [V]", "Volume-averaged cell temperature [K]"),
    time_unit: str = "hours",
    figsize=(9, 3.4),
):
    """Plot the given output variables of a solution vs. time.

    Spatially-resolved variables are averaged over space to give a time series.
    Returns the matplotlib ``Figure``.  Implemented directly on top of
    matplotlib for robustness across PyBaMM versions / backends.
    """
    factors = {"hours": 3600.0, "minutes": 60.0, "seconds": 1.0}
    if time_unit not in factors:
        raise ValueError(f"time_unit must be one of {list(factors)}")
    factor = factors[time_unit]

    t = np.asarray(sol["Time [s]"].entries)
    fig, axes = plt.subplots(1, len(variables), figsize=figsize)
    if len(variables) == 1:
        axes = [axes]

    for ax, name in zip(axes, variables):
        data = np.asarray(sol[name].entries, dtype=float)
        if data.ndim == 2:
            data = data.mean(axis=0)  # average over space -> time series
        ax.plot(t / factor, data, lw=1.5)
        ax.set_xlabel(f"Time [{time_unit}]")
        ax.set_ylabel(name)
        ax.grid(True, alpha=0.3)

    fig.tight_layout()
    return fig


def plot_current_and_potentials(sol: pybamm.Solution):
    """Quick overview of the current-collector behaviour."""
    variables = [
        "Current collector current density [A.m-2]",
        "Negative current collector potential [V]",
        "Positive current collector potential [V]",
        "Voltage [V]",
        "Volume-averaged cell temperature [K]",
    ]
    return sol.plot(variables, shading="auto")


# --------------------------------------------------------------------------- #
# 2D in-plane maps (2+1D models)
# --------------------------------------------------------------------------- #
def _yz_extents(sol: pybamm.Solution) -> tuple[float, float, float, float]:
    """Return (y_min, y_max, z_min, z_max) in metres for the current collector."""
    y = np.asarray(sol["y [m]"].entries)
    z = np.asarray(sol["z [m]"].entries)
    return float(y.min()), float(y.max()), float(z.min()), float(z.max())


def _mark_tabs(ax, spec, z_hi_cm):
    """Draw markers for the (2 cm x 2 cm) tabs on the top edge of the pouch."""
    from matplotlib.patches import Rectangle

    for label, yc in (("−", spec.neg_tab_y_centre), ("+", spec.pos_tab_y_centre)):
        y0 = (yc - spec.tab_width / 2.0) * 100.0
        ax.add_patch(
            Rectangle(
                (y0, z_hi_cm - 0.4),
                spec.tab_width * 100.0, 0.4,
                facecolor="red", edgecolor="black", alpha=0.55,
            )
        )
        ax.text(
            yc * 100.0, z_hi_cm + 1.2, label,
            ha="center", va="bottom", fontsize=13, fontweight="bold",
        )


def plot_2d_map(
    sol: pybamm.Solution,
    variable: str = "Current collector current density [A.m-2]",
    t: float | None = None,
    title: str | None = None,
    ax=None,
    cmap="viridis",
    show_tabs: bool = False,
    spec=None,
):
    """Heat-map of a 2D current-collector variable on the pouch face.

    Parameters
    ----------
    sol : pybamm.Solution
        Solution of a 2+1D model (dimensionality == 2).
    variable : str
        Any current-collector variable, e.g. ``"Current collector current
        density [A.m-2]"``, ``"Negative current collector potential [V]"``,
        ``"Negative current collector Ohmic heating [W.m-3]"`` or
        ``"X-averaged cell temperature [K]"``.
    t : float, optional
        Time (s) at which to plot.  Defaults to the final time.
    show_tabs : bool
        Mark the tab positions (requires ``spec``).
    spec : PouchCellSpec, optional
        Cell design, used to draw the tab markers.
    """
    times = np.asarray(sol["Time [s]"].entries)
    entries = np.asarray(sol[variable].entries, dtype=float)
    if t is None:
        tidx = entries.shape[-1] - 1
    else:
        tidx = int(np.argmin(np.abs(times - t)))
    data = entries[..., tidx]

    y_lo, y_hi, z_lo, z_hi = _yz_extents(sol)

    if data.ndim == 2:
        # 2D current collector: (n_y, n_z) -> transpose for imshow (rows = z)
        img = data.T
        if ax is None:
            fig, ax = plt.subplots(figsize=(6.5, 5))
        im = ax.imshow(
            img, origin="lower", aspect="equal", cmap=cmap,
            extent=[y_lo * 100, y_hi * 100, z_lo * 100, z_hi * 100],
            interpolation="nearest",
        )
        ax.set_xlabel("width, y [cm]")
        ax.set_ylabel("height, z [cm]")
        ax.set_title(title or f"{variable} at t = {times[tidx]:.0f} s")
        plt.colorbar(im, ax=ax, shrink=0.85)
        if show_tabs and spec is not None:
            _mark_tabs(ax, spec, z_hi * 100)
        return ax

    # 1D current collector (dimensionality 1): line along z
    z = np.linspace(z_lo, z_hi, data.size)
    if ax is None:
        fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(z * 100, data, lw=1.5)
    ax.set_xlabel("height, z [cm]")
    ax.set_ylabel(variable)
    ax.set_title(title or f"{variable} at t = {times[tidx]:.0f} s")
    ax.grid(True, alpha=0.3)
    return ax


def _scatter_map(sol, variable, t, title, ax, cmap):
    var = sol[variable]
    data = np.asarray(var(t)).flatten()
    y_lo, y_hi, z_lo, z_hi = _yz_extents(sol)
    n = data.size
    n_z = int(round(np.sqrt(n * (z_hi - z_lo) / max((y_hi - y_lo), 1e-9))))
    n_y = n // n_z if n_z else 1
    yy, zz = np.meshgrid(np.linspace(y_lo, y_hi, n_y), np.linspace(z_lo, z_hi, n_z))
    if ax is None:
        fig, ax = plt.subplots(figsize=(6.5, 5))
    sc = ax.scatter(yy.ravel() * 100, zz.ravel() * 100, c=data, cmap=cmap, s=8)
    ax.set_xlabel("width, y [cm]")
    ax.set_ylabel("height, z [cm]")
    ax.set_title(title or f"{variable} at t = {t:.0f} s")
    plt.colorbar(sc, ax=ax, shrink=0.85)
    return ax


def plot_current_density_map(
    sol: pybamm.Solution, t: float | None = None, ax=None
):
    """Heat-map of the current-collector current density on the pouch face."""
    return plot_2d_map(
        sol, "Current collector current density [A.m-2]", t=t, ax=ax,
        title="Current collector current density [A.m-2]", cmap="plasma",
    )


def plot_temperature_map(
    sol: pybamm.Solution, t: float | None = None, ax=None
):
    """Heat-map of the (x-lumped) cell temperature on the pouch face."""
    return plot_2d_map(
        sol, "X-averaged cell temperature [K]", t=t, ax=ax,
        title="X-averaged cell temperature [K]", cmap="inferno",
    )


def plot_tab_heating(
    sol: pybamm.Solution,
    spec: PouchCellSpec,
    param=None,
    t: float | None = None,
    figsize=(13, 10),
):
    """2x2 analysis of tab-driven current concentration and resistive heating.

    The two 2 cm x 2 cm tabs draw current from the surrounding current
    collector, so the in-plane current collector current density -- and its
    Ohmic (resistive) heating ``Q = i^2 / sigma`` -- peak in the vicinity of
    each tab.  This panel shows, at a single time:

    * the **in-plane current density** ``|i_cc| = sigma_cc * |grad phi_cc|``
      in the positive and negative current collectors (computed from the
      current-collector potentials -- this is the quantity that concentrates
      at the tabs),
    * the **total current-collector Ohmic (resistive) heating**
      ``Q_cc = i^2 / sigma`` (the heat generation source localised at the
      tabs),
    * the resulting **x-lumped temperature** field over the pouch face
      (magnitude is model-dependent for the fast SPM; the hot-spot *location*
      near the tabs is the key qualitative result).

    Tab positions are marked in red.  ``param`` is the ``ParameterValues``
    object used for the simulation (needed for the collector conductivities).

    Returns the matplotlib ``Figure``.
    """
    y_lo, y_hi, z_lo, z_hi = _yz_extents(sol)
    times = np.asarray(sol["Time [s]"].entries)
    tidx = entries_last_index(sol, t)

    def _panel(ax, data, cmap, title):
        img = np.asarray(data, dtype=float).T  # (n_z, n_y) for imshow
        im = ax.imshow(
            img, origin="lower", aspect="equal", cmap=cmap,
            extent=[y_lo * 100, y_hi * 100, z_lo * 100, z_hi * 100],
            interpolation="nearest",
        )
        ax.set_xlabel("width, y [cm]")
        ax.set_ylabel("height, z [cm]")
        ax.set_title(title, fontsize=10)
        plt.colorbar(im, ax=ax, shrink=0.8)
        _mark_tabs(ax, spec, z_hi * 100)

    fig, axes = plt.subplots(2, 2, figsize=figsize)

    # in-plane current density in each current collector (current concentration)
    i_pos = _cc_in_plane_current_density(sol, spec, param, "positive")
    i_neg = _cc_in_plane_current_density(sol, spec, param, "negative")
    _panel(
        axes[0, 0], i_pos, "plasma",
        "Positive CC in-plane current density |i| [A.m-2]\n"
        "(current concentrated at the positive tab)",
    )
    _panel(
        axes[0, 1], i_neg, "plasma",
        "Negative CC in-plane current density |i| [A.m-2]\n"
        "(current concentrated at the negative tab)",
    )

    # resistive (Ohmic) heating in the current collectors, Q = i^2 / sigma
    q_pos = _cc_ohmic_heating(sol, spec, param, "positive")
    q_neg = _cc_ohmic_heating(sol, spec, param, "negative")
    _panel(
        axes[1, 0], q_pos + q_neg, "hot",
        "Current-collector Ohmic (resistive) heating [W.m-3]\n"
        "(Q = i^2/sigma -- heat generation localised at the tabs)",
    )

    # resulting temperature distribution (qualitative magnitude)
    _panel(
        axes[1, 1],
        np.asarray(sol["X-averaged cell temperature [K]"].entries)[..., tidx],
        "inferno",
        "X-averaged cell temperature [K]\n"
        "(hot-spot location near tabs; magnitude model-dependent)",
    )

    fig.suptitle(
        f"Tab-driven current concentration and resistive heating "
        f"(t = {times[tidx]:.0f} s; tabs marked in red)",
        fontsize=13,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    return fig


def entries_last_index(sol: pybamm.Solution, t: float | None) -> int:
    """Time index into ``.entries[..., t]`` (last time if ``t`` is None)."""
    times = np.asarray(sol["Time [s]"].entries)
    if t is None:
        return times.size - 1
    return int(np.argmin(np.abs(times - t)))


def _cc_conductivity(param, polarity: str) -> float:
    """Current-collector conductivity (S/m) from the parameter values."""
    return float(param[f"{polarity.capitalize()} current collector conductivity [S.m-1]"])


def _cc_ohmic_heating(sol, spec, param, polarity: str):
    """Volumetric Ohmic heating in a current collector, Q = i^2 / sigma (W/m^3).

    ``i`` is the in-plane current density (A/m^2) in the collector; ``Q =
    i^2/sigma`` is the resistive power density.  This is what concentrates at
    the tabs.
    """
    i = _cc_in_plane_current_density(sol, spec, param, polarity)
    sigma = _cc_conductivity(param, polarity)
    return i**2 / sigma


def _cc_in_plane_current_density(sol, spec, param, polarity: str):
    """In-plane current density magnitude in a current collector (A/m^2).

    ``|i_cc| = sigma_cc * |grad phi_cc|``, evaluated from the current-collector
    potential field on the pouch face.  This is the quantity that concentrates
    near the tabs.
    """
    Domain = polarity.capitalize()
    entries = np.asarray(sol[f"{Domain} current collector potential [V]"].entries)
    tidx = entries.shape[-1] - 1
    phi = entries[..., tidx]  # (n_y, n_z)
    n_y, n_z = phi.shape
    dy = spec.width / max(n_y - 1, 1)
    dz = spec.height / max(n_z - 1, 1)
    dphi_y, dphi_z = np.gradient(phi, dy, dz)
    sigma = _cc_conductivity(param, polarity)
    return sigma * np.hypot(dphi_y, dphi_z)


# --------------------------------------------------------------------------- #
# True 3D plots (SPM_3D)
# --------------------------------------------------------------------------- #
def plot_3d_cross_section(
    sol: pybamm.Solution,
    variable: str = "Cell temperature [K]",
    plane: str = "yz",
    position: float = 0.5,
    t: float | None = None,
    **kwargs,
):
    """Slice plot through the 3D cell (via ``pybamm.plot_3d_cross_section``).

    Returns the matplotlib ``Figure``.
    """
    ax = pybamm.plot_3d_cross_section(
        sol, variable, t, plane=plane, position=position, **kwargs
    )
    return ax.figure


def plot_3d_heatmap(
    sol: pybamm.Solution,
    variable: str = "Cell temperature [K]",
    t: float | None = None,
    **kwargs,
):
    """3D volume heat-map (via ``pybamm.plot_3d_heatmap``).

    Returns the matplotlib ``Figure``.
    """
    ax = pybamm.plot_3d_heatmap(sol, t=t, variable=variable, **kwargs)
    return ax.figure
