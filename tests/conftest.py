import os
import tempfile
from pathlib import Path

# Every collab test process loads Pi through node; a compile cache shared by all xdist workers and
# kept across runs saves most of that load. Node validates cached entries against the source.
os.environ.setdefault("NODE_COMPILE_CACHE", str(Path(tempfile.gettempdir()) / "usercustom-node-compile-cache"))
