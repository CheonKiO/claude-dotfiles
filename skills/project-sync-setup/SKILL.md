---
name: project-sync-setup
description: Use when starting a new project that needs the same cross-machine continuity as ieumgil/S15P11A107 had — auto-exports Claude Code state (session history, memory, private/ docs) to a cloud-synced folder on real session end, and nudges (never auto-applies) an import on the next machine's session start. Use proactively when the user says they'll be switching computers on a new project, or asks to set up "그 동기화" for a new repo.
---

# Project Sync Setup

이음길(S15P11A107) 프로젝트에서 만든 "세션 끝나면 클라우드로 자동 백업, 시작하면 새 백업 있는지 알려주기" 패턴을 새 프로젝트에 그대로 심는 스킬. `~/claude-export.sh`/`~/claude-import.sh`(전역, 프로젝트에 안 묶임)는 이미 `REPO_ROOT`/`PROJECT_NAME` env var로 어느 프로젝트든 재사용 가능하게 만들어져 있음 — 이 스킬은 그 위에 얹는 **프로젝트별 훅 배선**만 새로 만든다.

## 언제 쓰나

- 새 프로젝트 시작 + 여러 컴퓨터를 오갈 계획일 때
- "그 동기화 다시 세팅해줘" 류 요청

## 절차

### 1. 입력 확정

- 새 프로젝트의 절대경로(`REPO_ROOT`)
- 클라우드 드라이브 루트 경로(iCloud든 구글드라이브든 — WSL이면 `/mnt/c/Users/<윈도우유저>/...` 형태로 마운트된 경로인지 먼저 확인. 마운트 안 보이면 그 클라우드 앱이 해당 머신에 설치·로그인됐는지부터 확인)
- 프로젝트 이름(기본값: repo 폴더명) — 이게 아카이브 파일명(`claude-<이름>-<타임스탬프>.tar.gz`)과 클라우드 서브폴더명(`claude-sync-<이름>`)에 쓰여서, **다른 프로젝트와 같은 클라우드 폴더를 공유해도 서로 안 섞이고 안 지운다.**

### 2. 생성기 실행

```bash
python3 ~/.claude/skills/project-sync-setup/setup.py \
  --repo /path/to/new-project \
  --cloud-dir /mnt/c/Users/<윈도우유저>/iCloudDrive
```

이게 하는 일:
- `<repo>/.claude/hooks/session-end-sync.py` — SessionEnd(`prompt_input_exit`/`logout`/`other`)에서 백그라운드로 `~/claude-export.sh` 호출. 원자적 락(`O_CREAT|O_EXCL`)으로 동시 다중세션 종료 시 중복 실행 방지. 스로틀 10초(순간적 버스트만 뭉치고, 진짜 재종료는 절대 안 막음 — 5분처럼 길게 잡으면 그 사이 대화가 안 담긴 채 넘어갈 수 있음, 이음길에서 실제로 지적된 문제).
- `<repo>/.claude/hooks/session-start-check.py` — SessionStart(`startup`)에서 클라우드에 안 가져온 최신 아카이브 있으면 `initialUserMessage`로 강제 주입(그냥 `additionalContext`만 쓰면 조용히 씹힐 수 있음 — 이음길에서 실측으로 확인된 약점). 절대 자동 import 안 함.
- `<repo>/.claude/settings.local.json`에 두 훅 등록(기존 내용 보존, hooks 키만 병합).
- 클라우드 서브폴더 생성.

### 3. 확인

- `.git/info/exclude`에 `.claude/`가 이미 있는지 확인(없으면 추가) — 프로젝트 로컬 훅 스크립트·settings가 커밋되면 안 됨.
- 세션 하나 끄고 `~/.claude-sync-<프로젝트명>-export.log` 생기는지 확인.
- 클라우드 폴더에 `claude-<프로젝트명>-*.tar.gz` 생기는지 확인.

## 알아둘 것 (이음길에서 겪은 함정, 미리 회피됨)

- **훅 payload 필드명은 문서랑 다를 수 있다** — `SessionEnd`의 사유 필드는 문서상 `session_end_reason`이라 나왔지만 실제로는 `reason`이었음(이 템플릿은 이미 `reason`으로 맞춰져 있음). 다른 필드도 의심되면 훅 스크립트에 디버그 로그 한 줄(`json.dump(payload, ...)`) 임시로 넣어서 실측할 것.
- **`/tmp`는 훅 실행마다 격리될 수 있다** — 상태 파일(스로틀·마커 등)은 `$HOME` 밑에 둘 것, `/tmp` 쓰지 말 것(이 템플릿은 이미 그렇게 돼있음).
- **import는 절대 자동화하지 않는다** — 압축 손상 위험, 그리고 "같은 컴퓨터에서 껐다 켠 것"일 수도 있어서 무조건 사람이 확인하고 실행.
