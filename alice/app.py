"""Compatibility entry point that always uses the guarded ALICE launcher."""
from .__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
