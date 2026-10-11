"""Build dist/umamusume.apworld: python tools/build.py [version]

With a version (e.g. 0.5.0) the packed archipelago.json carries it as
world_version; without one, the file's own world_version is kept."""

import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
version = sys.argv[1].lstrip("v") if len(sys.argv) > 1 else None
tables_version = re.search(r'APWORLD_VERSION = "([^"]+)"', (ROOT / "umamusume" / "tables.py").read_text())[1]
if version and version != tables_version:
    sys.exit(f"tables.py says {tables_version}: set APWORLD_VERSION in the server's tables.py and sync first")
out = ROOT / "dist" / "umamusume.apworld"
out.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted((ROOT / "umamusume").glob("*")):
        if not f.is_file() or f.suffix not in (".py", ".json"):
            continue
        if f.name == "archipelago.json" and version:
            manifest = json.loads(f.read_text())
            manifest["world_version"] = version
            z.writestr(f"umamusume/{f.name}", json.dumps(manifest, indent=2) + "\n")
        else:
            z.write(f, f"umamusume/{f.name}")
print(out)
