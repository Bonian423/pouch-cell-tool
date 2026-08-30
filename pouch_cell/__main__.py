"""Allow ``python -m pouch_cell`` to invoke the CLI."""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
