#!/usr/bin/env python3
"""Additive merge for Claude Code session data. Shared by claude-import.py (tar archives)
and claude-sync.py (rclone mirrors).

The rule everywhere: never delete or overwrite something local we cannot prove is stale.
Transcripts are append-only, so "the incoming copy starts with exactly the local bytes"
proves it is a strict superset and is the only case where a replace is allowed. Anything
else that differs is set aside as .incoming-<stamp> for a human to reconcile.
"""
import collections
import datetime
import hashlib
import json
import shutil
from pathlib import Path

CHUNK = 1 << 20
stats = collections.Counter()


def _stamp():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _identical(a: Path, b: Path):
    if a.stat().st_size != b.stat().st_size:
        return False
    with a.open("rb") as fa, b.open("rb") as fb:
        while True:
            ca, cb = fa.read(CHUNK), fb.read(CHUNK)
            if ca != cb:
                return False
            if not ca:
                return True


def _line_key(line: bytes):
    """Machine-independent identity for a transcript line. uuid-bearing lines (the actual
    conversation events — user/assistant/attachment/system) key by uuid, so the same event
    dedups across machines even though its embedded absolute paths differ (/home vs /Users).
    Lines without a uuid (mode, last-prompt, file-history snapshots, ...) key by their bytes —
    identical state lines dedup; the worst case for a path-bearing one is a harmless duplicate,
    never a loss."""
    try:
        u = json.loads(line).get("uuid")
    except Exception:
        u = None
    if u:
        return "u:" + str(u)
    return "h:" + hashlib.sha1(line).hexdigest()


def merge_jsonl_union(src: Path, dst: Path):
    """Union two copies of an append-only transcript by line identity (see _line_key). dst keeps
    all of its own lines in order; any src line whose identity dst lacks is appended in src order.
    Nothing is dropped, and byte-level path differences no longer masquerade as divergence — the
    failure mode of the old byte-prefix check. Returns the number of lines added."""
    seen = set()
    tmp = dst.with_name(dst.name + ".merging")
    added = 0
    last_nl = True
    with dst.open("rb") as fd, tmp.open("wb") as fo:
        for line in fd:
            fo.write(line)
            last_nl = line.endswith(b"\n")
            if line.strip():
                seen.add(_line_key(line))
        with src.open("rb") as fs:
            for line in fs:
                if not line.strip():
                    continue
                k = _line_key(line)
                if k not in seen:
                    if not last_nl:
                        fo.write(b"\n")
                        last_nl = True
                    fo.write(line)
                    last_nl = line.endswith(b"\n")
                    seen.add(k)
                    added += 1
    tmp.replace(dst)
    return added


def set_aside(src: Path, dst: Path, why: str):
    alt = dst.with_name(f"{dst.name}.incoming-{_stamp()}")
    shutil.copy2(src, alt)
    stats["conflict"] += 1
    print(f"   !! {why}: kept local {dst.name}, incoming copy -> {alt.name}")


def merge_memory_index(src: Path, dst: Path):
    """MEMORY.md is a one-line-per-memory index edited on both machines — union the lines
    rather than picking a side."""
    have = dst.read_text(encoding="utf-8").splitlines()
    seen = set(have)
    added = [ln for ln in src.read_text(encoding="utf-8").splitlines()
             if ln.strip() and ln not in seen]
    if not added:
        stats["same"] += 1
        return
    body = have + ([""] if have and have[-1].strip() else []) + added
    dst.write_text("\n".join(body) + "\n", encoding="utf-8")
    stats["index-merged"] += 1
    print(f"   ~ MEMORY.md  (+{len(added)} lines)")


def merge_file(src: Path, dst: Path):
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        stats["new"] += 1
        print(f"   + {dst.name}")
        return
    if _identical(src, dst):
        stats["same"] += 1
        return
    if dst.name == "MEMORY.md":
        merge_memory_index(src, dst)
        return
    # Transcripts (.jsonl) merge by line identity, not byte prefix: two copies of the same
    # session carry the same per-line uuids even when their embedded absolute paths differ
    # across machines (/home vs /Users, tokenized repo root vs not). The old byte-prefix check
    # read those path bytes as divergence and set the newer copy aside, silently dropping it.
    if src.suffix == ".jsonl":
        added = merge_jsonl_union(src, dst)
        if added:
            stats["extended"] += 1
            print(f"   ~ {dst.name}  (+{added} lines)")
        else:
            stats["same"] += 1
        return
    # Non-transcript files (agent meta.json, images, tool-result txt) are opaque — keep local
    # and set the differing incoming copy aside for a human, as before.
    set_aside(src, dst, "differs")


def merge_tree(src: Path, dst: Path):
    """Additive merge of a directory: new files land, existing ones follow merge_file's
    rules, nothing local is deleted."""
    for item in sorted(src.rglob("*")):
        if item.is_dir():
            continue
        merge_file(item, dst / item.relative_to(src))


def summary():
    return (f"new {stats['new']}, extended {stats['extended']}, unchanged {stats['same']}, "
            f"local-newer {stats['local-newer']}, index-merged {stats['index-merged']}, "
            f"conflicts {stats['conflict']}")
