#!/usr/bin/env python3
"""PostToolUse hook (Edit|Write): warn when the touched file exceeds 500 lines."""
import json
import sys

LIMIT = 500


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return

    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path")
    if not file_path:
        return

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            line_count = sum(1 for _ in f)
    except OSError:
        return

    if line_count > LIMIT:
        print(
            f"파일 크기 경고: {file_path} 이 {line_count}줄로 {LIMIT}줄을 넘었습니다. "
            "분리를 검토하세요 (CLAUDE.md §7 구조 가드레일)."
        )


if __name__ == "__main__":
    main()
