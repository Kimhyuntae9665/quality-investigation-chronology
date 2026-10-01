"""CPU startup and frozen-source integrity smoke check; no model calls."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from quality_queue.domain import load_snapshot
assert load_snapshot(ROOT/"data/packet-v1").base
print("CPU startup and source integrity passed")
