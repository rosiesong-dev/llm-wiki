# 📚 사내 llm-wiki: Confluence/Slack 회의 내용 수집·분석 및 Jira Ticket 생성

> **팀의 분산된 업무 지식과 이슈를 하나로 통합하고, Gemini AI or Gemma AI 지식 증강(RAG)을 통해 티켓 발행까지 원스톱으로 자동화하는 Python 기반 엔터프라이즈 지식 시스템**

---

## 📌 1. 프로젝트 개요 (Overview)

**llm-wiki**는 Andrej Karpathy가 제안한 **[LLM-Wiki 패턴](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)**을 사내 환경에 적용한 지식 시스템입니다.

> *"The knowledge is compiled once and then kept current, not re-derived on every query."*
> 지식은 **한 번 정리해 두고 계속 최신으로 유지**한다. 질문할 때마다 원본을 다시 뒤지지 않는다.

사내 **Confluence 회의록**과 **Slack 대화**를 원본으로 모으고, LLM(Gemini / Gemma)이 이를 읽어 **서로 링크로 연결된 Markdown 위키**를 쓰고 계속 고칩니다. 쌓인 위키로 질문에 답하고(Q&A), **Jira 티켓**까지 발행합니다.

| 기존 RAG | llm-wiki (LLM-Wiki) |
|---|---|
| 질문할 때마다 원본 조각을 검색 | 원본이 들어올 때 **미리 정리** (요약·엔티티·개념·종합) |
| 지식이 쌓이지 않음 | 좋은 답변도 **위키 페이지로 다시 저장** |
| 벡터는 사람이 못 읽음 | 사람이 그대로 읽고 고칠 수 있는 Markdown (Obsidian 호환 `[[링크]]`) |

---

## 🏗️ 2. LLM-Wiki 구조

### 2.1 3개 층

```
┌──────────────────────────────────────────────────────────────┐
│ ③ Schema   AGENTS.md                위키 구조·작성 규칙·작업 순서     │  ← 사람 + LLM이 함께 다듬음
├──────────────────────────────────────────────────────────────┤
│ ② Wiki     storage/wiki/            LLM이 쓰고 계속 고치는 위키       │  ← LLM이 씀, 사람은 읽고 검토
│            index.md · log.md · overview · synthesis ·         │
│            entities · concepts · comparisons · summaries      │
├──────────────────────────────────────────────────────────────┤
│ ① Raw      storage/raw/confluence/{스페이스}/  raw/slack/{채널}/ │  ← 수집만, 절대 수정 안 함
└──────────────────────────────────────────────────────────────┘
```

| 층 | 위치 | 누가 쓰나 | 규칙 |
|---|---|---|---|
| ① **Raw sources** | `storage/raw/` | 수집기 (`fetch-page`, `fetch-slack`) | **불변.** 위키가 틀려도 원본에서 다시 만들 수 있게 |
| ② **Wiki** | `storage/wiki/` | **LLM** (+ 사람 검토) | 아래 6가지 페이지 종류, `[[링크]]`로 연결 |
| ③ **Schema** | [`AGENTS.md`](AGENTS.md) | 사람 + LLM | 모든 에이전트(Codex·Cursor·Gemini CLI 등)가 읽는 위키 운영 규칙. Claude Code는 `CLAUDE.md`의 `@AGENTS.md`로 불러옴 |

### 2.2 위키 페이지 종류 (Frontmatter `type`)

| type | 폴더 | 내용 | 예 |
|---|---|---|---|
| `overview` | `overview/` | 전체를 한눈에 보는 **시작 페이지** | 프로젝트 개요 |
| `synthesis` | `synthesis/` | 여러 원본을 엮은 **현황·결론** (결정·할 일·미결) | 프로젝트 진행 현황 |
| `entity` | `entities/` | **사람·팀·시스템·도구** 대상별 페이지 | 홍길동, 김철수, Jira, Kafka |
| `concept` | `concepts/` | **주제·용어·아이디어** | 메시지 큐, 목업 UI, 소프트웨어 팩토리 |
| `comparison` | `comparisons/` | 두 개 이상을 **표로 비교** | Kafka vs RabbitMQ, Confluence vs Notion |
| `summary` | `summaries/{meetings,slack,issues,knowledge}/` | **원본 1개당 요약 1개** | 2026-10-26 회의록, Slack #dev 2026-10-27 |

### 2.3 페이지는 링크로 서로 연결된다

```
            [[프로젝트 개요]] (overview)
                 │                 │
       [[프로젝트 진행 현황]]     [[홍길동]] (entity) ──── [[메시지 큐]] (concept)
          (synthesis)              │  ## 출처별 내용          │
                 │                 │  ### [[2026-10-26 … 회의록]]
                 ▼                 ▼                          ▼
     [[2026-10-26 … 회의록]] (summary) ── ## 관련 페이지 ── [[Kafka vs RabbitMQ]] (comparison)
```

| 방향 | 규칙 |
|---|---|
| 요약 → 엔티티·개념 | 요약 페이지 끝 `## 관련 페이지`에 등장한 대상을 `[[링크]]` |
| 엔티티·개념 → 요약 | `## 출처별 내용` 아래 `### [[요약 제목]]` + 그 원본에서 알 수 있는 사실 (근거 추적) |
| 개요·종합 → 전체 | 본문 표·문장 안에서 `[[링크]]` |
| 별칭 | Frontmatter `aliases`(Slack ID, 영문명 등)로도 같은 페이지를 찾음 |

### 2.4 특별한 파일 2개

| 파일 | 성격 | 내용 | 용도 |
|---|---|---|---|
| **`storage/wiki/index.md`** | **내용 중심** 목차 | 모든 페이지의 `[[링크]]` + 한 줄 요약, **종류별** 정리 | **LLM이 질문을 받으면 가장 먼저 읽는다** (`ask`가 자동으로 함께 전달). 페이지 저장 시 자동 갱신 |
| **`storage/wiki/log.md`** | **시간 중심** 기록 | 언제 무엇을 넣고(ingest), 묻고(query), 점검(lint)·수정(update)했는지 | 작업 이력 추적, 최근 변경 확인. **덧붙이기만 함** |

`log.md` 형식과 최근 기록 보기:
```markdown
## [2026-10-27 09:31] ingest | 2026-10-26 결제 큐 아키텍처 회의록
- 원본: Confluence DEV/1001
- 새 페이지: [[홍길동]], [[메시지 큐]]
## [2026-10-27 14:40] query | 다음 회의는 누가 잡기로 했어?
## [2026-10-27 14:45] lint | 구조 점검 - 문제 5건
```
```powershell
Select-String -Path storage\wiki\log.md -Pattern '^## \[' | Select-Object -Last 5   # 최근 5개 작업
```

### 2.5 세 가지 동작

| 동작 | 명령 | 하는 일 |
|---|---|---|
| **Ingest** (넣기) | `fetch-page <ID>`, `build-wiki`, `fetch-slack` → `build-slack-wiki` | ① 원본 수집 → ② **요약 페이지** 작성 → ③ 등장한 **엔티티·개념 페이지 생성/갱신 + 양방향 링크** → ④ `index.md` 갱신 → ⑤ `log.md` 기록 |
| **Query** (묻기) | `ask "질문"` (`--save comparison` 등) | ① **`index.md` 먼저 읽기** → ② RAG로 관련 페이지 검색 → ③ `[[출처]]`와 함께 답변 → ④ (선택) **답변을 위키 페이지로 저장** → ⑤ `log.md` 기록 |
| **Lint** (점검) | `lint` | 깨진 링크, 고아 페이지(들어오는 링크 없음), 한 줄 요약 누락, 출처 없는 엔티티·개념 → `log.md` 기록 |

```
        ┌──────────── Ingest ────────────┐
 원본 ──▶│ 요약 · 엔티티/개념 갱신 · 링크 · 기록 │──▶ 위키 ◀──┐
        └────────────────────────────────┘     │       │ 좋은 답변 저장 (--save)
 질문 ──▶ Query (index.md → 관련 페이지) ──▶ 답변 ─┘       │
 주기적 ──▶ Lint ──▶ 문제 목록 ──▶ 수정(update) ─────────────┘
```

> [!WARNING]
> 엔티티·개념 자동 추출은 LLM이 이름과 사실만 뽑고, 페이지 생성·링크는 코드가 합니다. **원문에 실제로 없는 이름은 버립니다** (소형 모델 환각 방지).
> 그래도 gemma3:4b 요약은 사실 오류가 잦으므로, 저장된 요약은 원본과 대조해 검토하고 고친 내용은 `log.md`에 `update`로 남깁니다. 표(담당·기한)는 원문 그대로 옮기는 것을 원칙으로 합니다.

### 2.6 시스템 흐름

```
[Confluence 회의록] ────┐
                        ├─(수집)─▶ storage/raw/ (불변) ─(LLM Ingest)─▶ storage/wiki/ ─(임베딩)─▶ storage/index/
[Slack #dev] ────┘                                               │ index.md · log.md
                                                                        ▼
                         [Jira 티켓 발행]    ◀─(티켓 초안)─ [Query: index.md + RAG 검색 + LLM 답변]
```

---

## 📂 3. 프로젝트 폴더 구조

```text
llm-wiki/
├── .venv/                        # Python 가상환경
├── requirements.txt              # 의존성 패키지 목록 (requests, pydantic, numpy, rich, keyring, mcp 등)
├── .env.example                  # API 키 및 환경변수 템플릿
├── .env                          # 로컬 실행 환경변수 (Git 제외)
├── main.py                       # CLI 진입점 래퍼 스크립트
├── README.md                     # 시스템 종합 가이드 문서
├── AGENTS.md                     # ③ Schema: 위키 운영 규칙 (에이전트 공통, 규칙은 여기에만 작성)
├── CLAUDE.md                     #   Claude Code용 연결 파일 (@AGENTS.md 한 줄)
│
├── storage/                      # [데이터 저장소] 원본 데이터와 가공 문서의 완전한 분리
│   ├── raw/                      # 수집 원본 (불변 보존)
│   │   ├── confluence/           # Confluence 원본 JSON - 스페이스(프로젝트) 키별 폴더
│   │   │   ├── DEV/              #   스페이스 키별 폴더 (confluence_page_{id}.json)
│   │   │   └── _sample/          #   --mock 시뮬레이션용 샘플 (실제 스페이스 아님)
│   │   └── slack/                # Slack 원본 JSON - 채널명별 폴더
│   │       └── dev/                #   날짜(KST)별 파일 YYYY-MM-DD.json (스레드 댓글 포함)
│   ├── wiki/                     # ② LLM이 쓰고 관리하는 위키 (페이지 종류별 폴더, [[링크]]로 연결)
│   │   ├── index.md              #   전체 목차: 모든 페이지 링크 + 한 줄 요약 (질문 시 가장 먼저 읽음, 자동 갱신)
│   │   ├── log.md                #   작업 기록: ingest / query / lint / update (덧붙이기만 함)
│   │   ├── overview/             #   개요 - 시작 페이지
│   │   ├── synthesis/            #   종합 - 현황·결론 (결정·할 일·미결)
│   │   ├── entities/             #   엔티티 - 사람·팀·시스템·도구
│   │   ├── concepts/             #   개념 - 주제·용어·아이디어
│   │   ├── comparisons/          #   비교 - A vs B 표
│   │   └── summaries/            #   요약 - 원본 1개당 1페이지
│   │       ├── meetings/         #     Confluence 회의록
│   │       ├── slack/            #     Slack 하루 (요약 + 원문 대화) "Slack #{채널} YYYY-MM-DD.md"
│   │       ├── issues/           #     장애·이슈 분석
│   │       └── knowledge/        #     그 외 문서
│   ├── index/                    # RAG 벡터 인덱스 캐시 (vector_index.json, index 실행 시 전체 재구축)
│   └── tickets/                  # 발행된 티켓 기록 - Jira 프로젝트 키별 폴더
│       ├── index.md              #   전체 발행 티켓 목록 (최신순, 자동 갱신)
│       ├── DEV/                  #   프로젝트 키별 폴더 ({KEY}.md, 예: DEV-2.md)
│       └── LOCAL/                #   --provider local 로 생성한 로컬 티켓 (TICKET-*.md)
│
└── llm_wiki/                      # [Python 패키지 소스코드]
    ├── __init__.py
    ├── config.py                 # Pydantic 기반 설정 및 디렉터리 경로 자동 보장
    ├── main.py                   # CLI 명령어 구현체 (Rich UI 터미널 지원)
    ├── jira_mcp.py               # 사내 Jira Server용 MCP 서버 (Claude Code에서 이슈 생성·검색)
    │
    ├── slack/                    # [모듈] Slack 연동 계층
    │   └── client.py             # Slack Web API 수집기 (채널 히스토리·스레드, 날짜별 저장)
    │
    ├── confluence/               # [모듈] Confluence 연동 계층
    │   ├── models.py             # ConfluencePage 데이터 모델 & HTML → 텍스트 변환 (to_plain_text)
    │   ├── client.py             # Confluence REST API 수집기 & Mock 생성기
    │   └── credential.py         # Windows 자격 증명 관리자 계정 조회/저장
    │
    ├── llm/                      # [모듈] LLM & AI 생성 계층
    │   ├── client.py             # BaseLLMClient + Gemini / Gemma(Ollama) 클라이언트 (Generate & Embedding & Mock)
    │   ├── gemini.py             # (구버전, 미사용)
    │   └── prompts.py            # 위키 요약·Q&A·티켓 드래프트 프롬프트 템플릿
    │
    ├── wiki/                     # [모듈] 마크다운 위키 엔진
    │   ├── document.py           # 페이지 종류(PAGE_TYPES)·Frontmatter 모델, [[링크]] 추출
    │   ├── manager.py            # 종류별 폴더 저장, 링크 추가, index.md 자동 생성
    │   ├── linker.py             # Ingest 후처리: 엔티티·개념 추출 → 페이지 생성/갱신 + 양방향 링크
    │   ├── log.py                # log.md 덧붙이기 (ingest / query / lint / update / index)
    │   └── lint.py               # 점검: 깨진 링크, 고아 페이지, 요약 누락, 출처 없는 페이지
    │
    ├── rag/                      # [모듈] RAG 및 시맨틱 지식 검색 엔진
    │   ├── chunker.py            # 마크다운 H2/H3 섹션 및 단락 단위 청킹
    │   ├── embedder.py           # Gemini AI or Gemma AI 임베딩 모델을 통한 텍스트 벡터화
    │   └── store.py              # NumPy 코사인 유사도(Cosine Similarity) 고속 벡터 스토어
    │
    └── ticket/                   # [모듈] 티켓 생성 및 외부 발행 계층 (플러그형)
        ├── base.py               # TicketProvider 추상 베이스 클래스(ABC) & TicketDraft 모델
        ├── drafter.py            # RAG 검색 결과를 결합하여 고품질 티켓 초안을 작성하는 에이전트
        ├── record.py             # 발행 티켓을 tickets/{프로젝트 키}/에 기록하고 index.md 갱신
        └── providers/
            ├── local.py          # 로컬 마크다운 파일 티켓 발행자 (기본 탑재)
            └── jira.py           # Atlassian Jira Cloud REST API 발행자 (확장용)
```

### 저장 규칙
| 데이터 | 저장 위치 | 폴더 기준 |
|---|---|---|
| Confluence 원본 | `storage/raw/confluence/{스페이스 키}/confluence_page_{id}.json` | 페이지가 속한 스페이스 키 (API 응답의 `space.key`) |
| Slack 원본 | `storage/raw/slack/{채널명}/YYYY-MM-DD.json` | 채널 이름, 메시지 날짜(KST). 스레드 댓글은 원글의 `_replies`에 포함 |
| 위키 페이지 | `storage/wiki/{overview,synthesis,entities,concepts,comparisons}/{제목}.md` | 페이지 종류 (Frontmatter `type`) |
| 원본 요약 | `storage/wiki/summaries/{meetings,slack,issues,knowledge}/{제목}.md` | `type: summary` + 원본 종류 (`category`) |
| 발행 티켓 | `storage/tickets/{프로젝트 키}/{이슈 키}.md` | Jira 이슈 키의 프로젝트 부분 (예: `DEV-2` → `DEV/`) |

---

## ⚡ 4. 가상환경 활성화 및 실행 방법

### 1) PowerShell 가상환경 활성화
프로젝트 폴더(`llm-wiki`)로 이동한 후 가상환경을 활성화합니다:

```powershell
cd C:\path\to\llm-wiki

# 가상환경 활성화
.\.venv\Scripts\Activate.ps1
```

> [!TIP]
> 만약 PowerShell에서 스크립트 실행 권한 에러(`ExecutionPolicy`)가 발생할 경우 아래 명령어를 한 번 실행해 주세요:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

### 2) 환경 변수 설정
`.env.example`을 복사하여 `.env`를 생성하고 Gemini AI or Gemma AI API 키 및 Confluence 정보를 설정합니다:
```powershell
copy .env.example .env
```

### 3) LLM 설정 (기본: Gemini)
| 항목 | `.env` | 비고 |
|---|---|---|
| 백엔드 | `LLM_BACKEND=gemini` | 로컬 Ollama를 쓰려면 `gemma` (CPU에서는 느리고 요약·답변 오류가 잦음), Claude를 쓰려면 `claude` |
| 생성 모델 | `GEMINI_MODEL=gemini-2.5-flash` | |
| 임베딩 모델 | `GEMINI_EMBEDDING_MODEL=gemini-embedding-001` | 바꾸면 `python main.py index`로 인덱스 재구축 필요 |
| API 키 | (저장 안 함) | `python main.py set-gemini-key` → Windows 자격 증명 관리자(target: `gemini`)에 저장 |

```powershell
python main.py set-gemini-key   # 최초 1회 (AI Studio에서 발급한 키 입력)
python main.py index            # 임베딩 모델이 바뀌었으므로 인덱스 재구축
```
> [!NOTE]
> `ask`는 **짧고 빠르게** 답합니다: 결론 1~3문장 + `출처: [[페이지]]`, 출력 최대 400토큰, Gemini thinking 생략.
> Gemini를 쓰면 위키 내용(사내 문서)이 Google API로 전송됩니다.

**Claude 사용 시** (`LLM_BACKEND=claude`)
| 항목 | `.env` | 비고 |
|---|---|---|
| 생성 모델 | `CLAUDE_MODEL=claude-opus-5-5` | `ask`는 effort `low`, 위키 생성은 `medium` |
| 임베딩 | `CLAUDE_EMBEDDING_BACKEND=gemma` | Claude는 임베딩 API가 없어 `gemma`(Ollama) 또는 `gemini`가 담당. 바꾸면 `python main.py index` 재실행 |
| API 키 | (저장 안 함) | `python main.py set-claude-key` → Windows 자격 증명 관리자(target: `claude`)에 저장. `ANTHROPIC_API_KEY` 환경변수도 동작 |

> Claude를 쓰면 위키 내용(사내 문서)이 Anthropic API로 전송됩니다.

---

## 🖥️ 5. CLI 명령어 레퍼런스

가상환경이 활성화된 상태에서 `python main.py <command>`로 실행합니다.

### 1) 전체 파이프라인 일괄 실행 (수집 ➔ 위키화 ➔ 인덱싱)
```powershell
python main.py pipeline --mock
```

### 2) Confluence 원본 데이터 수집
```powershell
# 특정 페이지(회의록 등) 수집 → storage/raw/confluence/{스페이스 키}/ 저장 → 위키화 → 인덱싱
python main.py fetch-page 4653163

# 스페이스 전체 수집 (.env의 CONFLUENCE_SPACE_KEY)
python main.py sync

# Mock 시뮬레이션 수집 (storage/raw/confluence/_sample/ 저장)
python main.py sync --mock
```

### 3) Slack 채널 메시지 수집
```powershell
# 최초 1회: Bot 토큰(xoxb-...)을 Windows 자격 증명 관리자에 저장 (target: slack)
python main.py set-slack-token

# .env의 SLACK_CHANNEL_ID 채널 전체 수집 → storage/raw/slack/{채널명}/YYYY-MM-DD.json
python main.py fetch-slack

# 최근 N일만 / 다른 채널
python main.py fetch-slack --days 3
python main.py fetch-slack --channel C0XXXXXXXXX

# 수집한 대화 → storage/wiki/summaries/slack/ 날짜별 요약 + 엔티티·개념 연결 → RAG 인덱스 갱신
python main.py build-slack-wiki                       # 새로 수집된 날짜만 (이미 만든 문서는 건너뜀)
python main.py build-slack-wiki --date 2026-10-27     # 특정 날짜만
python main.py build-slack-wiki --force               # 전부 다시 생성
```
> Slack 위키 문서는 **LLM 요약**(요약·주요 논의·공유 자료·결정 사항·요청 및 할 일)과 **원문 대화**(메시지·스레드 그대로)로 구성됩니다. LLM이 놓친 내용도 원문으로 검색됩니다.
> [!NOTE]
> Bot에 필요한 권한: `channels:history`, `channels:read` (비공개 채널은 `groups:*`). 작성자 이름까지 받으려면 `users:read`를 추가하세요. 없으면 사용자 ID로 저장됩니다.

### 4) Confluence 원본 → 위키 (Ingest)
```powershell
# storage/raw/confluence/ 전체 → 요약 페이지 + 엔티티·개념 페이지 연결 + index.md·log.md 갱신
python main.py build-wiki
```

### 5) RAG 벡터 인덱스 생성
```powershell
python main.py index
```

### 6) 사내 위키 지식 시맨틱 검색
```powershell
python main.py search "결제 504 타임아웃 장애" --top-k 3
```

### 7) 위키 지식 기반 Q&A (Query)
```powershell
python main.py ask "8번 과제를 맡은 사람은 누구니?"            # index.md를 먼저 읽고 관련 페이지로 답변
python main.py ask "보고 회의는 누가 잡아?" -k 6                # 참조 섹션 수 늘리기
python main.py ask "Kafka와 RabbitMQ 차이는?" --save comparison --title "Kafka vs RabbitMQ"   # 답변을 위키 페이지로 저장
python main.py chat   # 대화형 모드
```
> 모든 질문은 `log.md`에 `query`로 기록되고, `--save`(synthesis / comparison / concept / overview)를 주면 답변이 해당 종류의 위키 페이지로 저장됩니다.
>
> 검색은 **하이브리드**입니다: 임베딩 코사인 유사도 50% + 한국어 2글자 키워드 일치율(IDF 가중) 50%. Slack 원문 대화 조각은 0.85배로 낮춰, 정리된 요약·엔티티 페이지가 먼저 나오게 합니다 (`llm_wiki/rag/store.py`의 `KEYWORD_WEIGHT`, `TRANSCRIPT_PENALTY`).
> 기본 참조 섹션 수는 8개입니다. gemma3:4b는 표(담당·기한)를 잘못 읽는 경우가 있어, 정확한 답이 필요하면 출처 페이지를 직접 확인하세요.

### 8) 위키 점검 (Lint)
```powershell
python main.py lint    # 깨진 링크, 고아 페이지, 한 줄 요약 누락, 출처 없는 엔티티·개념
```
> 구조 문제만 찾습니다. 내용이 사실인지는 원본(`storage/raw/`)과 대조해 사람이 판단합니다.

### 9) RAG 지식 기반 신규 티켓 자동 발행
```powershell
# 로컬 마크다운 티켓 발행 (storage/tickets/LOCAL/ 에 생성)
python main.py ticket "결제 요청 몰릴 때 504 에러 발생하는 이슈 조치 티켓 만들어줘" --provider local

# Jira 티켓 발행 (Jira Cloud API v3 기준 - 사내 Jira Server는 아래 MCP 사용)
python main.py ticket "결제 큐 비동기 전환 이슈" --provider jira
```

> [!TIP]
> 전역 옵션 `--backend gemini|gemma|claude`로 `.env`의 `LLM_BACKEND`를 덮어쓸 수 있습니다.

---

## 🎫 Jira MCP 서버 (Claude Code 연동)

구버전 Jira Server는 API 토큰(PAT)을 지원하지 않으므로, Windows 자격 증명 관리자의 `wiki.example.com` 계정으로 Basic 인증하는 MCP 서버(`llm_wiki/jira_mcp.py`)를 사용합니다.

```powershell
# 등록 (최초 1회, 사용자 범위)
claude mcp add-json llm-wiki-jira '{\"type\":\"stdio\",\"command\":\"C:\\path\\to\\llm-wiki\\.venv\\Scripts\\python.exe\",\"args\":[\"-m\",\"llm_wiki.jira_mcp\"],\"env\":{\"PYTHONPATH\":\"C:\\path\\to\\llm-wiki\",\"PYTHONIOENCODING\":\"utf-8\"}}' --scope user
```

| 도구 | 기능 |
|---|---|
| `jira_create_issue` | 이슈 생성 + `storage/tickets/{프로젝트 키}/{KEY}.md` 기록 (`source`에 근거 문서 지정) |
| `jira_record_issue` | 이미 발행된 이슈를 로컬 기록에 추가·갱신 |
| `jira_search` / `jira_get_issue` | JQL 검색 / 상세·댓글 조회 |
| `jira_add_comment` | 댓글 추가 |
| `jira_list_projects` / `jira_get_issue_types` | 프로젝트 목록 / 이슈 유형·필수 필드 |

> [!NOTE]
> 이슈 본문은 Markdown이 아닌 Jira 위키 마크업(`h2.`, `*`, `#`, `{code}`)을 사용합니다. 로컬 기록에는 Markdown으로 변환되어 저장됩니다.

---

## 🔌 6. 티켓 시스템 확장 인터페이스 (`TicketProvider` ABC)

Jira, GitHub Issues, ServiceNow 등 사내에서 사용하는 어떠한 이슈 트래커로도 손쉽게 확장할 수 있도록 파이썬 `abc.ABC`로 설계되었습니다.

```python
from abc import ABC, abstractmethod
from llm_wiki.ticket.base import TicketDraft, TicketResult

class TicketProvider(ABC):
    @abstractmethod
    def provider_name(self) -> str:
        """프로바이더 고유 식별자"""
        pass

    @abstractmethod
    def issue_ticket(self, draft: TicketDraft) -> TicketResult:
        """티켓 초안을 대상 시스템에 API로 발행"""
        pass
```
새로운 프로바이더는 `llm_wiki/ticket/providers/`에 위 클래스를 상속받아 구현하기만 하면 즉시 연동됩니다.

### 🔄 업무 자동화
Confluence와 Slack의 회의 내용을 주기적으로 수집·분석하고, LLM을 활용해 Action Item을 추출한 뒤 Jira Ticket을 자동으로 생성합니다.  
향후 **crontab 기반 스케줄링**을 적용하여 전체 업무 프로세스를 자동화할 예정입니다.
