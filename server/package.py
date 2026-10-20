"""Release package of the server: python server/package.py [linux|windows]

-> dist/umaps-archipelago-server-linux-x86_64.tar.gz (or -windows-x86_64.zip)

The server's tracked files plus both race engines built in release mode, so the
launcher finds them up to date and needs no Rust, and a portable Python
(python-build-standalone, pinned and checked) in python/, so nothing needs to be
installed: start-global.bat/.sh use it, or a system Python 3.11+ without it.

windows cross-builds the engines with `cargo --target x86_64-pc-windows-gnu`,
which needs that target's standard library (rustup target add
x86_64-pc-windows-gnu) and a mingw linker (x86_64-w64-mingw32-gcc)."""

import hashlib
import io
import os
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
ENGINES = ("race_exact_rs", "race_engine_rs")
TARGETS = {"linux": None, "windows": "x86_64-pc-windows-gnu"}

# Portable CPython (astral-sh/python-build-standalone, the builds uv uses). A
# release at least two weeks old, its stripped install_only archives (no debug
# symbols: a fifth of the size) pinned by SHA256
# (from that release's SHA256SUMS): a changed file fails the build.
PYTHON_RELEASE = "20261003"
PYTHON_BUILDS = {
    "linux": ("cpython-3.12.15+20261003-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz",
              "731af898886c5f821890dc901eca3c651cca8e51fa7308c159d12a1194aeac91"),
    "windows": ("cpython-3.12.15+20261003-x86_64-pc-windows-msvc-install_only_stripped.tar.gz",
                "6fba7f2ae506facf41d457ea8293c7497910a675c69a4e954875169410a50402"),
}

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

def portable_python() -> tarfile.TarFile:
    """The pinned build, downloaded once into dist/.cache and checked."""
    name, sha = PYTHON_BUILDS[os_name]
    cached = ROOT / "dist" / ".cache" / name
    if not cached.is_file():
        cached.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://github.com/astral-sh/python-build-standalone/releases/download/{PYTHON_RELEASE}/{name}"
        urllib.request.urlretrieve(url, cached)
    if hashlib.sha256(cached.read_bytes()).hexdigest() != sha:
        cached.unlink()
        sys.exit(f"{name}: SHA256 mismatch, not packaging it")
    return tarfile.open(cached)


top = f"umaps-archipelago-server-{os_name}-x86_64"
out = ROOT / "dist" / (top + (".zip" if os_name == "windows" else ".tar.gz"))
out.parent.mkdir(exist_ok=True)


def entries():
    for f in files:
        yield ROOT / f, f"{top}/{f.removeprefix('server/')}"
    for arc, src in engines.items():
        yield src, f"{top}/{arc.removeprefix('server/')}"


python = portable_python()  # its members all sit under python/
if os_name == "windows":
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arc in entries():
            z.write(src, arc)
        for m in python.getmembers():
            if m.isfile():
                z.writestr(zipfile.ZipInfo(f"{top}/{m.name}", (1980, 1, 1, 0, 0, 0)), python.extractfile(m).read(),
                           zipfile.ZIP_DEFLATED)
else:
    with tarfile.open(out, "w:gz") as t:
        for src, arc in entries():
            t.add(src, arc)
        for m in python.getmembers():  # symlinks and modes kept (bin/python3 -> python3.12)
            data = python.extractfile(m) if m.isfile() else None
            m.name = f"{top}/{m.name}"
            t.addfile(m, data)
print(out)
