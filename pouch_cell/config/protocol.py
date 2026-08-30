"""Protocol definitions for multi-step (cycling) simulations.

A protocol is an ordered list of steps -- discharge / charge / rest / hold --
optionally repeated for ``N`` cycles, with an output ``period``, an overall
``termination`` condition and an optional experiment ``temperature``.  It
serialises to the PyBaMM ``Experiment`` step strings from the PyBaMM docs::

    "Discharge at 1C for 10 minutes"
    "Charge at 0.5 C until 4.2 V"
    "Rest for 5 minutes"
    "Hold at 4.2 V until 0.45 A"

Each step can be expressed as a C-rate, an absolute current (A) or a power (W);
terminations as a duration ("for ...") or a cut-off ("until ... V / A").
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


def fmt_duration(seconds: float | None) -> str:
    """Human-friendly duration string for a PyBaMM step (e.g. '10 minutes')."""
    if seconds is None or seconds <= 0:
        return "1 second"
    if seconds >= 3600 and seconds % 3600 == 0:
        return f"{int(seconds // 3600)} hours"
    if seconds >= 60 and seconds % 60 == 0:
        return f"{int(seconds // 60)} minutes"
    return f"{seconds:g} seconds"


@dataclass
class Step:
    """One protocol step.

    ``kind`` is ``discharge``, ``charge``, ``rest`` or ``hold``.  Discharge /
    charge use ``c_rate`` (or ``current_A`` / ``power_W``) with either a
    ``duration_s`` or a ``cutoff_V``.  Hold uses ``hold_voltage_V`` and either
    a ``cutoff_current_C`` (as a C-rate -> amperes) or a ``duration_s``.
    """

    kind: str = "discharge"
    c_rate: float | None = 1.0
    current_A: float | None = None
    power_W: float | None = None
    duration_s: float | None = None
    cutoff_V: float | None = None
    hold_voltage_V: float | None = None
    cutoff_current_C: float | None = None

    def to_string(self, capacity_Ah: float) -> str:
        if self.kind == "rest":
            return f"Rest for {fmt_duration(self.duration_s)}"
        if self.kind == "hold":
            v = self.hold_voltage_V or 4.2
            if self.cutoff_current_C:
                amps = self.cutoff_current_C * capacity_Ah
                return f"Hold at {v:g} V until {amps:g} A"
            return f"Hold at {v:g} V for {fmt_duration(self.duration_s)}"
        action = "Discharge" if self.kind == "discharge" else "Charge"
        if self.current_A is not None:
            what = f"{self.current_A:g} A"
        elif self.power_W is not None:
            what = f"{self.power_W:g} W"
        elif self.c_rate is not None:
            what = f"{self.c_rate:g} C"
        else:
            what = "1 C"
        if self.cutoff_V is not None:
            return f"{action} at {what} until {self.cutoff_V:g} V"
        return f"{action} at {what} for {fmt_duration(self.duration_s)}"


@dataclass
class Protocol:
    """A runnable protocol: steps + cycles + experiment options."""

    type: str = "discharge"          # discharge | charge | custom
    steps: list = field(default_factory=list)  # list[Step]
    cycles: int = 1
    period: str | None = None
    termination: list = field(default_factory=list)  # e.g. ["80% capacity"]
    temperature_K: float | None = None
    thermal_maps: bool = True        # save a thermal map at the end of each step
    step_map_mode: str = "every"     # every | cycle_last

    # -- factories for the quick presets ---------------------------------- #
    @classmethod
    def discharge_protocol(
        cls,
        c_rate: float = 1.0,
        duration_s: float | None = 60.0,
        cutoff_V: float | None = None,
        thermal_maps: bool = True,
    ) -> "Protocol":
        return cls(
            type="discharge",
            steps=[Step(kind="discharge", c_rate=c_rate, duration_s=duration_s,
                        cutoff_V=cutoff_V)],
            thermal_maps=thermal_maps,
        )

    @classmethod
    def charge_protocol(
        cls,
        c_rate: float = 0.5,
        upper_cutoff_V: float = 4.2,
        cv_hold: bool = True,
        cv_cutoff_C: float = 0.05,
        rest_s: float | None = None,
        thermal_maps: bool = True,
    ) -> "Protocol":
        steps = [Step(kind="charge", c_rate=c_rate, cutoff_V=upper_cutoff_V)]
        if cv_hold:
            steps.append(Step(kind="hold", hold_voltage_V=upper_cutoff_V,
                              cutoff_current_C=cv_cutoff_C))
        if rest_s:
            steps.append(Step(kind="rest", duration_s=rest_s))
        return cls(type="charge", steps=steps, thermal_maps=thermal_maps)

    # -- serialisation ----------------------------------------------------- #
    def step_strings(self, capacity_Ah: float) -> list[str]:
        return [s.to_string(capacity_Ah) for s in self.steps]

    def experiment_cycles(self, capacity_Ah: float) -> list[tuple]:
        """The ``operating_conditions`` argument for ``pybamm.Experiment``."""
        steps = self.step_strings(capacity_Ah)
        if not steps:
            return []
        return [tuple(steps)] * max(1, int(self.cycles))

    def as_dict(self) -> dict:
        d = asdict(self)
        d["steps"] = [asdict(s) for s in self.steps]
        return d

    @classmethod
    def from_dict(cls, data: dict | None) -> "Protocol":
        if not data:
            return cls()
        data = dict(data)
        steps = [Step(**s) for s in data.pop("steps", [])]
        return cls(steps=steps, **data)
