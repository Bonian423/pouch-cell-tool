"""Preset persistence -- save / load named ``RunConfig`` presets as JSON.

Presets live in the ``presets/`` directory at the project root (or the
directory given to :func:`set_preset_dir`).  Each file stores the full
``RunConfig.as_dict()`` so a design + its run settings can be recalled later.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .run import RunConfig

# Project root = parent of the package directory (repo layout keeps the
# package at the root, not under src/).
_PKG_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = _PKG_DIR.parent
DEFAULT_PRESET_DIR = PROJECT_ROOT / "presets"


def set_preset_dir(path) -> None:
    global DEFAULT_PRESET_DIR
    DEFAULT_PRESET_DIR = Path(path)


def preset_path(name: str) -> Path:
    """Path for a named preset (name may or may not include ``.json``)."""
    if not name.lower().endswith(".json"):
        name += ".json"
    return DEFAULT_PRESET_DIR / name


def list_presets() -> list[str]:
    """Names (without extension) of the presets on disk."""
    if not DEFAULT_PRESET_DIR.is_dir():
        return []
    return sorted(p.stem for p in DEFAULT_PRESET_DIR.glob("*.json"))


def save_preset(name: str, config: RunConfig) -> Path:
    """Write a named preset and return its path."""
    DEFAULT_PRESET_DIR.mkdir(parents=True, exist_ok=True)
    path = preset_path(name)
    path.write_text(json.dumps(config.as_dict(), indent=2, default=str), encoding="utf-8")
    return path


def load_preset(name: str) -> RunConfig:
    """Load a named preset as a :class:`RunConfig`."""
    path = preset_path(name)
    if not path.is_file():
        raise FileNotFoundError(f"No preset '{name}' at {path}")
    return RunConfig(**json.loads(path.read_text(encoding="utf-8")))


def delete_preset(name: str) -> None:
    path = preset_path(name)
    if path.is_file():
        os.remove(path)


# --------------------------------------------------------------------------- #
# User-defined parameter sets (overrides on top of a PyBaMM base set)
# --------------------------------------------------------------------------- #
USER_PARAM_DIR = PROJECT_ROOT / "pouch_output" / "parameter_sets"


def user_param_path(name: str) -> Path:
    """Path for a named custom parameter set (name may omit ``.json``)."""
    if not name.lower().endswith(".json"):
        name += ".json"
    return USER_PARAM_DIR / name


def list_user_parameter_sets() -> list[str]:
    """Names (without extension) of the saved custom parameter sets."""
    if not USER_PARAM_DIR.is_dir():
        return []
    return sorted(p.stem for p in USER_PARAM_DIR.glob("*.json"))


def save_user_parameter_set(
    name: str, base_set: str, overrides: dict, description: str | None = None
) -> Path:
    """Write a custom parameter set ``{base, overrides}`` and return its path.

    ``description`` is an optional user note shown in the parameter-set
    browser on the Model page.
    """
    USER_PARAM_DIR.mkdir(parents=True, exist_ok=True)
    path = user_param_path(name)
    data: dict = {"base": base_set, "overrides": overrides or {}}
    if description and str(description).strip():
        data["description"] = str(description).strip()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def load_user_parameter_set(name: str) -> dict:
    """Load a custom parameter set as ``{"base": ..., "overrides": {...}}``."""
    path = user_param_path(name)
    if not path.is_file():
        raise FileNotFoundError(f"No custom parameter set '{name}' at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def delete_user_parameter_set(name: str) -> None:
    """Delete a saved custom parameter set."""
    path = user_param_path(name)
    if path.is_file():
        os.remove(path)


def is_user_parameter_set(name: str) -> bool:
    """True if ``name`` matches a saved custom parameter set."""
    return name in list_user_parameter_sets()


def resolve_parameter_set(name: str) -> tuple[str, dict]:
    """Return ``(base PyBaMM set name, extra overrides)`` for a set name.

    Built-in sets -> ``(name, {})``; a saved custom set -> its stored
    ``(base, overrides)`` (so nesting a custom set inside another is avoided).
    """
    if is_user_parameter_set(name):
        uset = load_user_parameter_set(name)
        return uset.get("base", name), dict(uset.get("overrides") or {})
    return name, {}


# --------------------------------------------------------------------------- #
# Saved protocols (full Protocol.as_dict(), steps + run conditions)
# --------------------------------------------------------------------------- #
PROTOCOL_DIR = PROJECT_ROOT / "pouch_output" / "protocols"


def protocol_path(name: str) -> Path:
    """Path for a named saved protocol (name may omit ``.json``)."""
    if not name.lower().endswith(".json"):
        name += ".json"
    return PROTOCOL_DIR / name


def list_saved_protocols() -> list[str]:
    """Names (without extension) of the saved protocols on disk."""
    if not PROTOCOL_DIR.is_dir():
        return []
    return sorted(p.stem for p in PROTOCOL_DIR.glob("*.json"))


def save_protocol(name: str, proto) -> Path:
    """Write a protocol's ``as_dict()`` and return its path."""
    PROTOCOL_DIR.mkdir(parents=True, exist_ok=True)
    path = protocol_path(name)
    path.write_text(
        json.dumps(proto.as_dict(), indent=2, default=str), encoding="utf-8"
    )
    return path


def load_protocol(name: str) -> dict:
    """Load a saved protocol as a raw ``as_dict()`` dict."""
    path = protocol_path(name)
    if not path.is_file():
        raise FileNotFoundError(f"No saved protocol '{name}' at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def delete_protocol(name: str) -> None:
    """Delete a saved protocol."""
    path = protocol_path(name)
    if path.is_file():
        os.remove(path)
