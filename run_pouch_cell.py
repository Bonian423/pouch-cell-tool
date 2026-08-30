"""Compatibility entry point.

Use ``python -m pouch_cell`` (the CLI now lives in ``pouch_cell.cli``), or
``python -m pouch_cell --ui`` to launch the Streamlit UI.
"""
from pouch_cell.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
