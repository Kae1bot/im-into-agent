"""Run the bundled bridge with either embedded or system Python."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from im_bridge.cli import main

raise SystemExit(main())
