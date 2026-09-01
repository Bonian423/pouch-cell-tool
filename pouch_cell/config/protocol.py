"""Protocol definitions for multi-step (cycling) simulations.

A protocol is an ordered list of steps -- discharge / charge / rest / hold --
optionally repeated for ``N`` cycles, with an output ``period``, an overall
``termination`` condition and an optional experiment ``temperature``.

Each step ends when **any** of its end conditions fires (Neware-style OR
semantics): time (duration), voltage, current, temperature or capacity.  Steps
can also act as **loop points** (jump back to an earlier step, repeated N
times, optionally until a condition) and the protocol supports a run-level
``temperature_stop`` safety limit.

The protocol serialises to PyBaMM ``Experiment`` step objects
(:meth:`Step.to_pybamm_step`), so non-native conditions (temperature /
capacity) ride PyBaMM's ``CustomTermination`` events.
"""
from __future__ import annotations

import copy
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
    charge use ``c_rate`` (or ``current_A`` / ``power_W``); ``hold`` uses
    ``hold_voltage_V``.  Every step ends when **any** of its ``terminations``
    fires (time / voltage / current / temperature / capacity) -- the first to
    trigger wins (Neware-style OR semantics).

    A step may also act as a **loop point**: ``loop_to`` (the index of an
    earlier step to jump back to), ``loop_count`` (how many times the
    ``loop_to..i`` block runs) and an optional ``loop_until`` condition list
    that exits the loop early (evaluated post-hoc -- PyBaMM cannot branch
    mid-solve).
    """

    kind: str = "discharge"
    c_rate: float | None = 1.0
    current_A: float | None = None
    power_W: float | None = None
    hold_voltage_V: float | None = None

    # -- end conditions (OR-ed; first to fire ends the step) --------------- #
    # each: {"type": "time"|"voltage"|"current"|"temperature"|"capacity",
    #        "operator": "<="|">=", "value": float, "unit": None|...}
    terminations: list = field(default_factory=list)

    # -- loop point -------------------------------------------------------- #
    loop_to: int | None = None       # index of the step to jump back to
    loop_count: int = 1              # total times the loop block runs
    loop_until: list = field(default_factory=list)  # OR-ed exit conditions

    # ------------------------------------------------------------------ #
    @property
    def duration_s(self) -> float | None:
        """The time-condition value (s), if any -- a convenience for the
        preview planner / callers (legacy field name)."""
        for c in self.terminations or []:
            if (c or {}).get("type") == "time":
                return float((c or {}).get("value", 0.0))
        return None

    # -- display ---------------------------------------------------------- #
    def _action_str(self) -> str:
        if self.kind == "rest":
            return "Rest"
        if self.kind == "hold":
            return f"Hold at {self.hold_voltage_V or 4.2:g} V"
        action = "Discharge" if self.kind == "discharge" else "Charge"
        if self.current_A is not None:
            return f"{action} at {self.current_A:g} A"
        if self.power_W is not None:
            return f"{action} at {self.power_W:g} W"
        return f"{action} at {self.c_rate or 1.0:g} C"

    def _condition_text(self, c: dict, capacity_Ah: float) -> str:
        typ = (c or {}).get("type", "time")
        op = (c or {}).get("operator", ">=")
        val = float((c or {}).get("value", 0.0))
        unit = (c or {}).get("unit")
        op_txt = "≤" if op == "<=" else "≥"
        if typ == "time":
            return f"t={fmt_duration(val)}"
        if typ == "voltage":
            return f"V {op_txt} {val:g} V"
        if typ == "current":
            if unit == "C":
                return f"I {op_txt} {val:g} C"
            return f"I {op_txt} {val:g} A"
        if typ == "temperature":
            # value is already stored in the chosen unit (C or K)
            u = "°C" if unit == "C" else "K"
            return f"T {op_txt} {val:g} {u}"
        if typ == "capacity":
            if unit == "%":
                return f"cap {op_txt} {val:g}%"
            return f"cap {op_txt} {val:g} Ah"
        return ""

    def to_string(self, capacity_Ah: float) -> str:
        """Human-readable (honest) step description, incl. temperature /
        capacity conditions."""
        parts = [self._action_str()]
        conds = [self._condition_text(c, capacity_Ah)
                 for c in self.terminations or []]
        conds = [c for c in conds if c]
        # a time condition reads as "for ..." (the step's max duration)
        for i, c in enumerate(conds):
            if c.startswith("t="):
                parts.append("for " + c[2:])
                del conds[i]
                break
        if conds:
            parts.append("until " + " or ".join(conds))
        return " ".join(parts)

    def preview_string(self, capacity_Ah: float) -> str:
        """A single-step PyBaMM-parseable string for the live preview.

        Only expressible conditions (time / voltage / current) are rendered;
        temperature / capacity conditions fall back to a default duration so
        the preview never hangs (the real solve honours them via
        :meth:`to_pybamm_step`).
        """
        dur = self.duration_s
        if self.kind == "rest":
            return f"Rest for {fmt_duration(dur or 60.0)}"
        if self.kind == "hold":
            v = self.hold_voltage_V or 4.2
            for c in self.terminations or []:
                if (c or {}).get("type") == "current":
                    val = float((c or {}).get("value", 0.05))
                    if (c or {}).get("unit") == "C":
                        val = val * capacity_Ah
                    return f"Hold at {v:g} V until {val:g} A"
            return f"Hold at {v:g} V for {fmt_duration(dur or 60.0)}"
        action = "Discharge" if self.kind == "discharge" else "Charge"
        if self.current_A is not None:
            what = f"{self.current_A:g} A"
        elif self.power_W is not None:
            what = f"{self.power_W:g} W"
        else:
            what = f"{self.c_rate or 1.0:g} C"
        if dur is not None:
            return f"{action} at {what} for {fmt_duration(dur)}"
        for c in self.terminations or []:
            typ = (c or {}).get("type")
            op = (c or {}).get("operator", ">=")
            val = float((c or {}).get("value", 0.0))
            if typ == "voltage":
                o = "<" if op == "<=" else ">"
                return f"{action} at {what} until {o}{val:g} V"
            if typ == "current":
                o = "<" if op == "<=" else ">"
                val_a = val if (c or {}).get("unit") != "C" else val * capacity_Ah
                return f"{action} at {what} until {o}{val_a:g} A"
        return f"{action} at {what} for {fmt_duration(60.0)}"

    # -- PyBaMM step ------------------------------------------------------- #
    def _pybamm_terminations(self, capacity_Ah: float, temp_source: str):
        """Return ``(duration, termination_objs)`` for a PyBaMM step."""
        import pybamm

        duration = None
        terms: list = []
        for c in self.terminations or []:
            typ = (c or {}).get("type", "time")
            op = (c or {}).get("operator", ">=")
            val = float((c or {}).get("value", 0.0))
            unit = (c or {}).get("unit")
            if typ == "time":
                duration = max(duration or 0.0, val)
            elif typ == "voltage":
                o = "<" if op == "<=" else ">"
                terms.append(f"{o}{val:g} V")
            elif typ == "current":
                val_a = val if unit != "C" else val * capacity_Ah
                if self.kind == "hold":
                    terms.append(f"{val_a:g} A")  # CV: |I| < val
                else:
                    o = "<" if op == "<=" else ">"
                    terms.append(f"{o}{val_a:g} A")
            elif typ == "temperature":
                kv = val + 273.15 if unit == "C" else val
                source = temp_source or "volume_averaged"

                def _T(vars_, src=source):
                    if src == "hot_spot":
                        return pybamm.max(
                            vars_["X-averaged cell temperature [K]"]
                        )
                    return vars_["Volume-averaged cell temperature [K]"]

                if op == ">=":
                    def _ev(vars_, kv=kv):
                        return kv - _T(vars_)
                else:
                    def _ev(vars_, kv=kv):
                        return _T(vars_) - kv
                terms.append(pybamm.step.CustomTermination("Temperature cut-off", _ev))
            elif typ == "capacity":
                x = val if unit != "%" else val / 100.0 * capacity_Ah
                if op == ">=":
                    def _ev(vars_, x=x):
                        return x - vars_["Discharge capacity [A.h]"]
                else:
                    def _ev(vars_, x=x):
                        return vars_["Discharge capacity [A.h]"] - x
                terms.append(pybamm.step.CustomTermination("Capacity cut-off", _ev))
        return duration, terms

    def to_pybamm_step(self, capacity_Ah: float, temp_source: str = "volume_averaged"):
        """Build a :class:`pybamm.step.BaseStep` for the real solve."""
        import pybamm

        duration, terms = self._pybamm_terminations(capacity_Ah, temp_source)
        if self.kind == "rest":
            return pybamm.step.rest(duration=duration, termination=terms or None)
        if self.kind == "hold":
            return pybamm.step.voltage(
                self.hold_voltage_V or 4.2,
                duration=duration, termination=terms or None,
            )
        sign = 1.0 if self.kind == "discharge" else -1.0  # +ve = discharge
        if self.current_A is not None:
            return pybamm.step.current(sign * self.current_A, duration=duration,
                                       termination=terms or None)
        if self.power_W is not None:
            return pybamm.step.power(sign * self.power_W, duration=duration,
                                     termination=terms or None)
        return pybamm.step.c_rate(sign * (self.c_rate or 1.0), duration=duration,
                                  termination=terms or None)

    # -- serialisation ----------------------------------------------------- #
    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "Step":
        if not data:
            return cls()
        data = dict(data)
        terminations = [dict(c) for c in (data.pop("terminations", None) or [])]
        # --- legacy migration: single end-condition fields -> terminations ---
        if not terminations:
            dur = data.pop("duration_s", None)
            cvo = data.pop("cutoff_V", None)
            cco = data.pop("cutoff_current_C", None)
            if dur is not None and float(dur) > 0:
                terminations.append(
                    {"type": "time", "operator": ">=", "value": float(dur)}
                )
            if cvo is not None:
                op = ">=" if data.get("kind") == "charge" else "<="
                terminations.append(
                    {"type": "voltage", "operator": op, "value": float(cvo)}
                )
            if cco is not None:
                # legacy CV end current was entered as a C-rate
                terminations.append(
                    {"type": "current", "operator": "<=",
                     "value": float(cco), "unit": "C"}
                )
        data["terminations"] = terminations
        data.setdefault("loop_to", None)
        data.setdefault("loop_count", 1)
        data.setdefault("loop_until", [])
        return cls(**data)


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
    # run-level temperature safety stop (K) -- evaluated post-hoc, since
    # PyBaMM has no experiment-level temperature termination
    temperature_stop: float | None = None
    # temperature source used by temperature conditions: "volume_averaged" |
    # "hot_spot" (max over the 2+1D y-z field; only valid on 2+1D x-lumped)
    temperature_source: str = "volume_averaged"

    # -- factories for the quick presets ---------------------------------- #
    @classmethod
    def discharge_protocol(
        cls,
        c_rate: float = 1.0,
        duration_s: float | None = 60.0,
        cutoff_V: float | None = None,
        thermal_maps: bool = True,
    ) -> "Protocol":
        terms: list = []
        if duration_s is not None:
            terms.append({"type": "time", "operator": ">=",
                          "value": float(duration_s)})
        if cutoff_V is not None:
            terms.append({"type": "voltage", "operator": "<=",
                          "value": float(cutoff_V)})
        return cls(
            type="discharge",
            steps=[Step(kind="discharge", c_rate=c_rate, terminations=terms)],
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
        steps = [
            Step(kind="charge", c_rate=c_rate,
                 terminations=[{"type": "voltage", "operator": ">=",
                                "value": float(upper_cutoff_V)}])
        ]
        if cv_hold:
            steps.append(Step(kind="hold", hold_voltage_V=upper_cutoff_V,
                              terminations=[{"type": "current", "operator": "<=",
                                             "value": float(cv_cutoff_C), "unit": "C"}]))
        if rest_s:
            steps.append(Step(kind="rest",
                              terminations=[{"type": "time", "operator": ">=",
                                             "value": float(rest_s)}]))
        return cls(type="charge", steps=steps, thermal_maps=thermal_maps)

    # -- loop expansion ---------------------------------------------------- #
    def expand(self) -> tuple[list, list]:
        """Unroll loops into a flat per-cycle step list.

        Returns ``(flat_steps, loop_infos)`` where ``loop_infos`` is a list of
        dicts ``{"loop_to", "count", "until", "iter_ends"}`` with
        ``iter_ends`` = flat indices of the last step of each loop iteration
        (used by the post-hoc loop-until evaluation in ``run_protocol``).
        """
        loop_infos: list[dict] = []
        flat = self._expand_range(0, len(self.steps), False, loop_infos)
        return flat, loop_infos

    def _expand_range(self, start: int, end: int, suppress_last: bool,
                      loop_infos: list) -> list:
        """Expand ``self.steps[start:end]``; ``suppress_last`` treats a loop
        marker at ``end-1`` as a plain step (it is a consumed marker)."""
        steps = self.steps
        out: list[Step] = []
        idx = start
        while idx < end:
            s = steps[idx]
            is_marker = s.loop_to is not None and 0 <= s.loop_to < idx
            is_last = idx == end - 1
            if is_marker and not (suppress_last and is_last):
                body = self._expand_range(s.loop_to, idx + 1, True, loop_infos)
                count = max(1, int(s.loop_count or 1))
                iter_ends: list[int] = []
                for _ in range(count):
                    out.extend(copy.deepcopy(x) for x in body)
                    iter_ends.append(len(out) - 1)
                loop_infos.append({
                    "loop_to": s.loop_to, "count": count,
                    "until": list(s.loop_until or []), "iter_ends": iter_ends,
                })
            else:
                cpy = copy.deepcopy(s)
                if is_marker and suppress_last and is_last:
                    cpy.loop_to = None
                    cpy.loop_count = 1
                    cpy.loop_until = []
                out.append(cpy)
            idx += 1
        return out

    def expanded_step_count(self) -> int:
        """Number of steps in one cycle after loop unrolling."""
        flat, _ = self.expand()
        return len(flat)

    # -- serialisation ----------------------------------------------------- #
    def step_strings(self, capacity_Ah: float) -> list[str]:
        return [s.to_string(capacity_Ah) for s in self.steps]

    def experiment_cycles(
        self, capacity_Ah: float, temp_source: str = "volume_averaged"
    ) -> list[tuple]:
        """The ``operating_conditions`` argument for ``pybamm.Experiment``
        (list of tuples of ``pybamm.step`` objects, loops unrolled)."""
        flat, _ = self.expand()
        if not flat:
            return []
        steps = [s.to_pybamm_step(capacity_Ah, temp_source) for s in flat]
        return [tuple(steps)] * max(1, int(self.cycles))

    def as_dict(self) -> dict:
        d = asdict(self)
        d["steps"] = [s.as_dict() for s in self.steps]
        return d

    @classmethod
    def from_dict(cls, data: dict | None) -> "Protocol":
        if not data:
            return cls()
        data = dict(data)
        steps = [Step.from_dict(s) for s in data.pop("steps", [])]
        return cls(steps=steps, **data)
