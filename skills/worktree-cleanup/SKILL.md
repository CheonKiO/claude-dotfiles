---
name: worktree-cleanup
description: Use before running `git worktree remove` on any worktree — rescues gitignored content that exists only inside that worktree (plan docs, task reports, scratch notes) into the main tree before deletion. Use proactively whenever the user asks to clean up/remove a worktree, or when a worktree hasn't been touched in a while and looks abandoned.
---

# Worktree Cleanup

`git worktree remove`는 **gitignore된 파일은 그냥 통째로 날린다.** 워크트리 생성 시점에 gitignore된 디렉토리(`.superpowers/`, `private/`, `.env` 등)는 애초에 메인 트리에서 복사돼 오지도 않고, 그 워크트리 안에서 새로 만들어진 내용은 지울 때 아무데도 안 남는다. 실제로 이 프로젝트에서 서브에이전트 작업보고서(`.superpowers/sdd/.../task-N-report.md`)가 방치된 워크트리 안에만 있다가 하마터면 통째로 날아갈 뻔한 적이 있었다.

## 언제 쓰나

- `git worktree remove`를 실행하기 직전 — 예외 없이 항상
- 사용자가 "워크트리 정리해줘", "이거 지워도 되나" 물어볼 때
- 오래 방치된 워크트리를 우연히 발견했을 때(치우기 전에)

## 절차

### 1. 브랜치가 진짜로 다 반영됐는지 확인한다

```bash
git merge-base --is-ancestor <worktree-branch> origin/master && echo "머지됨" || echo "미머지"
git -C <worktree-path> status --short   # uncommitted 변경 있는지
```

**미머지 상태거나 uncommitted 변경이 있으면 여기서 멈춘다.** 지우지 말고 사용자에게 보여준다 — 그 브랜치에만 있는 고유 커밋일 수 있다.

브랜치가 "머지됨"으로 나와도 안심하지 않는다 — 같은 메시지로 다른 해시에 재커밋(리베이스/스쿼시)된 경우 `git merge-base --is-ancestor`가 false를 줄 수 있다. 그럴 땐 그 커밋의 실제 diff를 메인 트리의 동등한 파일과 직접 비교해서 내용이 진짜 반영됐는지 확인한다(커밋 해시 동일이 아니라 **내용 동등성**을 본다).

### 2. 그 워크트리에만 있는 gitignore 콘텐츠를 찾는다

```bash
cd <worktree-path>
git status --ignored=matching --porcelain=v1 | grep '^!!'
```

나온 각 경로에 대해, 메인 트리의 같은 경로와 비교한다:
- 메인 트리에 **아예 없는** 파일/디렉토리 → 유실 위험. 반드시 회수.
- 메인 트리에도 있지만 **내용이 다른** 파일 → 사용자에게 어느 쪽이 최신/맞는지 확인.

특히 자주 걸리는 것: `.superpowers/sdd/<plan-name>/task-*-report.md`(서브에이전트 작업보고서), `private/`(개인 스크래치 — [[8. Knowledge Propagation]] 참조), 워크트리 로컬로만 작성된 `.env`류.

### 3. 회수한다

```bash
cp -rn <worktree-path>/<gitignore-path> <main-repo>/<gitignore-path>
```

`-n`(no-clobber)으로 메인 트리 파일을 덮어쓰지 않는다 — 겹치면 수동으로 병합 판단.

### 4. 회수 다 됐으면 지운다

```bash
git worktree remove <worktree-path>
git worktree prune
git branch -D <worktree-branch>   # 다른 브랜치에 완전히 흡수됐을 때만
```

브랜치 삭제는 별도 판단이다 — 워크트리 삭제와 브랜치 삭제는 다른 작업이다. 브랜치의 고유 커밋이 메인 트리 어딘가에 내용까지 동등하게 존재함을 1단계에서 확인했을 때만 지운다.

## 실패 사례 (교훈)

- 워크트리 4개를 정리하면서 그 안에만 있던 `.superpowers/sdd/` 실행 원장(태스크 브리프·리포트·리뷰 diff)이 메인 워크스페이스에 없다는 걸 삭제 직전에 발견해서 겨우 회수함 — 한 단계만 늦었으면 유실됐다.
- 브랜치가 "머지된 것처럼 보이는" 워크트리에 실제로는 아무 브랜치에도 없는 고유 커밋이 남아 있던 사례 — 커밋 해시가 아니라 파일 내용을 직접 diff해서 확인해야 진짜 안전하다.
