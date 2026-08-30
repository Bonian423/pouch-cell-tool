"""Validate the pouch_cell tool end-to-end (working model paths)."""
import time

import pybamm

from pouch_cell import PouchCellSpec, PouchCellSimulation, build_parameter_values

pybamm.set_logging_level("ERROR")


def tic():
    return time.time()


def toc(t0, msg):
    print(f"[{time.time()-t0:7.1f}s] {msg}", flush=True)


if __name__ == "__main__":
    print("=" * 72)
    print("1) Cell design report")
    print("=" * 72)
    spec = PouchCellSpec()
    param = build_parameter_values(spec)
    print(spec.report(param))

    print()
    print("=" * 72)
    print("2) 1D SPMe full 1C discharge (validates capacity + initial state)")
    print("=" * 72)
    t0 = tic()
    sim1d = PouchCellSimulation(
        spec=spec, model_name="SPMe", dimensionality=0,
        thermal="lumped", mesh="draft", initial_soc=1.0,
    )
    sol1d = sim1d.discharge(C_rate=1.0)
    V = sol1d["Voltage [V]"].entries
    cap = sim1d.discharge_capacity_Ah()
    toc(t0, f"1D discharge done: {V[0]:.3f} -> {V[-1]:.3f} V, "
            f"{cap:.3f} Ah, {sol1d['Time [s]'].entries[-1] / 60:.1f} min")
    assert 8.0 < cap < 10.0, f"capacity {cap} outside 9 +/- 1 Ah"
    assert V[-1] < 3.0, "did not discharge to cutoff"

    print()
    print("=" * 72)
    print("3) True-3D SPM_3D (3D FEM thermal over the stack) - short discharge")
    print("=" * 72)
    t0 = tic()
    sim3 = PouchCellSimulation(
        spec=spec, model_name="SPM_3D", mesh="draft", initial_soc=1.0,
    )
    sol3 = sim3.discharge(C_rate=1.0, duration_s=60)
    toc(t0, "SPM_3D solve (60 s at 1C) complete")
    T = sol3["Cell temperature [K]"]
    V3 = sol3["Voltage [V]"].entries
    print(f"  voltage: {V3[0]:.3f} -> {V3[-1]:.3f} V")
    print(f"  3D temperature field shape: {T.entries.shape} "
          f"(nodes x times)")
    print(f"  temperature range: {T.entries.min():.2f} .. "
          f"{T.entries.max():.2f} K")

    print()
    print("=" * 72)
    print("4) Model / option sanity checks")
    print("=" * 72)
    from pouch_cell import build_model
    for name in ["SPM", "SPMe", "DFN", "SPM_3D"]:
        m = build_model(name, dimensionality=2 if name != "SPM_3D" else 2,
                        thermal="x-lumped")
        print(f"  {name}: ok ({type(m).__name__})")

    print()
    print("ALL VALIDATION DONE")
