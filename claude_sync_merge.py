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


def _starts_with(bigger: Path, smaller: Path):
    """True if bigger's leading bytes are exactly smaller — i.e. bigger is smaller plus
    appended content."""
    left = smaller.stat().st_size
    with bigger.open("rb") as fb, smaller.open("rb") as fs:
        while left > 0:
            n = min(CHUNK, left)
            if fb.read(n) != fs.read(n):
                return False
            left -= n
    return True


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
    s, d = src.stat().st_size, dst.stat().st_size
    if src.suffix == ".jsonl" and s > d and _starts_with(src, dst):
        shutil.copy2(src, dst)
        stats["extended"] += 1
        print(f"   ^ {dst.name}  (+{(s - d) // 1024}KB)")
        return
    if src.suffix == ".jsonl" and d >= s and _starts_with(dst, src):
        stats["local-newer"] += 1
        return
    set_aside(src, dst, "diverged" if src.suffix == ".jsonl" else "differs")


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
