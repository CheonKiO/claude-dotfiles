#!/usr/bin/env python3
"""Pull the current ~/.claude state INTO this repo (opposite direction of sync.py).
Run this after editing CLAUDE.md/skills/hooks directly under ~/.claude, before
committing. Only touches the files this repo tracks — never touches memory/,
projects/, settings.local.json, or credentials."""
import json
import shutil
from pathlib import Path

from sync import MANAGED_SCRIPTS, PY_TOKEN, detect_python

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
    interp = detect_python()

    def untoken(command):
        command = command or ""
        if interp and command.startswith(interp + " "):
            return PY_TOKEN + command[len(interp):]
        return command

    # Keep only the hooks this repo owns, and re-tokenize the concrete interpreter back
    # to __PY__ so the committed fragment stays OS-neutral (mirror of sync.merge_hooks).
    hooks = {}
    for event, entries in settings.get("hooks", {}).items():
        kept = []
        for e in entries:
            managed = [
                {**h, "command": untoken(h.get("command"))}
                for h in e.get("hooks", [])
                if any(s in (h.get("command") or "") for s in MANAGED_SCRIPTS)
            ]
            if managed:
                kept.append({**e, "hooks": managed})
        if kept:
            hooks[event] = kept

    (REPO_DIR / "hooks.settings.json").write_text(
        json.dumps({"hooks": hooks}, indent=2, ensure_ascii=False) + "\n"
    )
    print("captured hooks.settings.json (managed hooks only, interpreter -> __PY__)")


def main():
    copy_file("CLAUDE.md")
    copy_file("RTK.md")
    copy_tree("skills")
    copy_tree("hooks")
    copy_file("claude-export.py")
    copy_file("claude-import.py")
    copy_file("statusline.py")
    for d in ("commands", "agents", "output-styles"):
        copy_tree(d)
    capture_hooks_fragment()
    print("done — review with `git diff`, then commit + push")


if __name__ == "__main__":
    main()
