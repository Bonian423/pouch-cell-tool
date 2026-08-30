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
