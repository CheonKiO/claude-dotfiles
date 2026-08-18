#!/usr/bin/env python3
"""claude-sync.py — mirror one project's Claude Code state to a cloud remote via rclone.

Replaces the tar.gz export/import pair for day-to-day use. Three reasons:

  * rclone talks to the provider's API directly, so `push` only returns once the bytes are
    actually there. The Google Drive desktop client syncs lazily — closing the laptop before
    it finished meant arriving at the other machine with missing data.
  * A plain directory mirror transfers only the files that changed. A gzip stream differs
    everywhere after a one-byte edit, so every session end re-uploaded the whole archive.
  * No archive means no size ceiling and no pruning, so a 67M transcript is a non-issue.

Slug canonicalization
  Claude Code derives a project's slug from the *resolved* working directory, so the same
  project on two machines (/home/kio/omok vs /Users/me/Development/omok) gets two slugs and
  the remote used to accumulate them side by side under projects/<slug>/ — they never
  converged and `resume` on each machine only saw its own. Now every machine reads and
  writes ONE remote dir, <base>/sessions/, in which the repo-root path is stored as the
  token __CLAUDE_PROJECT_ROOT__ (machine-neutral, same idiom as the repo's __PY__ hook
  token). push tokenizes local -> token and unions into the remote; pull detokenizes
  token -> this machine's repo root and merges into the local slug. Tokenized both sides
  means identical checksums across machines, so nothing re-uploads on every sync.

  claude-sync.py push    --repo PATH [--remote gdrive:claude-sync]
  claude-sync.py pull    --repo PATH [--remote ...] [--new-repo-path PATH]
  claude-sync.py status  --repo PATH [--remote ...]
  claude-sync.py migrate --repo PATH [--remote ...]   # one-time: old projects/<slug> -> sessions/

A brand-new machine has no local slug dir yet (Claude's slug encoding is undocumented, and
reversing it already bit us on the _ -> - mapping), so open Claude in the repo once to
create the slug, then pull.

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
CWD_TOKEN = "__CLAUDE_PROJECT_ROOT__"
STATE_DIR = Path.home() / ".claude" / "sync-state"
CACHE_DIR = Path.home() / ".claude" / "sync-cache"
# Merge-conflict copies are local review artifacts (see claude_sync_merge.set_aside). They
# must never ride the wire: uploading them propagates one machine's conflict to every other,
# and pulling the remote's stale ones re-litters a slug that was just cleaned.
EXCLUDE_INCOMING = ["*.incoming-*"]


def run(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def state_path(project):
    return STATE_DIR / f"{project}.json"


def cache_dir(project, sub):
    """Persistent per-project mirror of a remote subtree, kept byte-identical to the remote
    (neutral-token form for sessions) so rclone --checksum transfers only changed files instead
    of re-downloading the whole tree into a fresh tempdir every sync. Never detokenize this dir
    in place — that breaks checksum parity and forces a full re-download; detokenize a copy."""
    d = CACHE_DIR / project / sub
    d.mkdir(parents=True, exist_ok=True)
    return d


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


def native_slug(claude_dir: Path, repo_root: str):
    """The local slug dir whose sessions were recorded exactly at repo_root (the one Claude
    writes to when launched here). Prefers an exact cwd match; falls back to any slug under
    repo_root; None if this machine has never opened Claude in the repo."""
    slugs = find_slugs(claude_dir, repo_root)
    for s in slugs:
        if repo_root in slug_cwds(s):
            return s
    return slugs[0] if slugs else None


def remote_base(remote, project):
    return f"{remote.rstrip('/')}/{project}"


def sessions_remote(base):
    return f"{base}/sessions"


def rewrite_paths(root: Path, frm: str, to: str):
    """Rewrite frm -> to inside every *.jsonl / *.json under root, in place. Used to swap
    the repo-root path for the machine-neutral token (push) and back (pull)."""
    for f in root.rglob("*"):
        if f.is_file() and f.suffix in (".jsonl", ".json"):
            try:
                txt = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if frm in txt:
                f.write_text(txt.replace(frm, to), encoding="utf-8")


def rclone_copy(src, dst, allow_missing_src=False, excludes=()):
    cmd = ["rclone", "copy", str(src), str(dst), "--checksum", "--transfers", "4",
           "--checkers", "8", "--fast-list"]
    for pat in excludes:
        cmd += ["--exclude", pat]
    r = run(cmd)
    if r.returncode != 0 and allow_missing_src and "directory not found" in (r.stderr or ""):
        return None                       # remote dir does not exist yet — treat as empty
    return r


def cmd_push(args, claude_dir, repo_root, project):
    base = remote_base(args.remote, project)
    sess = sessions_remote(base)
    write_state(project, repo=repo_root, remote=args.remote,
                push={"state": "running", "at": now_iso()})

    slugs = find_slugs(claude_dir, repo_root)
    if not slugs:
        write_state(project, push={"state": "failed", "at": now_iso(),
                                   "error": f"no slug records {repo_root}"})
        sys.exit(f"!! no slug under {claude_dir/'projects'} records {repo_root}")

    print(f">> push {project} -> {sess}")
    errors = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # Consolidate every local slug for this project into one staging dir, then swap this
        # machine's repo-root path for the neutral token. Snapshotting into a temp dir also
        # makes the upload source immutable while a live session keeps appending.
        local = tmp / "local"
        local.mkdir()
        for s in slugs:
            merge_tree(s, local)
        rewrite_paths(local, repo_root, CWD_TOKEN)

        # Union with whatever the remote already holds so a push never drops another
        # machine's sessions or memory lines, then upload the union. The remote mirror is the
        # persistent cache (not a fresh tempdir), so this download is incremental — only files
        # another machine changed come down. .incoming-* conflict copies are excluded from the
        # upload so they never propagate off this machine.
        remote = cache_dir(project, "sessions")
        rclone_copy(sess, remote, allow_missing_src=True, excludes=EXCLUDE_INCOMING)
        merge_tree(local, remote)
        up = rclone_copy(remote, sess, excludes=EXCLUDE_INCOMING)
        if up is not None and up.returncode != 0:
            tail = (up.stderr or "").strip().splitlines()
            errors.append(f"sessions: {tail[-1] if tail else 'rclone failed'}")

        private = Path(repo_root) / "private"
        if private.is_dir():
            snap = tmp / "private"
            shutil.copytree(private, snap)
            rp = rclone_copy(snap, f"{base}/private")
            if rp is not None and rp.returncode != 0:
                tail = (rp.stderr or "").strip().splitlines()
                errors.append(f"private: {tail[-1] if tail else 'rclone failed'}")

        # .ua = understand-anything knowledge graph. Expensive to regenerate
        # (full scan + LLM), so we mirror it like private/ rather than rebuild per machine.
        ua = Path(repo_root) / ".ua"
        if ua.is_dir():
            snap = tmp / "ua"
            shutil.copytree(ua, snap)
            ru = rclone_copy(snap, f"{base}/ua")
            if ru is not None and ru.returncode != 0:
                tail = (ru.stderr or "").strip().splitlines()
                errors.append(f".ua: {tail[-1] if tail else 'rclone failed'}")

    if errors:
        write_state(project, push={"state": "failed", "at": now_iso(),
                                   "error": "; ".join(errors)[:400]})
        sys.exit(f"!! {len(errors)} transfer(s) failed — data is NOT on the remote")

    newest = remote_newest(base)
    write_state(project, push={"state": "ok", "at": now_iso()},
                seen=newest or "", remote_newest=newest or "", remote_checked=now_iso())
    print("push complete — verified on the remote")


def cmd_pull(args, claude_dir, repo_root, project):
    base = remote_base(args.remote, project)
    sess = sessions_remote(base)
    target = native_slug(claude_dir, repo_root)
    if target is None:
        sys.exit(f"!! no local slug records {repo_root} yet — open Claude in the repo once "
                 f"to create it, then pull")

    # Fast path: if the remote is no newer than what we last recorded and the local cache is
    # already populated (so a prior pull merged that state), there is nothing to merge — skip
    # the whole copy+detokenize+merge, which otherwise runs full every time even for 0 changes.
    # One lsjson listing decides it. --force overrides. Also silences the per-pull cross-platform
    # .incoming churn on unchanged remotes.
    newest = remote_newest(base)
    seen = read_state(project).get("seen", "")
    if not args.force and newest and seen and newest <= seen \
            and any(cache_dir(project, "sessions").iterdir()):
        write_state(project, repo=repo_root, remote=args.remote,
                    remote_newest=newest, remote_checked=now_iso())
        print(f">> pull {sess}: remote up to date (newest {newest} <= seen {seen}) — skipped")
        return

    print(f">> pull {sess} -> {target.name}")
    dest_repo = Path(args.new_repo_path or repo_root)
    # Persistent caches make each rclone download incremental. Sessions are stored tokenized
    # (like the remote), so detokenize a throwaway copy rather than the cache itself — mutating
    # the cache would break checksum parity and re-download everything next time. private/ and
    # .ua/ carry no token, so they merge straight from cache. .incoming-* conflict copies are
    # excluded so the remote's stale ones never re-enter a slug that was already cleaned.
    csess = cache_dir(project, "sessions")
    r = rclone_copy(sess, csess, allow_missing_src=True, excludes=EXCLUDE_INCOMING)
    if r is not None and r.returncode != 0:
        sys.exit(f"!! rclone copy failed: {(r.stderr or '').strip()[-300:]}")
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "sessions"
        shutil.copytree(csess, stage)
        rewrite_paths(stage, CWD_TOKEN, repo_root)
        merge_tree(stage, target)

    cpriv = cache_dir(project, "private")
    rclone_copy(f"{base}/private", cpriv, allow_missing_src=True, excludes=EXCLUDE_INCOMING)
    if any(cpriv.iterdir()):
        if dest_repo.is_dir():
            print(f">> private/ -> {dest_repo / 'private'}")
            merge_tree(cpriv, dest_repo / "private")
        else:
            print(f"!! {dest_repo} missing — skipped private/", file=sys.stderr)

    cua = cache_dir(project, "ua")
    rclone_copy(f"{base}/ua", cua, allow_missing_src=True, excludes=EXCLUDE_INCOMING)
    if any(cua.iterdir()):
        if dest_repo.is_dir():
            print(f">> .ua/ -> {dest_repo / '.ua'}")
            merge_tree(cua, dest_repo / ".ua")
        else:
            print(f"!! {dest_repo} missing — skipped .ua/", file=sys.stderr)

    newest = remote_newest(base)
    write_state(project, repo=repo_root, remote=args.remote,
                seen=newest or "", remote_newest=newest or "", remote_checked=now_iso())
    print(f"\npull complete — {summary()}")


def cmd_migrate(args, claude_dir, repo_root, project):
    """One-time: fold the old per-machine projects/<slug>/ dirs into the canonical
    sessions/ dir, tokenizing each slug's literal repo path. Leaves the old dirs in place;
    delete them by hand once the result is verified."""
    base = remote_base(args.remote, project)
    sess = sessions_remote(base)
    old = f"{base}/projects"
    r = run(["rclone", "lsf", old, "--dirs-only"])
    if r.returncode != 0:
        sys.exit(f"nothing to migrate — no {old}")
    dirs = [d.strip().rstrip("/") for d in r.stdout.splitlines() if d.strip()]
    if not dirs:
        sys.exit(f"nothing to migrate — {old} is empty")

    print(f">> migrate {len(dirs)} slug(s) -> {sess}")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        union = tmp / "union"
        union.mkdir()
        rclone_copy(sess, union, allow_missing_src=True)      # seed with any existing canonical
        for d in dirs:
            dl = tmp / d
            dl.mkdir()
            rclone_copy(f"{old}/{d}", dl)
            for cwd in slug_cwds(dl):                         # each old slug carries a literal cwd
                rewrite_paths(dl, cwd, CWD_TOKEN)
            merge_tree(dl, union)
            print(f"   folded {d}")
        up = rclone_copy(union, sess)
        if up is not None and up.returncode != 0:
            sys.exit(f"!! upload failed: {(up.stderr or '').strip()[-300:]}")
    print(f"migrated -> {sess}. verify, then delete the old dir with:\n"
          f"   rclone purge {old}")


def remote_newest(base):
    """Newest mtime on the remote, as an ISO string, or None. Used as the marker both
    push and pull record so the statusline can tell 'remote has something we have not
    taken' from 'remote is our own last push'."""
    r = run(["rclone", "lsjson", base, "--recursive", "--files-only", "--fast-list"])
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
    ap.add_argument("action", choices=("push", "pull", "status", "refresh", "migrate"))
    ap.add_argument("--repo", default=os.environ.get("REPO_ROOT"), required=False)
    ap.add_argument("--project-name", default=os.environ.get("PROJECT_NAME"))
    ap.add_argument("--remote", default=os.environ.get("SYNC_REMOTE", DEFAULT_REMOTE))
    ap.add_argument("--new-repo-path", default=None,
                    help="pull only: where private/ should land on this machine")
    ap.add_argument("--detach", action="store_true",
                    help="run in the background and return immediately (for hooks)")
    ap.add_argument("--force", action="store_true",
                    help="pull only: bypass the up-to-date fast path and merge anyway")
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
     "refresh": cmd_refresh, "migrate": cmd_migrate}[args.action](args, claude_dir, repo_root, project)


if __name__ == "__main__":
    main()
