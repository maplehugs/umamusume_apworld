"""Build dist/umamusume.apworld: python apworld/build.py [version]

Also builds the optional client plugin dist/umapd_archipelago.dll (zig through
uvx; skipped with a warning when that fails).

With a version (e.g. 0.5.0) the packed archipelago.json carries it as
world_version; without one, the file's own world_version is kept."""

import json
import subprocess
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "apworld" / "umamusume"
version = sys.argv[1].lstrip("v") if len(sys.argv) > 1 else None
tables_version = re.search(r'APWORLD_VERSION = "([^"]+)"', (WORLD / "tables.py").read_text())[1]
if version and version != tables_version:
    sys.exit(f"tables.py says {tables_version}: set APWORLD_VERSION in tables.py (here and in server/) first")
out = ROOT / "dist" / "umamusume.apworld"
out.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted(WORLD.glob("*")):
        if not f.is_file() or f.suffix not in (".py", ".json"):
            continue
        if f.name == "archipelago.json" and version:
            manifest = json.loads(f.read_text())
            manifest["world_version"] = version
            z.writestr(f"umamusume/{f.name}", json.dumps(manifest, indent=2) + "\n")
        else:
            z.write(f, f"umamusume/{f.name}")
print(out)

dll = ROOT / "dist" / "umapd_archipelago.dll"
src = ROOT / "source_code_dll" / "umapd_archipelago.c"
try:
    subprocess.run(["uvx", "--from", "ziglang==0.17.0", "python", "-m", "ziglang", "cc", "-target", "x86_64-windows-gnu",
                    "-shared", "-O2", "-s", "-o", str(dll), str(src)], check=True)
    for junk in (dll.with_suffix(".lib"), dll.with_suffix(".pdb")):
        junk.unlink(missing_ok=True)
    print(dll)
except (OSError, subprocess.CalledProcessError) as e:
    print(f"warning: {dll.name} not built ({e})")
