---
name: project-sync-setup
description: Use when starting a new project that needs the same cross-machine continuity as ieumgil/S15P11A107 had — installs a SessionEnd hook that mirrors Claude Code state (session history, memory, private/, .ua/) to an rclone cloud remote, while pulling stays manual and the "remote is newer" signal lives in the status line. Use proactively when the user says they'll be switching computers on a new project, asks to set up "그 동기화" for a new repo, or renames/moves a synced project's root.
---

# Project Sync Setup

한 프로젝트의 Claude Code 상태(대화 기록·memory·`private/`·`.ua/`)를 rclone 클라우드 원격에 미러해서 여러 컴퓨터에서 이어 쓰게 하는 배선. 전역 엔진은 `~/.claude/claude-sync.py`(이 repo의 `sync.py`가 배포)이고, 이 스킬은 그 위에 얹는 **프로젝트별 SessionEnd 훅 하나**만 만든다.

**저장은 자동, 당기기는 절대 자동이 아니다.** pull은 항상 사람이 확인하고 실행한다.

## 언제 쓰나

- 새 프로젝트 시작 + 여러 컴퓨터를 오갈 계획일 때
- "그 동기화 다시 세팅해줘" 류 요청
- 동기화 중인 프로젝트의 루트 경로가 바뀌었을 때 (아래 "루트 경로가 바뀌면")

## 전제

- **rclone 설치 + remote 설정** — 직접 업로드가 아니라 provider API 요청 방식이라 필수.
  `brew install rclone` / `sudo apt install rclone` / `winget install Rclone.Rclone` → `rclone config`
- **`~/.claude/claude-sync.py` 배포됨** — 이 repo에서 `python3 sync.py` 한 번.
- 원격 기본값은 `gdrive:claude-sync`, 프로젝트별 하위 경로는 `<remote>/<project-name>`.

## 절차

### 1. 입력 확정

- 프로젝트 절대경로 (`--repo`)
- rclone remote + base path (`--remote`, 기본 `gdrive:claude-sync`)
- 프로젝트 이름 (`--project-name`, 기본값 repo 폴더명) — 원격 하위 폴더명과 `~/.claude/sync-state/<이름>.json` 상태 파일명에 쓰인다. **다른 프로젝트와 같은 remote를 공유해도 서로 안 섞이고 안 지운다.**

### 2. 생성기 실행

```bash
python3 ~/.claude/skills/project-sync-setup/setup.py \
  --repo /path/to/new-project \
  --remote gdrive:claude-sync
```

이게 하는 일:

- `<repo>/.claude/hooks/session-end-sync.py` 생성 — SessionEnd(`prompt_input_exit`/`logout`/`other`)에서 `claude-sync.py push --detach` 호출. 분리 실행이라 즉시 복귀하고, 결과는 `~/.claude/sync-state/<project>.json`에 남아 상태줄이 읽는다. 세션 닫기가 업로드에 안 붙잡히고, 실패해도 나중에 보인다.
  - 원자적 락(`O_CREAT|O_EXCL`)으로 다중 세션 동시 종료 시 중복 push 방지.
  - 스로틀 10초 — 순간 버스트만 뭉치고 진짜 재종료는 안 막는다. 5분처럼 길게 잡으면 그 사이 대화가 안 담긴 채 넘어간다(이음길에서 실제로 지적된 문제).
- `<repo>/.claude/settings.local.json`에 SessionEnd 훅 등록. **주의: `hooks.SessionEnd` 키는 통째로 덮어쓴다** — 그 프로젝트에 다른 SessionEnd 훅이 이미 있으면 먼저 확인할 것. 나머지 키(`permissions` 등)는 보존된다.
- 예전 버전이 깔았던 SessionStart 훅(`session-start-check.py`)이 남아 있으면 파일과 등록을 함께 제거.

### 3. 확인

- `.git/info/exclude`에 `.claude/`가 있는지 확인(없으면 추가) — 프로젝트 로컬 훅·settings가 커밋되면 안 됨.
- 세션 하나 끄고 `~/.claude/sync-state/<project>.json`의 `push.state`가 `ok`인지 확인.
- `rclone lsd <remote>/<project>` 로 `sessions/` 생겼는지 확인.

## 일상 사용

```bash
python3 ~/.claude/claude-sync.py status --repo /path/to/project   # 원격이 더 새로운지
python3 ~/.claude/claude-sync.py pull   --repo /path/to/project   # 병합해서 당기기
```

push는 SessionEnd 훅이 알아서 한다. pull만 손으로. setup 때 `--project-name`을 기본값이 아닌 값으로 줬다면 status/pull에도 똑같이 줘야 한다.

**새 머신에서는 slug 디렉터리가 아직 없다.** 그 repo에서 Claude Code를 한 번 열어 `~/.claude/projects/<slug>/`가 생긴 뒤에 pull 할 것 (slug 인코딩은 비문서화라 역산하지 않는다).

머신마다 repo 경로가 다르면 `pull --new-repo-path <이 컴의 repo 경로>` — `private/`·`.ua/`가 내려앉을 위치를 지정한다.

## 동작 모델 (알아두면 디버깅이 쉬움)

- **원격 레이아웃**: `<remote>/<project>/sessions/` (대화 기록·memory), `.../private/`, `.../ua/`.
- **slug 정규화**: Claude Code는 *실제 작업 디렉터리*에서 slug을 뽑기 때문에 머신마다 slug이 다르다(`/home/kio/omok` vs `/Users/me/Development/omok`). 그래서 원격에는 slug별 폴더를 두지 않고 **단일 `sessions/`** 만 두고, repo 루트 경로를 `__CLAUDE_PROJECT_ROOT__` 토큰으로 치환해 저장한다. push는 로컬 경로 → 토큰, pull은 토큰 → 이 머신 경로. 양쪽 다 토큰이라 머신 간 checksum이 같아서 매 sync마다 재업로드되지 않는다.
- **slug 탐색은 이름이 아니라 기록된 `cwd` 기준**이다(`find_slugs`). jsonl 앞부분 40줄의 `cwd` 값이 repo 루트이거나 그 하위여야 잡힌다.
- **pull은 절대 덮어쓰지 않는다** — 원격을 로컬 temp에 stage → `claude_sync_merge`로 병합(append-only 증명된 것만 교체, 충돌은 `.incoming`으로 세이브, 삭제 없음).
- **push는 union**이다 — 원격 것을 먼저 받아 합친 뒤 올려서 다른 머신 세션을 안 지운다. 업로드 전 temp에 스냅샷하므로 라이브 transcript가 계속 append돼도 전송이 안 찢어진다.
- **`.ua/`(understand-anything 지식그래프)도 미러**한다 — 재생성 비용(전체 스캔 + LLM)이 커서 머신마다 다시 만들지 않는다.
- **`migrate`**: 예전 `projects/<slug>/` 레이아웃을 쓰던 프로젝트는 한 번만 `claude-sync.py migrate --repo PATH` → 결과 검증 후 `rclone purge <remote>/<project>/projects`.

## 루트 경로가 바뀌면 (rename·이사)

디렉터리 이름만 바꿔도 세 군데가 어긋난다. 전부 고쳐야 pull이 붙는다.

1. `<repo>/.claude/hooks/session-end-sync.py`의 `REPO_ROOT`·`PROJECT_NAME` 상수 — 하드코딩이라 자동으로 안 따라간다. `setup.py`를 새 경로로 다시 돌리는 게 제일 안전.
2. `<repo>/.claude/settings.local.json`의 훅 command 절대경로.
3. `~/.claude/projects/<옛 slug>/` 안의 `cwd` 문자열 — 옛 경로 그대로라 `find_slugs`가 새 루트를 못 찾고 `pull`이 `no local slug records <path>`로 죽는다. 두 가지 길:
   - **재시작**(권장, 안전): 새 경로에서 Claude Code를 한 번 열면 새 slug이 생긴다. 옛 slug의 기록은 아래 치환으로 나중에 합치면 된다.
   - **치환**: 옛 slug 디렉터리의 `*.jsonl`/`*.json` 안 옛 경로 → 새 경로로 문자열 치환 후 디렉터리를 새 slug 이름으로 rename. 세션 기록을 직접 건드리므로 **먼저 백업**할 것. 진행 중인 세션이 그 안에 있으면 재시작 전까지 기록 위치가 보장되지 않는다.

`~/.claude/sync-state/<옛이름>.json`은 남는다 — 이름을 바꿨으면 새 이름 파일이 따로 생기므로 옛 것은 지워도 된다.

## 알아둘 것 (실제로 겪은 함정)

- **훅 payload 필드명은 문서랑 다를 수 있다** — `SessionEnd`의 사유 필드는 문서상 `session_end_reason`이지만 실제로는 `reason`이었다(템플릿은 이미 `reason`). 다른 필드도 의심되면 훅에 `json.dump(payload, ...)` 한 줄 임시로 넣어 실측할 것.
- **`/tmp`는 훅 실행마다 격리될 수 있다** — 상태 파일(스로틀·마커)은 `$HOME` 밑에 둘 것(템플릿은 이미 그렇게 돼있음).
- **SessionStart 주입은 폐기했다** — `initialUserMessage`로 pull을 유도하던 훅은 `startup`에서만 뜨고(resume은 못 봄), 뜨면 새 세션의 첫 턴을 잡아먹었다. 지금 신호는 상태줄(`statusline.py`)에 있다 — 모든 세션에서 보이고 아무 턴도 안 뺏는다.
- **pull은 자동화하지 않는다** — "같은 컴퓨터에서 껐다 켠 것"일 수도 있어서 무조건 사람이 확인하고 실행.
- **`claude-export.py`/`claude-import.py`는 레거시**다 — 한 프로젝트를 `.tar.gz` 한 덩이로 옮기는 일회성 이관용. 일상 sync는 `claude-sync.py`.
- **네이티브 Windows slug 인코딩은 미검증** — POSIX·macOS는 실측 완료(절대경로의 `/ \ . : _` 를 `-` 로, 대소문자는 보존: `/Users/kio/Development/hisTour` → `-Users-kio-Development-hisTour`). 네이티브 Windows cwd(`C:\Users\..`)를 Claude Code가 어떻게 slug화하는지는 확인 안 됨 — Windows에서 처음 돌릴 때 `~/.claude/projects` 실제 폴더명과 대조할 것.
