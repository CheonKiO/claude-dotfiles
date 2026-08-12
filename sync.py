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

PY_TOKEN = "__PY__"
# Managed hooks this repo owns — matched by script basename so a prior version
# (old hardcoded path or a different interpreter) is replaced, never duplicated.
MANAGED_SCRIPTS = ("file-size-guard.py", "git-fetch-guard.py")


def detect_python():
    """Interpreter invocation that exists on this OS: python3 -> python -> py -3."""
    for cand in (["python3"], ["python"], ["py", "-3"]):
        if shutil.which(cand[0]):
            return " ".join(cand)
    return "python3"


def copy_file(name):
    src = REPO_DIR / name
    dst = CLAUDE_DIR / name
    shutil.copy2(src, dst)
    print(f"copied {name}")


def copy_tree(name):
    src = REPO_DIR / name
    if not src.exists():
        return
    dst = CLAUDE_DIR / name
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        if item.is_file():
            rel = item.relative_to(src)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
    print(f"copied {name}/")


def _is_managed(command):
    return any(s in (command or "") for s in MANAGED_SCRIPTS)


def merge_hooks():
    fragment = json.loads((REPO_DIR / "hooks.settings.json").read_text())
    incoming = fragment.get("hooks", {})
    interp = detect_python()

    settings_path = CLAUDE_DIR / "settings.json"
    settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    hooks = settings.setdefault("hooks", {})

    for event, entries in incoming.items():
        existing = hooks.setdefault(event, [])
        # Drop any prior version of our managed hooks (old hardcoded /home path or a
        # stale interpreter) so re-running never leaves the hook registered twice.
        pruned = []
        for e in existing:
            kept = [h for h in e.get("hooks", []) if not _is_managed(h.get("command"))]
            if kept:
                pruned.append({**e, "hooks": kept})
        existing[:] = pruned
        # Insert current definitions, rendering __PY__ -> this OS's interpreter.
        for entry in entries:
            rendered = [
                {**h, "command": (h.get("command") or "").replace(PY_TOKEN, interp)}
                for h in entry.get("hooks", [])
            ]
            existing.append({**entry, "hooks": rendered})

    settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
    print(f"merged hooks into settings.json (interpreter: {interp})")


def merge_permissions():
    """Add this repo's curated safe allow-rules to settings.json without removing any
    rule already there. Additive + dedup only (capture never pulls permissions back,
    so the curated list stays hand-maintained in the repo)."""
    frag_path = REPO_DIR / "permissions.settings.json"
    if not frag_path.exists():
        return
    curated = json.loads(frag_path.read_text()).get("permissions", {}).get("allow", [])
    settings_path = CLAUDE_DIR / "settings.json"
    settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    allow = settings.setdefault("permissions", {}).setdefault("allow", [])
    seen = set(allow)
    added = 0
    for rule in curated:
        if rule not in seen:
            allow.append(rule)
            seen.add(rule)
            added += 1
    settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
    print(f"merged {added} permission allow rule(s)")


def register_statusline():
    """Point settings.json statusLine at the deployed statusline.py with this OS's
    interpreter. Derived per-machine (not synced), so capture.py leaves it alone."""
    script = CLAUDE_DIR / "statusline.py"
    if not script.exists():
        return
    interp = detect_python()
    settings_path = CLAUDE_DIR / "settings.json"
    settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    settings["statusLine"] = {"type": "command", "command": f'{interp} "{script}"'}
    settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
    print("registered statusLine")


def main():
    CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
    copy_file("CLAUDE.md")
    copy_file("RTK.md")
    copy_tree("skills")
    copy_tree("hooks")
    copy_file("claude-export.py")
    copy_file("claude-import.py")
    copy_file("statusline.py")
    for d in ("commands", "agents", "output-styles"):
        copy_tree(d)
    merge_hooks()
    register_statusline()
    merge_permissions()
    print(f"done → {CLAUDE_DIR}")


if __name__ == "__main__":
    main()
