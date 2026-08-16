# claude-dotfiles

여러 대의 컴퓨터(맥·윈도우·WSL)에서 **Claude Code 개인 설정을 똑같이 맞춰 쓰기 위한** dotfiles 저장소입니다.
행동 지침(CLAUDE.md), 스킬, 훅, 상태줄, 권한 허용목록, 플러그인 목록을 한곳에 모아 두고,
새 컴퓨터에서 `git clone` → `python3 sync.py` 한 번으로 그대로 재현합니다.

`python3`만 있으면 되고(표준 라이브러리만 사용), OS에 상관없이 동작합니다.

---

## 무엇이 동기화되나

| 항목 | 파일/폴더 | 설명 |
|---|---|---|
| 행동 지침 | `CLAUDE.md` | 세션 시작 시 항상 로드되는 개인 규칙. 매턴 적용되는 것만 인라인, 특수 상황용은 아래 `rules/`·스킬로 분리 |
| 상황별 규칙 | `rules/` | 특수 상황에서만 읽는 참조 문서 — `knowledge-propagation`(문서 배치·완료 기록), `doc-review`(긴 문서 리뷰), `git-hygiene`(머지·리베이스·브랜치 정리). CLAUDE.md 상단 포인터 표로 트리거 |
| 스킬 | `skills/` | `delegation-tiering`, `full-review`, `live-contract-check`, `project-sync-setup`, `wip-then-squash`, `worktree-cleanup` |
| 훅 | `hooks/` | 아래 3종 (파일) + `hooks.settings.json`(등록 정보) |
| 권한 허용목록 | `permissions.settings.json` | 매번 물어보지 않아도 되는 안전한 명령 allowlist (읽기 전용 도구·gradle 등) |
| 일반 설정 | `general.settings.json` | 머신마다 달라지면 안 되는 정책 키를 **강제 덮어쓰기**. 현재 `cleanupPeriodDays: 36500` — 기본값 30일이 startup 스윕에서 세션 기록 ~73M을 복구 불가로 삭제한 사고(2026-08-16) 이후 고정 |
| 상태줄 | `statusline.py` | 프롬프트 하단 상태줄. context %·비용·rate limit + **프로젝트 세션 sync 신호**(`올리는중`/`실패`/`새 기록`) 표시 |
| 플러그인 | `install-plugins.py` + `plugins.manifest.json` | 쓰는 플러그인 + 마켓플레이스 목록, 새 머신에서 재설치 |
| 프로젝트 세션 sync | `claude-sync.py` + `claude_sync_merge.py` | 한 프로젝트의 대화 기록·메모리를 rclone으로 클라우드 원격에 미러. 아래 [프로젝트 세션 동기화](#프로젝트-세션-동기화-rclone) 참고 |
| 세션 이관 (레거시) | `claude-export.py` / `claude-import.py` | 한 프로젝트를 `.tar.gz` 한 덩이로 묶어 옮기는 일회성 이관. 일상 sync는 위 `claude-sync.py`가 대체 |

### 글로벌 훅 3종 (`hooks/`)

모든 프로젝트에 걸리는 훅. (프로젝트별 세션 sync 훅은 별도 — [프로젝트 세션 동기화](#프로젝트-세션-동기화-rclone) 참고.)

- **`file-size-guard.py`** — 파일이 500줄을 넘으면 경고 (god 파일 방지)
- **`git-fetch-guard.py`** — `origin/`을 참조하는 명령 전에 자동으로 `git fetch` (stale 참조 방지)
- **`notify.sh`** — Claude가 확인을 기다릴 때(권한 프롬프트·입력 대기) **OS별 네이티브 데스크톱 알림**을 띄움. 멀티세션에서 어느 세션이 멈췄는지 놓치지 않으려는 용도.
  - macOS → `osascript` 알림 / WSL·Windows → PowerShell WinRT 토스트(`-EncodedCommand`라 한글 안전) / Linux → `notify-send` / 그 외 → 터미널 벨
  - 제목에 **작업 폴더명 + git 브랜치**를 넣어 세션을 구분함 (예: `Claude Code · S15P11A107 (feature-branch)`)
  - 별도 설치 불필요(각 OS 기본 도구 사용)

---

## 프로젝트 세션 동기화 (rclone)

**글로벌 config**(위 전부)는 git으로 옮기지만, **한 프로젝트의 대화 기록·메모리**는 git에 안 올림(머신 로컬·용량 큼). 이건 `claude-sync.py`가 클라우드 원격에 미러함.

### 왜 rclone인가 — 예전 방식과 뭐가 다른가

예전엔 SessionEnd 훅이 `.tar.gz`를 **Google Drive 동기화 폴더에 떨궜음**. 파일이 로컬 디스크에 닿는 순간 훅은 "성공" 반환 — 실제 업로드는 Drive 데스크톱 클라이언트가 자기 스케줄대로 나중에. 랩탑 먼저 닫으면 안 보내진 채 다른 머신 도착. 이 셋업 존재 이유 자체를 못 지킴.

이제 `claude-sync.py`가 **rclone으로 provider API에 직접 요청**함:

- **push는 bytes가 원격에 ACK돼야 성공 반환** — lazy Drive 클라이언트 레이스 제거.
- **tar.gz 폐기, 평범한 디렉토리를 `--checksum`으로 미러** — 바뀐 파일만 전송(gzip은 1바이트 수정에도 전체가 달라져 매번 전량 재업로드였음). mtime은 못 믿어서(머신 간 복사 시 리셋됨) 내용 해시로 비교.
- **아카이브 없음 → 100MB 상한 없음, 타 머신 복사본 pruning 없음.** 67M transcript도 무문제.
- **업로드 전 temp로 스냅샷** — 라이브 transcript가 계속 append돼서 rclone 해시 재검증 시 "md5 differ" 나던 것 방지. 소스가 전송 중 안 변함.

### 훅: SessionEnd 하나만 (SessionStart 제거)

`project-sync-setup` 스킬의 `setup.py`가 프로젝트 `.claude/`에 SessionEnd 훅 하나만 깖:

- **트리거**: `prompt_input_exit|logout|other` (진짜 작업 종료 신호만), cwd가 repo 하위일 때만.
- **동작**: `claude-sync.py push --detach` — 분리 실행 0.04s 복귀, 결과는 `~/.claude/sync-state/<project>.json`에 기록. 세션 닫기가 업로드에 안 붙잡히고, 실패해도 나중에 보임.
- **throttle 파일**: 멀티탭 동시 close 버스트를 10초로 합쳐 push 한 번만.
- **SessionStart nudge 훅은 삭제됨** — `startup`에만 발화라 resume 땐 못 봤고, 발화하면 새 세션 첫 턴을 잡아먹었음. 이제 그 신호는 **상태줄**이 상시 운반(`올리는중`/`실패`/`새 기록`), 어떤 세션도 방해 안 함. 상태줄은 캐시 파일만 읽고(네트워크 X) 10분 지나면 백그라운드로 원격 재확인.

### pull은 항상 수동 (merge 기반)

저장은 자동, **당기기는 절대 자동 아님**. 당길 땐 원격을 로컬에 stage 후 `claude_sync_merge`로 병합:

- 로컬에 없는 파일 → 복사.
- append로 늘어난 transcript → **로컬 바이트가 원격의 prefix일 때만** 교체(append-only라 prefix면 superset 증명).
- 로컬이 더 길거나 갈라짐 → 안 건드리고 원격본을 `.incoming-<stamp>`로 옆에 둠.
- `MEMORY.md`는 양쪽서 편집되는 줄 단위 인덱스 → 줄 union.
- **로컬은 절대 삭제 안 함.**

```bash
python3 ~/.claude/claude-sync.py status --repo /path/to/project   # 원격이 더 새로운지 확인
python3 ~/.claude/claude-sync.py pull   --repo /path/to/project   # 병합해서 당기기
#   새 머신서 경로 다르면: --new-repo-path /new/path
```

### 준비물 (새 머신)

- **rclone 설치** — 직접 업로드가 아니라 API 요청 방식이라 필수.
  - macOS `brew install rclone` / Linux `sudo apt install rclone` 또는 `curl https://rclone.org/install.sh | sudo bash` / Windows `winget install Rclone.Rclone`
- **원격 설정** — `rclone config`로 Google Drive 등 remote 하나 잡기(기본 이름 `gdrive:claude-sync`).
- 프로젝트에 훅 설치: `python3 skills/project-sync-setup/setup.py --repo /path/to/project [--remote gdrive:claude-sync]`

---

## 동기화하지 않는 것 (의도적 제외)

머신마다 다르거나 인증/세션 상태가 들어 있어 **절대 올리지 않습니다**:

- `memory/`, `projects/` — 세션 대화 기록·자동 메모리 (머신 로컬)
- `settings.local.json` — 프로젝트별 개인 오버라이드
- `.credentials.json` — 로그인 토큰
- `plugins/cache/` — 플러그인 캐시
- `private/` — 개인 스테이징(gitignore)

`settings.json`은 통째로 덮어쓰지 않고, `sync.py`가 **훅·권한·상태줄 등록 병합 + `general.settings.json`의 정책 키 강제 덮어쓰기**만 합니다. 나머지 키(`enabledPlugins`, 개인 권한 등)는 그 머신 것 그대로 둡니다.

> `general.settings.json`의 `cleanupPeriodDays`만 예외적으로 **fill-if-absent가 아니라 덮어쓰기**입니다 — 잘못된 값(기본 30일)에 앉아 있는 머신을 교정해야 하기 때문. 30일 기본값이 startup 스윕에서 세션 기록 ~73M을 복구 불가로 지운 사고(2026-08-16)를 막으려는 것.

---

## 빠른 시작 (새 컴퓨터)

```bash
git clone https://github.com/CheonKiO/claude-dotfiles.git
cd claude-dotfiles
python3 sync.py            # 설정을 ~/.claude 에 설치
python3 install-plugins.py # (선택) 플러그인까지 재설치
```

`sync.py`는 **몇 번을 돌려도 안전(멱등)**합니다 — 파일을 그대로 복사하고, 훅/권한 등록을 중복 없이 병합하며, `settings.json`의 다른 키는 건드리지 않습니다. `git pull` 후 다시 돌리면 변경분만 반영됩니다.

> 알림 훅은 `settings.json` 워처가 **세션 시작 시점** 기준이라, 이미 켜 둔 Claude 세션에는 `/hooks`를 한 번 열거나 재시작해야 적용됩니다. 새로 여는 세션부터는 자동.

---

## 스크립트 정리

| 스크립트 | 방향 | 하는 일 |
|---|---|---|
| `sync.py` | repo → `~/.claude` | 설정 설치. CLAUDE.md·스킬·훅·statusline·`claude-sync.py` 복사 + 훅/권한/일반설정 병합 + 상태줄 등록 |
| `capture.py` | `~/.claude` → repo | 반대 방향. 로컬에서 직접 고친 설정을 저장소로 되끌어옴 (커밋 전에 실행). `memory/`·`projects/`·`credentials`는 안 건드림 |
| `install-plugins.py` | — | `plugins.manifest.json` 기준으로 마켓플레이스 추가 + 플러그인 설치 (`claude` CLI 구동, 멱등) |
| `claude-sync.py` | 프로젝트 ↔ rclone 원격 | **일상 세션 sync.** `push`/`pull`/`status`/`refresh`. push는 SessionEnd 훅이 `--detach`로 자동 호출, pull은 수동·merge 기반 |
| `claude_sync_merge.py` | — | `claude-sync.py pull`·`claude-import.py`가 공유하는 병합 로직 (prefix 증명 후 교체, 충돌은 `.incoming`으로 세이브, 삭제 없음) |
| `claude-export.py` (레거시) | — | 한 프로젝트를 `.tar.gz` 한 덩이로 묶기 (일회성 이관용, 토큰·타 프로젝트 제외). 일상은 `claude-sync.py` |
| `claude-import.py` (레거시) | — | 위 아카이브를 이 머신 `~/.claude`에 병합해 풀기 (`claude_sync_merge` 사용, 추출 폴더서도 실행 가능) |

훅·권한은 **스크립트 이름(basename)으로 관리**돼서, 다시 sync해도 이전 버전이 중복되지 않고 교체됩니다. 커밋된 훅 명령의 파이썬 인터프리터는 `__PY__` 토큰으로 저장돼, 설치할 때 그 OS의 인터프리터(`python3`/`python`/`py -3`)로 치환됩니다.

---

## 일상 워크플로

> 여긴 **글로벌 config**(CLAUDE.md·스킬·훅 등) 흐름. **프로젝트 세션 기록**은 git 아니라 `claude-sync.py`로 오감 — [프로젝트 세션 동기화](#프로젝트-세션-동기화-rclone) 참고.

편집은 아무 머신에서나 (`~/.claude/` 밑에서 직접 고치든, 이 저장소에서 고치든 — 같은 파일):

```bash
# 로컬(~/.claude)에서 직접 고쳤다면, 저장소로 되끌어오기
python3 capture.py

# 검토 후 커밋 + 푸시
git diff
git add -A && git commit -m "..." && git push

# 다른 머신에서
git pull && python3 sync.py
```

`~/.claude` 밑을 직접 고쳤으면 커밋 전에 `capture.py`를 꼭 돌려야 저장소에 반영됩니다(안 그러면 로컬 변경이 저장소에 안 담김).
