"""Normalise the ``cooling=`` option into parameter overrides."""
from __future__ import annotations

from ..registry import COOLING_PRESETS, FACE_ALIASES


def resolve_cooling(cooling) -> tuple:
    """Normalise ``cooling`` into ``(h, T_amb, extra_params)``.

    ``cooling`` may be:

    * a **str preset** -- sets the uniform surface heat-transfer coefficient
      (``natural``, ``forced_air``/``fan``, ``liquid_cold_plate``/``cold_plate``);
    * a **dict** -- ``heat_transfer_coefficient_W_m2K`` and/or
      ``ambient_temperature_K`` convenience keys, plus any other PyBaMM
      parameter overrides (per-face ``<face> face heat transfer coefficient
      [W.m-2.K-1]``, the short face aliases ``left/right/front/back/bottom/top``,
      or time/space-dependent callables, e.g. ``{"Ambient temperature [K]":
      lambda t: 288.15 if t < 600 else 298.15}``).
    """
    if cooling is None:
        return None, None, {}
    if isinstance(cooling, str):
        key = cooling.lower()
        if key not in COOLING_PRESETS:
            raise ValueError(
                f"Unknown cooling preset '{cooling}'. "
                f"Choose from {sorted(COOLING_PRESETS)} or pass a dict of "
                "parameter overrides."
            )
        return COOLING_PRESETS[key], None, {}
    if isinstance(cooling, dict):
        cooling = dict(cooling)
        h = cooling.pop("heat_transfer_coefficient_W_m2K", None)
        t_amb = cooling.pop("ambient_temperature_K", None)
        extra = {
            FACE_ALIASES.get(str(k).lower(), k): v for k, v in cooling.items()
        }
        return h, t_amb, extra
    raise TypeError(
        "cooling must be a str preset, a dict of parameter overrides, or None."
    )


# Backwards-compatible private aliases (older code referenced the underscore
# names; kept so the legacy shims and notebook cells keep working).
_COOLING_PRESETS = COOLING_PRESETS
_FACE_ALIASES = FACE_ALIASES
_resolve_cooling = resolve_cooling
