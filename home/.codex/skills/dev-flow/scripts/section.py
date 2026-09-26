#!/usr/bin/env python3
"""Forward to `mdsec`, which replaced this script; dispatched contracts may still cite this path.

Delete this file and its test once no active task record or running attempt cites
`scripts/section.py`.
"""

import os
import shutil
import sys
from pathlib import Path

# This file sits at home/.codex/skills/dev-flow/scripts/ in the checkout that also holds mdsec.
sibling = Path(__file__).resolve().parents[4] / ".local/bin/mdsec"
target = str(sibling) if sibling.is_file() else shutil.which("mdsec")
if target is None:
    sys.exit("section.py: mdsec is missing; install it with setup_scripts/setup_config.sh")
os.execv(sys.executable, [sys.executable, target, *sys.argv[1:]])
