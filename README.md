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
| 상태줄 | `statusline.py` | 프롬프트 하단 상태줄 |
| 플러그인 | `install-plugins.py` + `plugins.manifest.json` | 쓰는 플러그인 + 마켓플레이스 목록, 새 머신에서 재설치 |
| 세션 이관 | `claude-export.py` / `claude-import.py` | 한 프로젝트의 대화 기록 + 글로벌 설정을 `.tar.gz`로 묶어 다른 머신으로 옮김 |

### 훅 3종 (`hooks/`)

- **`file-size-guard.py`** — 파일이 500줄을 넘으면 경고 (god 파일 방지)
- **`git-fetch-guard.py`** — `origin/`을 참조하는 명령 전에 자동으로 `git fetch` (stale 참조 방지)
- **`notify.sh`** — Claude가 확인을 기다릴 때(권한 프롬프트·입력 대기) **OS별 네이티브 데스크톱 알림**을 띄움. 멀티세션에서 어느 세션이 멈췄는지 놓치지 않으려는 용도.
  - macOS → `osascript` 알림 / WSL·Windows → PowerShell WinRT 토스트(`-EncodedCommand`라 한글 안전) / Linux → `notify-send` / 그 외 → 터미널 벨
  - 제목에 **작업 폴더명 + git 브랜치**를 넣어 세션을 구분함 (예: `Claude Code · S15P11A107 (feature-branch)`)
  - 별도 설치 불필요(각 OS 기본 도구 사용)

---

## 동기화하지 않는 것 (의도적 제외)

머신마다 다르거나 인증/세션 상태가 들어 있어 **절대 올리지 않습니다**:

- `memory/`, `projects/` — 세션 대화 기록·자동 메모리 (머신 로컬)
- `settings.local.json` — 프로젝트별 개인 오버라이드
- `.credentials.json` — 로그인 토큰
- `plugins/cache/` — 플러그인 캐시
- `private/` — 개인 스테이징(gitignore)

`settings.json`은 통째로 덮어쓰지 않고, `sync.py`가 **훅·권한·상태줄 등록만 병합**합니다. 나머지 키(`enabledPlugins`, 개인 권한 등)는 그 머신 것 그대로 둡니다.

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
| `sync.py` | repo → `~/.claude` | 설정 설치. CLAUDE.md·스킬·훅·statusline 복사 + 훅/권한 병합 + 상태줄 등록 |
| `capture.py` | `~/.claude` → repo | 반대 방향. 로컬에서 직접 고친 설정을 저장소로 되끌어옴 (커밋 전에 실행). `memory/`·`projects/`·`credentials`는 안 건드림 |
| `install-plugins.py` | — | `plugins.manifest.json` 기준으로 마켓플레이스 추가 + 플러그인 설치 (`claude` CLI 구동, 멱등) |
| `claude-export.py` | — | 한 프로젝트의 세션 기록 + 글로벌 설정을 `.tar.gz`로 묶기 (토큰·타 프로젝트 제외) |
| `claude-import.py` | — | 위 아카이브를 이 머신 `~/.claude`에 풀기 |

훅·권한은 **스크립트 이름(basename)으로 관리**돼서, 다시 sync해도 이전 버전이 중복되지 않고 교체됩니다. 커밋된 훅 명령의 파이썬 인터프리터는 `__PY__` 토큰으로 저장돼, 설치할 때 그 OS의 인터프리터(`python3`/`python`/`py -3`)로 치환됩니다.

---

## 일상 워크플로

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
