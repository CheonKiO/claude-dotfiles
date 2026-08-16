#!/usr/bin/env python3
"""claude-import.py — unpack a claude-export.py archive into this machine's ~/.claude.
Run from inside the extracted claude-export/ folder (after `tar -xzf ...`).

Restores every project slug (main + worktrees + docs/superpowers/plans) and <repo>/private/.
Global config (CLAUDE.md, settings.json, plugins/) is deliberately untouched — this dotfiles
repo's sync.py / install-plugins.py own those.
Gotcha: a slug encodes the ORIGINAL absolute path. If this machine stores the repo at a
different path (different username/drive), pass --new-repo-path to rewrite every slug's base
(sub-paths like worktrees are preserved). Cross-platform, stdlib only.

  same path:      python claude-import.py
  different path:  python claude-import.py --new-repo-path /home/bob/work/S15P11A107
"""
import argparse
import os
import re
import shutil
import sys
from pathlib import Path

SLUG_RE = re.compile(r"[/\\.:]")


def path_to_slug(path):
    return SLUG_RE.sub("-", path)


sys.path.insert(0, str(Path(__file__).resolve().parent))
from claude_sync_merge import merge_tree, stats, summary  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--new-repo-path", default=os.environ.get("NEW_REPO_PATH"),
                    help="Rewrite slug base to this repo path on the new machine")
    args = ap.parse_args()

    claude_dir = Path(os.environ.get("CLAUDE_DIR", str(Path.home() / ".claude")))
    src = Path(__file__).resolve().parent

    repo_root_file = src / "REPO_ROOT.txt"
    old_root = repo_root_file.read_text(encoding="utf-8").strip() if repo_root_file.is_file() else ""
    if not old_root:
        sys.exit("!! REPO_ROOT.txt missing in archive — run from inside extracted claude-export/")
    old_base = path_to_slug(old_root)

    new_repo = args.new_repo_path
    new_base = path_to_slug(str(Path(new_repo).resolve())) if new_repo else old_base
    dest_repo = str(Path(new_repo).resolve()) if new_repo else old_root

    print(f">> target ~/.claude = {claude_dir}")
    print(f">> base path {old_root}  (slug {old_base})")
    if new_base != old_base:
        print(f"   rewrite -> {dest_repo}  (slug {new_base})")

    (claude_dir / "projects").mkdir(parents=True, exist_ok=True)

    # --- project slugs ---
    src_projects = src / "projects"
    if src_projects.is_dir():
        for slug_dir in sorted(src_projects.iterdir()):
            if not slug_dir.is_dir():
                continue
            old_slug = slug_dir.name
            if old_slug.startswith(old_base):
                new_slug = new_base + old_slug[len(old_base):]
            else:
                new_slug = old_slug
            dest = claude_dir / "projects" / new_slug
            print(f">> merge: {old_slug}")
            if new_slug != old_slug:
                print(f"        -> {new_slug}")
            merge_tree(slug_dir, dest)

    # --- personal docs (private/) restored under the destination repo ---
    private = src / "private"
    if private.is_dir():
        dest_repo_path = Path(dest_repo)
        if dest_repo_path.is_dir():
            print(f">> private/ -> {dest_repo_path / 'private'}")
            merge_tree(private, dest_repo_path / "private")
        else:
            print(f"!! warning: {dest_repo} missing — can't restore private/. "
                  f"Clone the repo first, then copy manually from: {private}", file=sys.stderr)

    # --- .git/info/exclude — a fresh clone has none, so private/ etc. show as untracked ---
    exclude_src = src / "git-info-exclude.txt"
    exclude_dst_parent = Path(dest_repo) / ".git" / "info"
    if exclude_src.is_file() and (Path(dest_repo) / ".git").is_dir():
        exclude_dst_parent.mkdir(parents=True, exist_ok=True)
        print(f">> .git/info/exclude -> {exclude_dst_parent / 'exclude'}")
        shutil.copy2(exclude_src, exclude_dst_parent / "exclude")

    stamp_file = src / "EXPORT_STAMP.txt"
    if stamp_file.is_file():
        shutil.copy2(stamp_file, Path.home() / ".claude-sync-imported")

    print()
    print(f"merge complete — {summary()}")
    if stats["conflict"]:
        print("   review the .incoming-* files: nothing local was overwritten.")
    print()
    print("notes:")
    print(" 1) login token not transferred. run 'claude' on this machine to log in.")
    print(" 2) global config is not in this archive by design — run this dotfiles repo's")
    print("    sync.py (CLAUDE.md/skills/hooks/settings merge) and install-plugins.py.")
    if new_base != old_base:
        print(f" 3) keep the repo at {dest_repo} so sessions link (worktrees under it too).")
    else:
        print(f" 3) keep the repo at {old_root} so sessions link, or re-run with --new-repo-path.")


if __name__ == "__main__":
    main()
