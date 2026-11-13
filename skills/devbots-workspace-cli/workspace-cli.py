"""Devbots workspace entrypoint; resolve shared code relative to installation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devbots_common import main

if __name__ == "__main__":
    raise SystemExit(main("workspace"))
