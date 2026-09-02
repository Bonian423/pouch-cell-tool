"""Time-series persistence for the interactive Results plot browser.

The worker writes two CSVs at run time (the pybamm ``Solution`` is not kept
afterwards, so the browser and the data export both read from disk):

* ``series.csv`` -- the key cell-level time series (raw variables + derived
  energy / power / capacity-throughput / SOC / specific-capacity series).
  This is the file the plot browser reads AND the "key series" download.
* ``variables.csv`` -- every solution output variable, spatial-meaned to a
  1D time series (the "full variables" download).

Derived series follow the same conventions as
:func:`pouch_cell.core.experiment._electrical_metrics` (PyBaMM's ``Current
[A]`` is positive on discharge, so ``P = V * I`` is positive while
discharging).  All integrals are trapezoidal and cumulative over time.
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np


def _to_timeseries(arr) -> np.ndarray:
    """Flatten a solution-variable array to a 1D time series (spatial mean)."""
    a = np.asarray(arr, dtype=float)
    while a.ndim > 1:
        a = a.mean(axis=0)
    return a


def _series(sol, name: str, length: int):
    """Return a 1D series for ``name`` matching ``length`` or None."""
    try:
        a = _to_timeseries(sol[name].entries)
    except Exception:  # noqa: BLE001 - one bad variable must not kill the export
        return None
    if a.size != length:
        return None
    return a


def write_series_csv(outdir: Path, sol, sim, spec, config) -> list[str]:
    """Write ``series.csv`` (key cell-level time series + derived series).

    Returns the column names written (empty list on failure).
    """
    try:
        t = _to_timeseries(sol["Time [s]"].entries)
    except (KeyError, TypeError, ValueError):
        return []
    n = len(t)
    if n < 2:
        return []

    V = _series(sol, "Voltage [V]", n)
    I = _series(sol, "Current [A]", n)
    T = None
    for name in ("Volume-averaged cell temperature [K]",
                 "X-averaged cell temperature [K]", "Cell temperature [K]"):
        T = _series(sol, name, n)
        if T is not None:
            break

    energy = charge_energy = thru_energy = None
    q_disch = q_chg = q_thru = q_net = None
    power = None
    soc = specific = None

    if V is not None and I is not None:
        dt = np.maximum(np.diff(t), 0.0)
        P = V * I
        P_mid = 0.5 * (P[:-1] + P[1:])
        I_mid = 0.5 * (I[:-1] + I[1:])

        def _cum(x):
            out = np.empty(n)
            out[0] = 0.0
            out[1:] = np.cumsum(x * dt)
            return out

        energy = _cum(np.maximum(P_mid, 0.0)) / 3600.0      # Wh delivered
        charge_energy = _cum(np.maximum(-P_mid, 0.0)) / 3600.0
        thru_energy = _cum(np.abs(P_mid)) / 3600.0
        q_disch = _cum(np.maximum(I_mid, 0.0)) / 3600.0     # Ah
        q_chg = _cum(np.maximum(-I_mid, 0.0)) / 3600.0
        q_thru = _cum(np.abs(I_mid)) / 3600.0
        q_net = _cum(I_mid) / 3600.0
        power = P

        nominal = float(getattr(spec, "capacity_Ah", 0.0) or 0.0)
        init_soc = float(getattr(config, "initial_soc", 0.0) or 0.0)
        if nominal > 0:
            soc = init_soc - q_net / nominal
        try:
            from ..core.experiment import _estimate_cell_mass_kg
            mass_kg = _estimate_cell_mass_kg(sim, spec)
        except Exception:  # noqa: BLE001 - mass estimate is best-effort
            mass_kg = None
        if mass_kg:
            specific = q_disch / mass_kg

    cols = ["time_s", "voltage_V", "current_A",
            "discharge_capacity_Ah", "charge_capacity_Ah",
            "throughput_capacity_Ah", "energy_Wh", "charge_energy_Wh",
            "throughput_energy_Wh", "power_W", "temperature_K",
            "soc", "specific_capacity_Ah_per_kg"]
    values = [t, V, I, q_disch, q_chg, q_thru, energy, charge_energy,
              thru_energy, power, T, soc, specific]

    # 2+1D models run at the per-stack current, so scale the extensive
    # (A / Ah / Wh / W) columns back up to the full parallel-stack cell.
    from ..core.experiment import _parallel_scale
    _s = _parallel_scale(spec, int(getattr(sim, "dimensionality", 0)))
    if _s > 1:
        for _idx in (2, 3, 4, 5, 6, 7, 8, 9):
            if values[_idx] is not None:
                values[_idx] = values[_idx] * _s

    with open(outdir / "series.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for i in range(n):
            w.writerow(["" if v is None else v[i] for v in values])
    return cols


# Curated comprehensive set of the meaningful cell-level / spatially-averaged
# performance variables for the "full variables" export.  JIT-processing every
# model output costs ~1 s per variable (a full dump is ~500 columns and ~3 min
# of post-processing), so we bound the export to the standard battery
# performance quantities; names that a given model doesn't define are skipped.
_CURATED_VARIABLES = [
    "Voltage [V]",
    "Terminal voltage [V]",
    "Current [A]",
    "Discharge capacity [A.h]",
    "Throughput capacity [A.h]",
    "Power [W]",
    "Terminal power [W]",
    "Volume-averaged cell temperature [K]",
    "X-averaged cell temperature [K]",
    "Cell temperature [K]",
    "X-averaged negative electrode potential [V]",
    "X-averaged positive electrode potential [V]",
    "Negative electrode open circuit potential [V]",
    "Positive electrode open circuit potential [V]",
    "Negative electrode surface potential [V]",
    "Positive electrode surface potential [V]",
    "X-averaged negative particle surface concentration [mol.m-3]",
    "X-averaged positive particle surface concentration [mol.m-3]",
    "X-averaged negative electrolyte concentration [mol.m-3]",
    "X-averaged positive electrolyte concentration [mol.m-3]",
    "X-averaged separator electrolyte concentration [mol.m-3]",
    "Negative electrode stoichiometry",
    "Positive electrode stoichiometry",
    "X-averaged total heating [W.m-3]",
    "Ohmic heating [W.m-3]",
    "Irreversible electrochemical heating [W.m-3]",
    "Reversible heating [W.m-3]",
    "Negative current collector potential [V]",
    "Positive current collector potential [V]",
    "Current collector current density [A.m-2]",
]


def write_variables_csv(outdir: Path, sol) -> list[str]:
    """Write ``variables.csv`` with a curated set of output variables.

    Each variable is spatial-meaned to a 1D time series.  Returns the column
    names written (empty list on failure).  Variables that can't be reduced to
    the solution's time vector are skipped.
    """
    try:
        t = _to_timeseries(sol["Time [s]"].entries)
    except (KeyError, TypeError, ValueError):
        return []
    n = len(t)
    if n < 2:
        return []

    data: dict = {"time_s": t}
    # free ones that were already processed during the run
    try:
        _src = getattr(sol, "data", None)
        if _src:
            for name in list(_src.keys()):
                if name in data:
                    continue
                a = _to_timeseries(_src[name])
                if a.size == n:
                    data[name] = a
    except Exception:  # noqa: BLE001
        pass
    # curated additions (just-in-time processing, guarded per variable)
    for name in _CURATED_VARIABLES:
        if name in data:
            continue
        a = _series(sol, name, n)
        if a is None:
            continue
        data[name] = a

    cols = list(data)
    with open(outdir / "variables.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for i in range(n):
            w.writerow(["" if v is None else v[i] for v in data.values()])
    return cols
