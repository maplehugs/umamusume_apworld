"""Release package of the server: python server/package.py [linux|windows]

-> dist/umaps-archipelago-server-linux-x86_64.tar.gz (or -windows-x86_64.zip)

The server's tracked files plus both race engines built in release mode, so the
launcher finds them up to date and needs no Rust. Python 3.11+ is still needed:
the launcher makes its own environment on the first run.

windows cross-builds the engines with `cargo --target x86_64-pc-windows-gnu`,
which needs that target's standard library (rustup target add
x86_64-pc-windows-gnu) and a mingw linker (x86_64-w64-mingw32-gcc)."""

import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
ENGINES = ("race_exact_rs", "race_engine_rs")
TARGETS = {"linux": None, "windows": "x86_64-pc-windows-gnu"}

os_name = sys.argv[1] if len(sys.argv) > 1 else "linux"
if os_name not in TARGETS:
    sys.exit(f"usage: python server/package.py [{'|'.join(TARGETS)}]")
target = TARGETS[os_name]
exe = ".exe" if os_name == "windows" else ""

# Built engines, at the path the launcher and the server look for them.
engines = {}
for crate in ENGINES:
    crate_dir = SERVER / "server" / crate
    cmd = ["cargo", "build", "--release", "--locked", "--quiet",
           "--manifest-path", str(crate_dir / "Cargo.toml"), "--target-dir", str(crate_dir / "target")]
    env = {**os.environ, "RUSTFLAGS": "-Awarnings"}
    if target:
        cmd += ["--target", target]
        env["CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER"] = "x86_64-w64-mingw32-gcc"
    try:
        subprocess.run(cmd, check=True, env=env)
    except (OSError, subprocess.CalledProcessError) as e:
        sys.exit(f"{crate}: build failed ({e}). " + (__doc__.split("\n\n")[-1] if target else ""))
    built = crate_dir / "target" / (target or "") / "release" / (crate + exe)
    built.touch()  # newer than every source file: the launcher's "up to date" test
    engines[f"server/server/{crate}/target/release/{crate}{exe}"] = built

files = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "server"],
                       capture_output=True, text=True, check=True).stdout.split("\0")
files = [f for f in files if f and f != "server/package.py"]
# The plugin too, so the panel's Game setup can install it and check it's this release's.
dll = ROOT / "dist" / "umapd_archipelago.dll"
if not dll.is_file():
    sys.exit("dist/umapd_archipelago.dll is missing: run python apworld/build.py first")
engines["server/plugin/umapd_archipelago.dll"] = dll

top = f"umaps-archipelago-server-{os_name}-x86_64"
out = ROOT / "dist" / (top + (".zip" if os_name == "windows" else ".tar.gz"))
out.parent.mkdir(exist_ok=True)


def entries():
    for f in files:
        yield ROOT / f, f"{top}/{f.removeprefix('server/')}"
    for arc, src in engines.items():
        yield src, f"{top}/{arc.removeprefix('server/')}"


if os_name == "windows":
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arc in entries():
            z.write(src, arc)
else:
    with tarfile.open(out, "w:gz") as t:
        for src, arc in entries():
            t.add(src, arc)
print(out)
