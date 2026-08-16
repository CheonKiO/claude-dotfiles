#!/usr/bin/env python3
"""claude-sync.py — mirror one project's Claude Code state to a cloud remote via rclone.

Replaces the tar.gz export/import pair for day-to-day use. Three reasons:

  * rclone talks to the provider's API directly, so `push` only returns once the bytes are
    actually there. The Google Drive desktop client syncs lazily — closing the laptop before
    it finished meant arriving at the other machine with missing data.
  * A plain directory mirror transfers only the files that changed. A gzip stream differs
    everywhere after a one-byte edit, so every session end re-uploaded the whole archive.
  * No archive means no size ceiling and no pruning, so a 67M transcript is a non-issue.

  claude-sync.py push   --repo PATH [--remote gdrive:claude-sync]
  claude-sync.py pull   --repo PATH [--remote ...] [--new-repo-path PATH]
  claude-sync.py status --repo PATH [--remote ...]

Pull never overwrites blindly: it stages the remote locally, then merges with
claude_sync_merge (append-only proof required to replace, conflicts set aside).
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from claude_sync_merge import merge_tree, summary  # noqa: E402

DEFAULT_REMOTE = "gdrive:claude-sync"
CWD_PROBE_LINES = 40
STATE_DIR = Path.home() / ".claude" / "sync-state"


def run(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def state_path(project):
    return STATE_DIR / f"{project}.json"


def read_state(project):
    try:
        return json.loads(state_path(project).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(project, **fields):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    st = read_state(project)
    st.update(fields)
    state_path(project).write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")
    return st


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def detach(argv):
    """Re-run ourselves without the --detach flag, fully detached, so a SessionEnd hook
    returns immediately. Uploading 83M over the shared Drive client_id took 12 minutes on
    first push and 2 minutes incremental — far too long to hold a session close. The run
    still records success or failure in the state file, which the statusline surfaces, so
    nothing is silently lost by not waiting."""
    cmd = [sys.executable, str(Path(__file__).resolve())] + [a for a in argv if a != "--detach"]
    kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008          # DETACHED_PROCESS
    else:
        kw["start_new_session"] = True
    subprocess.Popen(cmd, **kw)


def require_rclone():
    if not shutil.which("rclone"):
        sys.exit("!! rclone not on PATH — install it, then `rclone config create gdrive drive`")


def slug_cwds(slug_dir: Path):
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


def find_slugs(claude_dir: Path, repo_root: str):
    """Slugs whose transcripts were written at or below repo_root. Identified by the cwd
    recorded on each line rather than by reversing Claude Code's slug naming, which is
    undocumented and already caught us out once (it maps _ to - as well)."""
    proj = claude_dir / "projects"
    if not proj.is_dir():
        return []
    root = Path(repo_root)
    hits = []
    for p in sorted(proj.iterdir()):
        if not p.is_dir():
            continue
        for cwd in slug_cwds(p):
            try:
                if Path(cwd) == root or root in Path(cwd).parents:
                    hits.append(p)
                    break
            except (ValueError, OSError):
                continue
    return hits


def remote_base(remote, project):
    return f"{remote.rstrip('/')}/{project}"


def cmd_push(args, claude_dir, repo_root, project):
    base = remote_base(args.remote, project)
    write_state(project, repo=repo_root, remote=args.remote,
                push={"state": "running", "at": now_iso()})

    slugs = find_slugs(claude_dir, repo_root)
    if not slugs:
        write_state(project, push={"state": "failed", "at": now_iso(),
                                   "error": f"no slug records {repo_root}"})
        sys.exit(f"!! no slug under {claude_dir/'projects'} records {repo_root}")

    print(f">> push {project} -> {base}")
    errors = []

    def send(src, dst, label):
        print(f"   {label}")
        r = run(["rclone", "copy", str(src), dst, "--checksum", "--transfers", "4"])
        if r.returncode != 0:
            tail = r.stderr.strip().splitlines()
            errors.append(f"{label}: {tail[-1] if tail else 'rclone failed'}")
            print(f"   !! {errors[-1]}")

    # Snapshot before uploading. A live session appends to its transcript continuously, so
    # uploading the file in place races the writer: rclone hashes it, uploads, then fails
    # the post-transfer check because the local file grew underneath it ("corrupted on
    # transfer: md5 hashes differ"). Copying locally first costs a fraction of a second and
    # makes the upload source immutable.
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        for s in slugs:
            snap = stage / "projects" / s.name
            shutil.copytree(s, snap)
            send(snap, f"{base}/projects/{s.name}", f"projects/{s.name}")

        private = Path(repo_root) / "private"
        if private.is_dir():
            snap = stage / "private"
            shutil.copytree(private, snap)
            send(snap, f"{base}/private", "private/")

    if errors:
        write_state(project, push={"state": "failed", "at": now_iso(),
                                   "error": "; ".join(errors)[:400]})
        sys.exit(f"!! {len(errors)} transfer(s) failed — data is NOT on the remote")

    newest = remote_newest(base)
    write_state(project, push={"state": "ok", "at": now_iso()},
                seen=newest or "", remote_newest=newest or "",
                remote_checked=now_iso())
    print("push complete — verified on the remote")


def cmd_pull(args, claude_dir, repo_root, project):
    base = remote_base(args.remote, project)
    print(f">> pull {base}")
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "remote"
        r = run(["rclone", "copy", base, str(stage), "--checksum", "--transfers", "4"])
        if r.returncode != 0:
            sys.exit(f"!! rclone copy failed: {r.stderr.strip()[-300:]}")

        src_projects = stage / "projects"
        if src_projects.is_dir():
            for slug_dir in sorted(src_projects.iterdir()):
                if not slug_dir.is_dir():
                    continue
                dest = claude_dir / "projects" / slug_dir.name
                print(f">> merge: {slug_dir.name}")
                merge_tree(slug_dir, dest)

        src_private = stage / "private"
        if src_private.is_dir():
            dest_repo = Path(args.new_repo_path or repo_root)
            if dest_repo.is_dir():
                print(f">> private/ -> {dest_repo / 'private'}")
                merge_tree(src_private, dest_repo / "private")
            else:
                print(f"!! {dest_repo} missing — skipped private/", file=sys.stderr)

    newest = remote_newest(base)
    write_state(project, repo=repo_root, remote=args.remote,
                seen=newest or "", remote_newest=newest or "",
                remote_checked=now_iso())
    print(f"\npull complete — {summary()}")


def remote_newest(base):
    """Newest mtime on the remote, as an ISO string, or None. Used as the marker both
    push and pull record so the statusline can tell 'remote has something we have not
    taken' from 'remote is our own last push'."""
    r = run(["rclone", "lsjson", base, "--recursive", "--files-only"])
    if r.returncode != 0:
        return None
    try:
        items = json.loads(r.stdout or "[]")
    except json.JSONDecodeError:
        return None
    times = [i.get("ModTime") for i in items if i.get("ModTime")]
    return max(times) if times else None


def cmd_refresh(args, claude_dir, repo_root, project):
    """Record what the remote currently holds. Fire-and-forget from the statusline so the
    indicator stays current without any network call on the render path."""
    base = remote_base(args.remote, project)
    newest = remote_newest(base)
    write_state(project, repo=repo_root, remote=args.remote,
                remote_newest=newest or "", remote_checked=now_iso())


def cmd_status(args, claude_dir, repo_root, project):
    base = remote_base(args.remote, project)
    newest = remote_newest(base)
    st = read_state(project)
    seen = st.get("seen", "")
    push = st.get("push") or {}
    write_state(project, remote_newest=newest or "", remote_checked=now_iso())

    print(f"remote  {base}")
    print(f"  newest    : {newest or '(empty)'}")
    print(f"  seen      : {seen or '(never)'}")
    print(f"  last push : {push.get('state', '(never)')} {push.get('at', '')}")
    if push.get("error"):
        print(f"              {push['error']}")
    if newest and newest > seen:
        print("  -> remote has changes you have not pulled")
    else:
        print("  -> up to date")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("push", "pull", "status", "refresh"))
    ap.add_argument("--repo", default=os.environ.get("REPO_ROOT"), required=False)
    ap.add_argument("--project-name", default=os.environ.get("PROJECT_NAME"))
    ap.add_argument("--remote", default=os.environ.get("SYNC_REMOTE", DEFAULT_REMOTE))
    ap.add_argument("--new-repo-path", default=None,
                    help="pull only: where private/ should land on this machine")
    ap.add_argument("--detach", action="store_true",
                    help="run in the background and return immediately (for hooks)")
    args = ap.parse_args()

    if not args.repo:
        sys.exit("!! --repo (or REPO_ROOT env) required")
    require_rclone()

    if args.detach:
        detach(sys.argv[1:])
        return

    claude_dir = Path(os.environ.get("CLAUDE_DIR", str(Path.home() / ".claude")))
    repo_root = str(Path(args.repo).resolve())
    project = args.project_name or Path(repo_root).name

    {"push": cmd_push, "pull": cmd_pull, "status": cmd_status,
     "refresh": cmd_refresh}[args.action](args, claude_dir, repo_root, project)


if __name__ == "__main__":
    main()
