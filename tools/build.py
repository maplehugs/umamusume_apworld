"""Build dist/umamusume.apworld: python tools/build.py"""

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / "dist" / "umamusume.apworld"
out.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted((ROOT / "umamusume").glob("*")):
        if f.is_file() and f.suffix in (".py", ".json"):
            z.write(f, f"umamusume/{f.name}")
print(out)
