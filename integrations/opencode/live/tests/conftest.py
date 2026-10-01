import sys
from pathlib import Path

# The oracle lives beside the rig, not in the frozen `tests/` tree, so the rig test
# structure has to put its own parent on the path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
