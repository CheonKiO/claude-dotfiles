#!/usr/bin/env python3
"""PreToolUse(Read) hook: when Read targets a *.pdf, extract its text layer with pdftotext
and redirect the Read to a cached .txt sidecar, so a text-layer PDF is read as cheap text
instead of expensive page images. Scanned / image-only PDFs (pdftotext yields nothing) fall
through untouched, so the normal vision Read still handles them (and can OCR with high-DPI crops).

Emits hookSpecificOutput.updatedInput to rewrite file_path; stays silent (allow unchanged) on
every failure path so a broken extraction never blocks a Read."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

MIN_TEXT = 20  # fewer real chars than this = no usable text layer -> treat as scanned


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    ti = data.get("tool_input") or {}
    fp = ti.get("file_path") or ""
    if not fp.lower().endswith(".pdf"):
        return
    pdf = Path(fp)
    if not pdf.is_file():
        return  # let Read surface the missing-file error itself
    try:
        mtime = int(pdf.stat().st_mtime)
    except OSError:
        return

    # Cache keyed by absolute path + mtime, so editing the PDF re-extracts but repeat reads reuse.
    key = hashlib.sha1(f"{pdf.resolve()}:{mtime}".encode()).hexdigest()[:12]
    cache_dir = Path.home() / ".claude" / "pdf-text-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    txt = cache_dir / f"{pdf.stem}-{key}.txt"

    if not txt.exists():
        try:
            subprocess.run(["pdftotext", "-layout", str(pdf), str(txt)],
                           capture_output=True, timeout=60)
        except (FileNotFoundError, subprocess.SubprocessError):
            return  # pdftotext absent or failed -> allow the vision Read

    try:
        body = txt.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return

    if len(body.strip()) < MIN_TEXT:
        try:
            txt.unlink()  # scanned PDF: no text layer, don't leave an empty cache file
        except OSError:
            pass
        return  # fall through to the normal (vision) Read

    new_input = dict(ti)
    new_input["file_path"] = str(txt)
    new_input.pop("pages", None)  # 'pages' renders PDF images; meaningless for the .txt
    print(json.dumps({
        "systemMessage": f"PDF has a text layer — reading extracted text ({txt.name}) "
                         f"instead of page images.",
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": new_input,
        },
    }))


main()
