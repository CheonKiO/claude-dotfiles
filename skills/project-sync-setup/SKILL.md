---
name: project-sync-setup
description: Use when turning on cross-machine Claude Code continuity for a project — the SessionEnd push is now a single global hook gated by an allowlist, so onboarding a project is one line in ~/.claude/sync-projects.json, not a per-project hook install. Use when the user says they'll switch computers on a new project, asks to set up "그 동기화" for a repo, or renames/moves a synced project's root.
---

# Project Sync Setup

한 프로젝트의 Claude Code 상태(대화 기록·memory·`private/`·`.ua/`)를 rclone 클라우드 원격에 미러해서 여러 컴퓨터에서 이어 쓰게 하는 배선.

**핵심 변경 (2026-08-18):** 예전엔 프로젝트마다 `.claude/hooks/session-end-sync.py`를 복사·하드코딩하고 그 프로젝트 `settings.local.json`에 SessionEnd를 배선했다. 지금은 **전역 훅 하나**(`~/.claude/hooks/session-end-sync.py`, 전역 `settings.json`에 등록)가 모든 프로젝트를 담당하고, **어느 프로젝트를 켤지는 allowlist `~/.claude/sync-projects.json`** 한 곳에서 정한다. 새 프로젝트 = 목록에 한 줄.

**저장은 자동, 당기기는 절대 자동이 아니다.** pull은 항상 사람이 확인하고 실행한다.

## 동작 방식

전역 훅이 SessionEnd(`prompt_input_exit`/`logout`/`other`)마다:

1. payload의 `cwd`에서 **위로 올라가며 basename이 allowlist에 있는 첫 조상 디렉토리**를 찾는다 = 프로젝트 루트 + 이름. 없으면 그냥 no-op.
   - **git top-level이 아니라 allowlist 조상으로 유도하는 게 의도적이다.** `/home/kio/omok`처럼 루트가 **여러 독립 git repo(omok-back, omok-front)를 담는 컨테이너**면 `git rev-parse`는 서브repo를 잘못 집는다. sync 단위는 allowlist에 적힌 컨테이너다.
2. 매칭되면 `claude-sync.py push --detach` 호출. 분리 실행이라 즉시 복귀, 결과는 `~/.claude/sync-state/<project>.json`에 남아 상태줄이 읽는다.
3. 프로젝트명 기준 원자적 스로틀 10초 — 다중 탭 동시 종료 버스트만 뭉친다.

## 전제

- **rclone 설치 + remote 설정** — `brew/apt/winget install rclone` → `rclone config`. 원격 기본값 `gdrive:claude-sync`, 프로젝트별 하위 `<remote>/<project>`.
- **이 repo 배포됨** — `python3 sync.py` 한 번이면 `claude-sync.py`·전역 훅·`sync-projects.json`·settings 등록이 다 깔린다.

## 절차 (새 프로젝트 켜기)

### 1. allowlist에 이름 추가

이 dotfiles repo의 `sync-projects.json`에 **프로젝트 폴더명**(원격 하위 폴더·상태파일명에도 쓰임)을 한 줄 추가. 하위에 여러 repo를 담는 컨테이너면 **컨테이너 폴더명**을 넣는다(예: `omok`, 서브 `omok-front` 아님).

### 2. 배포

```bash
python3 sync.py           # 이 머신 ~/.claude에 반영
```

커밋해서 push하면 다른 머신은 각자 `python3 sync.py`로 받는다. (allowlist는 dotfiles가 소유 — 편집은 여기서, 배포는 sync.py.)

### 3. 확인

```bash
# 배선됐는지 (실제 push 없이 판정만)
echo '{"cwd":"/path/into/project","reason":"other"}' \
  | CLAUDE_SYNC_DRYRUN=1 python3 ~/.claude/hooks/session-end-sync.py
# -> [dryrun] cwd=... -> ('/repo/root', 'project')  이면 OK. -> None 이면 목록/경로 확인.
```

- 세션 하나 끄고 `~/.claude/sync-state/<project>.json`의 `push.state`가 `ok`인지.
- `rclone lsd <remote>/<project>` 로 `sessions/` 생겼는지.
- 프로젝트 `.claude/`가 `.git/info/exclude`에 있는지(로컬 settings가 커밋되면 안 됨).

## 일상 사용

```bash
python3 ~/.claude/claude-sync.py status --repo /path/to/project   # 원격이 더 새로운지
python3 ~/.claude/claude-sync.py pull   --repo /path/to/project   # 병합해서 당기기
```

push는 전역 훅이 알아서. pull만 손으로.

- **새 머신엔 slug 디렉터리가 아직 없다.** 그 repo에서 Claude를 한 번 열어 `~/.claude/projects/<slug>/`가 생긴 뒤 pull.
- 머신마다 repo 경로가 다르면 `pull --new-repo-path <이 컴 경로>` (`private/`·`.ua/` 착지 위치).
- `pull --force` = "up to date 빠른 경로"를 무시하고 무조건 병합.

## 성능 (2026-08-18 개선)

- **영구 캐시**: pull/push가 rclone 다운로드를 빈 tempdir 대신 `~/.claude/sync-cache/<project>/`에 미러 → `--checksum`이 변경분만 전송(예전엔 매 sync마다 원격 전체 재다운로드).
- **조기종료**: pull이 `remote_newest <= seen` && 캐시 존재면 copy/merge 통째 스킵.
- **`--fast-list`/`--checkers`** + `.incoming-*` 전송 제외(충돌본이 다른 머신에 전파 안 됨).
- 남은 병목 = 공유 rclone client_id throttle → 자기 client_id 발급이 다음 레버(코드 아님, `rclone config`).

## 동작 모델 (디버깅용)

- **원격 레이아웃**: `<remote>/<project>/{sessions,private,ua}`.
- **slug 정규화**: 머신마다 slug이 달라서(`/home/kio/omok` vs `/Users/me/Development/omok`) 원격엔 slug 폴더를 안 두고 단일 `sessions/`에 repo 루트를 `__CLAUDE_PROJECT_ROOT__` 토큰으로 치환해 저장. push=로컬→토큰, pull=토큰→이 머신. 양쪽 토큰이라 checksum 동일.
- **slug 탐색은 기록된 `cwd` 기준**(`find_slugs`) — jsonl 앞 40줄 `cwd`가 repo 루트이거나 하위여야 잡힘.
- **pull은 안 덮어씀** — 캐시→scratch stage→`claude_sync_merge` 병합(append-only 증명된 것만 교체, 충돌은 `.incoming`, 삭제 없음).
- **push는 union** — 원격을 먼저 받아 합쳐 올려 다른 머신 세션 안 지움.
- **`migrate`**: 예전 `projects/<slug>/` 레이아웃은 한 번 `claude-sync.py migrate --repo PATH` → 검증 후 `rclone purge <remote>/<project>/projects`.

## 루트 경로가 바뀌면 (rename·이사)

전역 훅은 이제 하드코딩 상수가 없어서 **훅/settings는 손댈 필요 없다.** 두 가지만:

1. `sync-projects.json`의 이름을 새 폴더명으로 바꾸고 `sync.py` 재실행(이름이 곧 원격 폴더·상태파일명이라, 원격도 바꾸려면 `rclone` 이동 별도).
2. `~/.claude/projects/<옛 slug>/` 안 `cwd` 문자열이 옛 경로라 `find_slugs`가 못 찾아 `pull`이 `no local slug records`로 죽는다.
   - **재시작(권장)**: 새 경로에서 Claude 한 번 열면 새 slug 생김.
   - **치환**: 옛 slug의 `*.jsonl`/`*.json` 경로 문자열 치환 후 디렉터리 rename. **먼저 백업**.

## 알아둘 것 (실제로 겪은 함정)

- **훅 payload 사유 필드는 `reason`** (문서상 `session_end_reason`과 다름 — 실측 완료). 의심되면 `CLAUDE_SYNC_DRYRUN=1`로 판정 경로 찍어볼 것.
- **`/tmp`는 훅 실행마다 격리될 수 있다** — 상태·스로틀 파일은 `$HOME` 밑(그렇게 돼있음).
- **allowlist는 basename 매칭** — 같은 이름 폴더가 다른 위치에 있으면 오탐 가능(사용자가 이름 관리).
- **SessionStart 주입은 폐기** — pull 유도 신호는 상태줄(`statusline.py`)에 있다. 모든 세션에서 보이고 턴을 안 뺏는다.
- **마이그레이션 잔재**: 예전 머신의 프로젝트별 `.claude/hooks/session-end-sync.py` + `settings.local.json` SessionEnd는 스로틀이 프로젝트명 기준이라 전역 훅과 겹쳐도 이중 push는 안 되지만, 스테일 등록이 삭제된 파일을 가리키면 에러난다. 각 머신에서 `sync.py`로 전역 훅 받은 뒤 프로젝트별 것을 제거할 것.
- **`claude-export.py`/`claude-import.py`는 레거시** — `.tar.gz` 일회성 이관용. 일상은 `claude-sync.py`.
