"""Turn raw PyBaMM solver exceptions into actionable one-line messages.

The worker (and the thermal preview) surface run failures in the UI.  Raw
``pybamm.SolverError`` text is cryptic, so known failure classes are mapped to
a short explanation + what to change.  Unknown errors pass through unchanged
(the full traceback is still recorded by the caller).
"""


def friendly_solver_error(err: BaseException) -> str:
    """An actionable one-liner for ``err`` (passes unknown messages through)."""
    msg = repr(err)
    if "Maximum voltage" in msg and "initial conditions" in msg:
        return (
            "The cell's initial voltage is already at/above the upper cut-off "
            "(or an OCP override pushes it there) — e.g. charging from a high "
            "SOC / high initial voltage. Lower the Initial SOC or initial "
            "voltage, reduce the charge C-rate, or reset the parameter "
            "overrides."
        )
    if (("infeasible" in msg and "exceeded bounds at initial conditions" in msg)
            or "skip_ok is True" in msg):
        return (
            "The protocol's steps are infeasible from the initial state — the "
            "start voltage/SOC is inconsistent with the step directions and "
            "cut-offs (e.g. charging from a nearly-full or degenerate state, "
            "or an override pushing the OCP out of range). Lower the C-rate, "
            "adjust the Initial SOC / initial voltage, or reset the parameter "
            "overrides (Design / Thermal raw overrides)."
        )
    if ("non-positive at initial conditions" in msg
            or "Minimum voltage" in msg
            or "IDA_CONV_FAIL" in msg
            or "CONV_FAIL" in msg):
        return (
            "The cell's initial state is degenerate: the initial voltage is at "
            "or below the discharge cut-off, so the solver can't start. Reset "
            "parameter overrides and raise the Initial SOC / initial voltage."
        )
    if "Parameter" in msg and "not found" in msg:
        return (
            "This parameter set isn't a full lithium-ion cell set (half-cell / "
            "composite / MSMR / ECM / Na-ion). Pick a full-cell set on Model & "
            "Run."
        )
    if "initial condition is outside of variable bounds" in msg:
        return (
            "The initial cell state is outside physical bounds — check the "
            "Initial SOC / voltage and any parameter overrides."
        )
    return msg
