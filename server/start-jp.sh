#!/usr/bin/env bash
# Set up (first run) and start the UmaPS JP server + admin panel. macOS / Linux.
#   ./start-jp.sh              normal run
#   ./start-jp.sh --no-admin   don't open the admin panel
#   ./start-jp.sh --help       all options
set -euo pipefail
cd "$(dirname "$0")"
# The package's own portable Python first, then any installed one.
for py in ./python/bin/python3 python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
        exec "$py" server/launcher.py --region jp "$@"
    fi
done
echo "Python 3.11 or newer is required: https://www.python.org/downloads/" >&2
echo "  (Linux: install python3 and python3-venv from your package manager)" >&2
exit 1
