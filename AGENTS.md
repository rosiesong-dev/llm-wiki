# llm-wiki Schema (위키 운영 규칙)

> Karpathy LLM-Wiki 패턴의 **세 번째 층(Schema)** 입니다. 이 저장소에서 위키를 쓰거나 고치는 LLM·에이전트·사람은 이 규칙을 따릅니다.
> 사람과 LLM이 함께 다듬는 문서이며, 규칙이 바뀌면 이 파일을 먼저 고칩니다.
> `AGENTS.md`는 Codex·Cursor·Gemini CLI 등 여러 에이전트가 읽는 공통 규칙 파일입니다. Claude Code는 `CLAUDE.md`의 `@AGENTS.md` 한 줄로 이 파일을 불러옵니다. **규칙은 이 파일에만 씁니다.**

## 1. 3개 층

| 층 | 위치 | 규칙 |
|---|---|---|
| ① Raw sources (원본) | `storage/raw/confluence/{스페이스 키}/`, `storage/raw/slack/{채널명}/` | **절대 수정하지 않는다.** 다시 수집할 때만 덮어쓴다 |
| ② Wiki (위키) | `storage/wiki/` | LLM이 쓰고 계속 고친다. 사람은 읽고 검토한다 |
| ③ Schema (규칙) | `AGENTS.md` (이 파일) | 위키 구조·작성 규칙·작업 순서 |

## 2. 페이지 종류 (Frontmatter `type`)

| type | 폴더 | 무엇을 쓰나 | 예 |
|---|---|---|---|
| `overview` | `overview/` | 전체를 한눈에 보는 시작 페이지 | 프로젝트 개요 |
| `synthesis` | `synthesis/` | 여러 원본을 엮은 현황·결론. 새 원본이 오면 갱신 | 프로젝트 진행 현황 |
| `entity` | `entities/` | 사람·팀·시스템·도구 (대상 1개 = 페이지 1개) | 홍길동, Jira, Kafka |
| `concept` | `concepts/` | 주제·용어·아이디어 | 메시지 큐, 목업 UI |
| `comparison` | `comparisons/` | 두 개 이상을 표로 비교 | Kafka vs RabbitMQ |
| `summary` | `summaries/{meetings,slack,issues,knowledge}/` | **원본 1개당 요약 1개** (회의록 1건, Slack 하루) | 2026-10-26 … 회의록, Slack #dev 2026-10-27 |

## 3. Frontmatter

```yaml
---
title: 홍길동                 # 페이지 이름 = [[링크]] 대상. 파일명도 이 값
type: entity                 # 위 6가지 중 하나 (필수)
category: meetings           # summary일 때만: meetings / slack / issues / knowledge
summary: 프로젝트 팀원. ...    # index.md에 쓰이는 한 줄 요약 (필수로 채운다)
tags: [person]
aliases: [U0XXXXXXXXX]       # 다른 이름 (Slack ID, 영문명, 계정명) - 링크·검색에 사용
source_id: confluence-4653163 # summary일 때 원본 ID
updated: '2026-10-27'         # 저장 시 자동
---
```

## 4. 링크 규칙
- 페이지끼리는 `[[페이지 제목]]`으로 연결한다. (Obsidian 호환)
- **요약 페이지** 끝에는 `## 관련 페이지`에 등장한 엔티티·개념·비교 페이지를 링크한다.
- **엔티티·개념 페이지**는 `## 출처별 내용` 아래 `### [[요약 페이지 제목]]` + 그 원본에서 알 수 있는 사실 불릿으로 근거를 남긴다.
- 없는 페이지로 링크하지 않는다. 필요하면 페이지를 먼저 만든다 (`lint`가 깨진 링크를 찾는다).

## 5. 특별한 파일 2개

| 파일 | 역할 | 규칙 |
|---|---|---|
| `storage/wiki/index.md` | 모든 페이지의 링크 + 한 줄 요약을 종류별로 정리한 목차 | **질문을 받으면 가장 먼저 읽는다.** 직접 고치지 않는다 (페이지 저장 시 자동 생성) |
| `storage/wiki/log.md` | 언제 무엇을 넣고(ingest), 묻고(query), 점검(lint)·수정(update)했는지 기록 | **덧붙이기만 한다.** 형식: `## [YYYY-MM-DD HH:MM] 작업 \| 제목` + 상세 불릿 |

## 6. 작업 순서

### Ingest (원본 넣기)
1. 원본을 `storage/raw/`에 수집한다 (`fetch-page`, `fetch-slack`)
2. 원본 1개당 **요약 페이지**를 만든다. 담당자·기한·숫자 같은 **표는 원문 그대로** 옮긴다
3. 등장한 엔티티·개념 페이지를 만들거나 `## 출처별 내용`에 사실을 추가한다
4. 관련 종합(synthesis) 페이지를 갱신한다 (결정 사항·할 일·미결 사항)
5. `index.md` 갱신 (자동), `log.md`에 `ingest` 기록 (자동)

### Query (묻기)
1. `index.md`를 먼저 읽고 관련 페이지를 고른다
2. 관련 페이지(RAG 검색 결과)를 읽고 `[[출처]]`와 함께 답한다
3. 다시 쓸 만한 답은 `--save comparison|synthesis|concept`으로 위키 페이지로 저장한다

### Lint (점검)
- 주기적으로 `python main.py lint` → 깨진 링크, 고아 페이지, 한 줄 요약 누락, 출처 없는 엔티티·개념
- 내용이 사실인지는 **사람이 원본과 대조해** 판단한다

## 7. 작성 원칙
- 원본에 없는 내용은 쓰지 않는다. 추정은 **추정**이라고 쓴다 (예: Slack ID → 이름 매핑)
- 소형 LLM(gemma3:4b) 요약은 오류가 잦다. 저장 전 원본과 대조하고, 틀린 곳은 고친 뒤 `log.md`에 `update`로 남긴다
- Slack 요약 페이지에는 `## 원문 대화`(원문 그대로)를 함께 둔다. LLM이 놓친 내용도 검색되게 하기 위해서다
- 자료는 `.env`의 `CONFLUENCE_SPACE_KEY` 스페이스에서 가져오고, 티켓은 `JIRA_PROJECT_KEY` 프로젝트에 발행한다
