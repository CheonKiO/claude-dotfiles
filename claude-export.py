#!/usr/bin/env python3
"""claude-export.py — bundle one project's Claude Code history + global config into a
single .tar.gz for transfer to another machine (unpack there with claude-import.py).

Cross-platform (Linux / macOS / WSL / native Windows): stdlib only, no shell-out.
Pure-python replacement for the old claude-export.sh.

Project history = every session slug under ~/.claude/projects whose decoded cwd is at or
below --repo (main tree + worktrees + docs/superpowers/plans etc.).
Personal = <repo>/private/.
Excluded = global config. CLAUDE.md / settings.json / plugins/ are this dotfiles repo's job
(sync.py, install-plugins.py); shipping them here only bloated the archive (plugins/cache
alone was 2.8G) and let an import overwrite what sync.py merges. Also excluded:
.credentials.json (login token), history.jsonl, other projects.

Usage:
  python claude-export.py --repo /path/to/project [--project-name name] [--out-dir DIR]
env fallbacks: REPO_ROOT, PROJECT_NAME, CLAUDE_DIR (default ~/.claude), out-dir default $HOME.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

# Absolute path -> Claude Code project-slug. Kept only as a fallback: guessing the slug
# was already wrong once (it also maps _ to -, so /Users/me/ssafy_histour lands in
# -Users-me-ssafy-histour and this regex missed it, failing the export outright).
SLUG_RE = re.compile(r"[/\\.:_]")

# How many lines to read from a transcript before giving up on finding its cwd.
CWD_PROBE_LINES = 40


def path_to_slug(path):
    return SLUG_RE.sub("-", path)


def slug_cwds(slug_dir):
    """Every cwd recorded inside a slug's transcripts. Each line carries the absolute
    working directory it was written from, so this identifies a slug by content instead
    of by reversing an undocumented naming rule."""
    found = set()
    for jsonl in slug_dir.glob("*.jsonl"):
        try:
            with jsonl.open(encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i >= CWD_PROBE_LINES:
                        break
                    try:
                        cwd = json.loads(line).get("cwd")
                    except (json.JSONDecodeError, AttributeError):
                        continue
                    if cwd:
                        found.add(cwd)
        except OSError:
            continue
    return found


def find_slugs(proj_dir, repo_root):
    """Slugs belonging to this repo: any whose transcripts were written at or below
    repo_root (main tree + worktrees), plus the name-based match so a slug whose
    transcripts predate the cwd field, or hold none, is still picked up."""
    prefix = path_to_slug(repo_root)
    root = Path(repo_root)
    hits = []
    for p in sorted(proj_dir.iterdir()):
        if not p.is_dir():
            continue
        if p.name.startswith(prefix):
            hits.append(p)
            continue
        for cwd in slug_cwds(p):
            try:
                below = Path(cwd) == root or root in Path(cwd).parents
            except (ValueError, OSError):
                below = False
            if below:
                hits.append(p)
                break
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("REPO_ROOT"),
                    help="Absolute path to the project repo root")
    ap.add_argument("--project-name", default=os.environ.get("PROJECT_NAME"),
                    help="Archive/label name (default: repo dir basename)")
    ap.add_argument("--out-dir", default=None,
                    help="Where to write the archive (default: $HOME)")
    args = ap.parse_args()

    if not args.repo:
        sys.exit("!! --repo (or REPO_ROOT env) required")

    claude_dir = Path(os.environ.get("CLAUDE_DIR", str(Path.home() / ".claude")))
    repo_root = str(Path(args.repo).resolve())
    project_name = args.project_name or Path(repo_root).name
    out_dir = Path(args.out_dir) if args.out_dir else Path.home()
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = out_dir / f"claude-{project_name}-{stamp}.tar.gz"

    proj_dir = claude_dir / "projects"
    if not proj_dir.is_dir():
        sys.exit(f"!! projects folder missing: {proj_dir}")

    slugs = find_slugs(proj_dir, repo_root)
    if not slugs:
        sys.exit(f"!! no slug under {proj_dir} names or records {repo_root}")

    print(f">> {len(slugs)} slug(s):")
    for s in slugs:
        print(f"   {s.name}")

    with tempfile.TemporaryDirectory() as stage:
        root = Path(stage) / "claude-export"
        (root / "projects").mkdir(parents=True)

        # Provenance for import: original repo path + this archive's stamp.
        (root / "REPO_ROOT.txt").write_text(repo_root + "\n", encoding="utf-8")
        (root / "EXPORT_STAMP.txt").write_text(stamp + "\n", encoding="utf-8")

        for s in slugs:
            print(f">> project history: {s.name}")
            shutil.copytree(s, root / "projects" / s.name)

        private = Path(repo_root) / "private"
        if private.is_dir():
            print(">> private/ (in-repo personal docs)")
            shutil.copytree(private, root / "private")

        exclude = Path(repo_root) / ".git" / "info" / "exclude"
        if exclude.is_file():
            print(">> .git/info/exclude (local gitignore rules)")
            shutil.copy2(exclude, root / "git-info-exclude.txt")

        importer = Path(__file__).resolve().parent / "claude-import.py"
        if importer.is_file():
            shutil.copy2(importer, root / "claude-import.py")
        else:
            print(f"!! warning: claude-import.py not found next to this script "
                  f"({importer}); archive won't be self-unpacking", file=sys.stderr)

        out_dir.mkdir(parents=True, exist_ok=True)
        print(">> compressing...")
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(root, arcname="claude-export")

    size_mb = archive.stat().st_size / (1024 * 1024)
    print()
    print(f"done: {archive} ({size_mb:.0f}M)")
    print(f"on the new machine:  tar -xzf {archive.name} && "
          f"python claude-export/claude-import.py")

    # Prune older archives for this project in the same folder (keep the new one).
    for old in out_dir.glob(f"claude-{project_name}-*.tar.gz"):
        if old.resolve() == archive.resolve():
            continue
        print(f">> removing old archive: {old.name}")
        old.unlink()


if __name__ == "__main__":
    main()
