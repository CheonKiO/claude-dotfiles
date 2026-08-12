#!/usr/bin/env python3
"""Reinstall the plugins this config uses, from plugins.manifest.json next to this
script. Idempotent: adds each marketplace then installs each plugin; already-present
ones just report and continue. Cross-platform (drives the `claude` CLI).

Run once on a new machine after sync.py:  python install-plugins.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

MANIFEST = Path(__file__).resolve().parent / "plugins.manifest.json"


def run(args):
    try:
        r = subprocess.run(["claude", "plugin", *args], capture_output=True, text=True, timeout=120)
        ok = r.returncode == 0
        msg = (r.stdout or r.stderr).strip().splitlines()
        print(f"   {'ok' if ok else 'skip/err'}: {msg[-1] if msg else ''}")
        return ok
    except Exception as e:
        print(f"   error: {e}")
        return False


def main():
    if not shutil.which("claude"):
        sys.exit("!! `claude` CLI not on PATH")
    if not MANIFEST.is_file():
        sys.exit(f"!! manifest missing: {MANIFEST}")

    data = json.loads(MANIFEST.read_text())

    for name, repo in data.get("marketplaces", {}).items():
        print(f">> marketplace add {name} ({repo})")
        run(["marketplace", "add", repo])

    for plugin in data.get("plugins", []):
        print(f">> install {plugin}")
        run(["install", plugin, "--scope", "user"])

    print("\ndone — restart Claude Code to load newly installed plugins.")


if __name__ == "__main__":
    main()
