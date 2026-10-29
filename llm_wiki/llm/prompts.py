class Prompts:
    @staticmethod
    def build_wiki_summary_prompt(title: str, raw_content: str, metadata: str) -> str:
        """원본 Confluence 문서를 사내 LLM-Wiki용 마크다운으로 구조화하는 프롬프트"""
        return f"""당신은 사내 지식 위키(LLM-Wiki)를 관리하는 수석 테크니컬 라이터입니다.
아래 Confluence에서 수집한 원본 업무 문서와 이슈 내용을 분석하여, 깔끔하고 구조화된 Markdown 위키 문서로 재작성해 주세요.

## 작성 규칙:
1. 최상단에 YAML Frontmatter를 반드시 포함하세요. 형식:
---
title: "{title}"
category: "meetings" (회의록) 또는 "issues" (장애·이슈 분석) 또는 "knowledge" (그 외 업무 지식)
tags: [관련태그1, 관련태그2]
source_id: "Confluence 원본 ID"
summary: "문서의 1~2줄 요약"
---
2. 문서 본문은 문서 종류에 맞는 아래 목차를 참고하여 체계적으로 정리하세요:
   - 회의록(meetings):
     - ## 회의 정보 (일시, 참석자, 진행, 작성자)
     - ## 요약
     - ## 결정 사항
     - ## 논의 내용 (안건별 ### 소제목)
     - ## 할 일 (담당 | 할 일 | 기한 표 형식, 담당자 이름과 번호를 원문 그대로 유지)
     - ## 미결 사항
   - 장애·이슈 분석 및 업무 지식(issues, knowledge):
     - ## 개요 (Summary)
     - ## 배경 및 원인 분석 (Background & Root Cause)
     - ## 핵심 조치 및 해결 방법 (Action Items & Resolution)
     - ## 재발 방지 및 관련 지식 (Lessons Learned & Reference)
3. 다른 위키 문서와의 연결을 위해 관련 키워드나 시스템명은 `[[관련_문서_이름]]` 형태의 백링크 문법을 적절히 활용하세요.
4. 불필요한 HTML 태그는 제거하고 표준 Markdown 서식(코드블록, 불릿포인트, 표 등)을 충실히 사용하세요.

[메타데이터]:
{metadata}

[원본 Confluence 내용]:
{raw_content}
"""

    @staticmethod
    def build_slack_digest_prompt(channel: str, date: str, conversation: str) -> str:
        """Slack 채널의 하루치 대화를 위키용 요약 문서로 정리하는 프롬프트"""
        return f"""당신은 사내 지식 위키(LLM-Wiki)를 관리하는 수석 테크니컬 라이터입니다.
아래는 Slack #{channel} 채널의 {date} 하루 대화입니다. (└ 표시는 스레드 댓글, U로 시작하는 값은 사용자 ID)
이 대화를 Markdown 위키 요약 문서로 정리해 주세요.

## 작성 규칙:
1. 최상단에 YAML Frontmatter를 반드시 포함하세요. 형식:
---
title: "Slack #{channel} {date}"
category: "slack"
tags: [관련태그1, 관련태그2]
summary: "그날 대화의 1~2줄 요약"
---
2. 본문은 아래 목차로 정리하세요. 해당 내용이 없는 섹션은 "없음"이라고 쓰세요.
   - ## 요약 (3줄 이내)
   - ## 주요 논의 (주제별 ### 소제목, 누가 무엇을 말했는지)
   - ## 공유된 자료 (문서·링크·첨부 파일과 공유한 사람)
   - ## 결정 사항
   - ## 요청 및 할 일 (요청한 사람 → 대상, 내용)
3. 사용자 ID(U...)와 이름은 원문 그대로 쓰고, 대화에 없는 내용은 절대 지어내지 마세요.
4. 원문 대화 전체는 별도로 첨부되므로 다시 옮겨 적지 말고 요약만 작성하세요.

[Slack 대화]:
{conversation}
"""

    @staticmethod
    def build_ticket_draft_prompt(issue_requirement: str, retrieved_context: str) -> str:
        """RAG로 검색된 위키 지식과 사용자 요구사항을 결합해 신규 티켓 초안을 작성하는 프롬프트"""
        return f"""당신은 엔지니어링 티켓(Jira/GitHub Issue) 생성 전문 AI 에이전트입니다.
아래 제공된 [사내 위키 지식]을 참조하여, 새롭게 접수된 [이슈/요구사항]에 대한 고품질 티켓 초안을 작성하세요.

[사내 위키 지식]:
{retrieved_context}

[이슈 / 요구사항]:
{issue_requirement}

## 티켓 초안 작성 형식 (JSON 형식으로만 응답):
```json
{{
  "title": "[분류] 간결하고 명확한 티켓 제목",
  "issue_type": "Bug" | "Task" | "Improvement" | "Incident",
  "priority": "High" | "Medium" | "Low",
  "labels": ["label1", "label2"],
  "description": "Markdown 형식의 상세 설명 (현상, 원인 추정, 위키 지식 참조 링크, 제안 작업 목록, 검증 방안 포함)",
  "suggested_assignee": "추천 담당 역할 또는 팀"
}}
```
반드시 위의 JSON 블록 하나만 출력해 주세요.
"""

    @staticmethod
    def build_entity_extraction_prompt(source_title: str, summary: str) -> str:
        """Ingest 후처리: 요약 문서에서 엔티티·개념과 그에 대한 사실을 JSON으로 추출하는 프롬프트"""
        return f"""당신은 사내 지식 위키(LLM-Wiki)의 편집자입니다.
아래 [위키 요약 문서]를 읽고, 위키에 별도 페이지로 둘 만한 엔티티와 개념을 뽑아 주세요.

## 규칙:
1. entities: 사람, 팀, 조직, 시스템·도구·제품, 프로젝트 (예: 홍길동, Jira, Kafka)
2. concepts: 주제, 용어, 아이디어, 방법론 (예: 메시지 큐, 데이터 리니지, 목업 UI)
3. name은 문서에 적힌 표기를 **그대로** 쓰세요. 문서에 없는 이름은 절대 만들지 마세요.
4. facts는 **이 문서에서 알 수 있는** 그 대상에 대한 사실 1~3개 (누가 무엇을 맡았는지, 결정·기한 등)
5. 각 최대 8개, 중요한 것만. 날짜·숫자 같은 일반 단어는 제외하세요.

## 응답 형식 (JSON만 출력):
```json
{{
  "entities": [{{"name": "이름", "kind": "person|team|organization|system|project", "description": "한 줄 설명", "facts": ["사실1"]}}],
  "concepts": [{{"name": "이름", "description": "한 줄 설명", "facts": ["사실1"]}}]
}}
```

[위키 요약 문서]: {source_title}
{summary}
"""

    @staticmethod
    def build_qa_prompt(question: str, retrieved_context: str, wiki_index: str = "") -> str:
        """index.md(전체 목차)와 RAG로 검색된 위키 페이지를 바탕으로 질문에 답변하는 프롬프트"""
        index_block = f"\n[위키 색인 (index.md) - 먼저 읽고 관련 페이지를 파악하세요]:\n{wiki_index}\n" if wiki_index else ""
        return f"""당신은 사내 지식 위키(LLM-Wiki) 어시스턴트입니다.
[위키 색인]으로 전체 구성을 파악한 뒤, [관련 위키 페이지]만 근거로 질문에 답하세요.

## 답변 규칙 (짧고 빠르게):
1. **결론부터 1~3문장**으로 답하세요. 인사말·서론·질문 반복·부연 설명은 쓰지 마세요.
2. 사람·날짜·숫자는 표(담당 | 할 일 | 기한)에 적힌 그대로 쓰세요.
3. 마지막 줄에 근거 페이지를 `출처: [[문서명]]` 형식으로 1~2개만 적으세요.
4. 위키로 알 수 없으면 "위키에 없는 내용입니다." 한 문장만 답하세요. 추측하지 마세요.
{index_block}
[관련 위키 페이지]:
{retrieved_context}

[사용자 질문]:
{question}
"""
