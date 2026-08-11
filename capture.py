#!/usr/bin/env python3
"""Pull the current ~/.claude state INTO this repo (opposite direction of sync.py).
Run this after editing CLAUDE.md/skills/hooks directly under ~/.claude, before
committing. Only touches the files this repo tracks — never touches memory/,
projects/, settings.local.json, or credentials."""
import json
import shutil
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent
CLAUDE_DIR = Path.home() / ".claude"


def copy_file(name):
    src = CLAUDE_DIR / name
    if not src.exists():
        return
    shutil.copy2(src, REPO_DIR / name)
    print(f"captured {name}")


def copy_tree(name):
    src = CLAUDE_DIR / name
    if not src.exists():
        return
    dst = REPO_DIR / name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    print(f"captured {name}/")


def capture_hooks_fragment():
    settings_path = CLAUDE_DIR / "settings.json"
    if not settings_path.exists():
        return
    settings = json.loads(settings_path.read_text())
    fragment = {"hooks": settings.get("hooks", {})}
    (REPO_DIR / "hooks.settings.json").write_text(
        json.dumps(fragment, indent=2, ensure_ascii=False) + "\n"
    )
    print("captured hooks.settings.json")


def main():
    copy_file("CLAUDE.md")
    copy_file("RTK.md")
    copy_tree("skills")
    copy_tree("hooks")
    capture_hooks_fragment()
    print("done — review with `git diff`, then commit + push")


if __name__ == "__main__":
    main()
