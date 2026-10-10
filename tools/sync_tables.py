"""Copy the server's Archipelago tables into the world, so ids always match:
python tools/sync_tables.py ../UmamusumeX-Private"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
server = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT.parent / "UmamusumeX-Private")
src = server / "server" / "umaps" / "features" / "archipelago" / "tables.py"
shutil.copyfile(src, ROOT / "umamusume" / "tables.py")
print(f"copied {src}")
