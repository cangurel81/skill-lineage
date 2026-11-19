"""Allow ``python -m skill_lineage``."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
