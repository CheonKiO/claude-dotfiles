#!/usr/bin/env python3
"""Install this repo's Claude Code config into ~/.claude on the current machine.

Safe to re-run (idempotent): overwrites CLAUDE.md/RTK.md/skills/hooks with this
repo's version, and merges hook registrations into settings.json without
duplicating entries or touching any other settings.json keys (permissions,
enabledPlugins, etc. stay whatever they already are on this machine).
"""
import json
import shutil
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent
CLAUDE_DIR = Path.home() / ".claude"


def copy_file(name):
    src = REPO_DIR / name
    dst = CLAUDE_DIR / name
    shutil.copy2(src, dst)
    print(f"copied {name}")


def copy_tree(name):
    src = REPO_DIR / name
    dst = CLAUDE_DIR / name
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        if item.is_file():
            rel = item.relative_to(src)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
    print(f"copied {name}/")


def merge_hooks():
    fragment = json.loads((REPO_DIR / "hooks.settings.json").read_text())
    incoming = fragment.get("hooks", {})

    settings_path = CLAUDE_DIR / "settings.json"
    settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    hooks = settings.setdefault("hooks", {})

    for event, entries in incoming.items():
        existing = hooks.setdefault(event, [])
        existing_keys = {
            (e.get("matcher"), h.get("command"))
            for e in existing
            for h in e.get("hooks", [])
        }
        for entry in entries:
            matcher = entry.get("matcher")
            new_hooks = [
                h for h in entry.get("hooks", [])
                if (matcher, h.get("command")) not in existing_keys
            ]
            if new_hooks:
                existing.append({**entry, "hooks": new_hooks})

    settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
    print("merged hooks into settings.json")


def main():
    CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
    copy_file("CLAUDE.md")
    copy_file("RTK.md")
    copy_tree("skills")
    copy_tree("hooks")
    merge_hooks()
    print(f"done → {CLAUDE_DIR}")


if __name__ == "__main__":
    main()
