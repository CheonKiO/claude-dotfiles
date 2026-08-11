---
name: live-contract-check
description: Use before writing code against an external API/vendor's documented response shape — makes a real live call first and diffs the actual response against the assumed field names/types/values. Use proactively whenever a new external API integration starts, or when a bug is suspected in how a DTO maps an external API's fields.
---

# Live Contract Check

외부 API를 문서만 보고 구현했다가 실제 응답과 달라서 터진 사고를 막기 위한 스킬. 이음길 프로젝트에서 ODsay `trafficType` 값이 문서와 실제가 뒤집혀 있던 것, TourAPI 페이지네이션이 예상과 다르게 부분수집되던 것 등 — 전부 "문서를 믿었다"에서 나왔다. AI는 특히 문서를 그대로 믿는 경향이 있어서, 이 절차를 명시적으로 강제할 필요가 있다.

## 언제 쓰나

- 새 외부 API 연동을 시작할 때 — DTO/엔티티를 코드로 옮기기 **전에** 먼저
- 기존 연동에서 "값이 이상하다"는 버그를 의심할 때
- 외부 API 문서가 오래됐거나 신뢰도가 낮다고 느껴질 때

이 프로젝트에 외부 API가 없으면 이 스킬은 그냥 안 쓴다.

## 절차

### 1. 실제 호출부터 한다

문서를 읽고 코드를 짜기 전에, `curl`이든 스크립트든 **실제로 호출**해서 원문 응답을 받는다. 인증키가 필요하면 사용자에게 테스트용 호출 1회 허가를 받는다(비용/쿼터가 있는 API라면).

### 2. 원문 덤프를 저장한다

받은 raw response를 그대로 파일로 남긴다(`docs/` 밖의 스크래치든 어디든). 나중에 "이게 진짜 그렇게 왔었나?"를 재확인할 근거가 된다.

### 3. 문서와 실제를 필드 단위로 대조한다

표로 만든다:

```
| 필드 | 문서상 타입/의미 | 실제 관측값 | 일치? |
|---|---|---|---|
| trafficType | enum, 문서 순서 그대로 | 실제로는 순서가 다름 | ❌ |
```

특히 다음을 의심해서 본다:
- enum/코드값의 실제 매핑 순서
- 페이지네이션 — 전체 건수 대비 실제로 다 도는지(부분수집 여부)
- null/누락 가능성이 문서에 안 적힌 필드
- 소수점/문자열/숫자 타입이 문서와 다르게 오는 경우(가격 필드가 특히 잘 이런다)
- 배열의 "첫 항목이 기본값"이라는 암묵적 가정이 실제로 맞는지

### 4. 불일치를 코드에 방어로 남긴다

발견한 불일치는 주석으로 "왜 이렇게 처리하는지" 근거를 남긴다 — 나중에 누가 "왜 이상하게 짜여있지"하고 되돌리지 않도록.

```
// 실측: trafficType 7 = 항공 (문서 순서와 다름, 2026-08-04 curl 634회로 확인)
```

### 5. 구현 전 게이트로 쓸 것

계획서에 "Task 1 = 실측 게이트"라고 써놓고 검증 없이 뒤 설계·구현을 다 진행하는 실수를 하지 않는다 — 게이트라고 적었으면 실제로 그 결과가 나오기 전엔 뒤 태스크를 시작하지 않는다.

## 실패 사례 (교훈)

- "문서를 민었다"에서 나온 사고: enum 순서 뒤집힘, 페이지네이션 부분수집, 가격 필드 타입 불일치.
- 계획서에 실측 게이트를 명시했으면서도 실제로는 안 지키고 앞서나간 사례 — 게이트는 문서화가 아니라 강제되는 순서여야 한다.
