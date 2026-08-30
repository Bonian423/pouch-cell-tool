"""``ThermalConfig`` -- thermal / cooling knobs used by the Streamlit UI.

Assembled into the ``cooling=`` argument accepted by
:class:`~pouch_cell.core.simulation.PouchCellSimulation`:

* a preset name (``natural`` / ``forced_air`` / ``cold_plate`` ...) or
* a dict of PyBaMM parameter overrides (per-face h, time-dependent ambient...).

The heat-pipe fields live on :class:`~pouch_cell.config.design.PouchCellSpec`
(single source of truth), so this config only carries the cooling preset and
the raw override escape hatch.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import registry


@dataclass
class ThermalConfig:
    """UI-facing thermal knobs."""

    cooling: str | dict | None = None      # preset name or dict overrides
    ambient_temperature_K: float | None = None   # None -> spec default
    heat_transfer_coefficient_W_m2K: float | None = None  # None -> preset/natural
    per_face_h: dict = field(default_factory=dict)       # SPM_3D face -> h
    extra_overrides: dict = field(default_factory=dict)  # raw PyBaMM params

    def to_cooling(self) -> str | dict | None:
        """Return the ``cooling=`` argument for ``PouchCellSimulation``.

        If only a preset is set it is passed through by name; anything else is
        assembled into a parameter-override dict (the raw override escape hatch
        wins on key collisions).
        """
        if (
            self.cooling is None
            and self.ambient_temperature_K is None
            and self.heat_transfer_coefficient_W_m2K is None
            and not self.per_face_h
            and not self.extra_overrides
        ):
            return None
        if (
            isinstance(self.cooling, str)
            and self.ambient_temperature_K is None
            and self.heat_transfer_coefficient_W_m2K is None
            and not self.per_face_h
            and not self.extra_overrides
        ):
            return self.cooling

        out: dict = {}
        if isinstance(self.cooling, dict):
            out.update(self.cooling)
        elif self.cooling:
            # start from the preset's h so the dict form inherits it
            h = registry.get("cooling", self.cooling)
            if h is not None:
                out["heat_transfer_coefficient_W_m2K"] = h
        if self.heat_transfer_coefficient_W_m2K is not None:
            out["heat_transfer_coefficient_W_m2K"] = self.heat_transfer_coefficient_W_m2K
        if self.ambient_temperature_K is not None:
            out["ambient_temperature_K"] = self.ambient_temperature_K
        for k, v in self.per_face_h.items():
            out[registry.FACE_ALIASES.get(str(k).lower(), k)] = v
        out.update(self.extra_overrides)
        return out
