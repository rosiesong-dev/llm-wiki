from abc import ABC, abstractmethod
import json
import logging
from typing import List, Optional
import numpy as np
import requests

logger = logging.getLogger(__name__)

class BaseLLMClient(ABC):
    """Gemini AI, Gemma AI, Claude를 일관되게 다루기 위한 LLM 추상 기본 클래스"""

    # 직전 generate_text 호출이 실제 LLM 대신 Mock 응답으로 대체되었는지 여부
    # (위키 저장 전에 확인해 가짜 응답이 저장소를 덮어쓰지 않도록 함)
    last_was_mock: bool = False

    @abstractmethod
    def generate_text(self, prompt: str, max_output_tokens: Optional[int] = None, fast: bool = False) -> str:
        """max_output_tokens: 출력 길이 상한 (짧은 답변용), fast: 추론(thinking) 단계 생략 등 속도 우선"""
        pass

    @abstractmethod
    def generate_embedding(self, text: str) -> List[float]:
        pass

class GeminiClient(BaseLLMClient):
    """Google Gemini AI REST API 클라이언트"""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash", embedding_model: str = "gemini-embedding-001"):
        self.api_key = api_key
        self.model = model
        self.embedding_model = embedding_model

    def _headers(self) -> dict:
        # API 키는 URL 쿼리 대신 헤더로 전달 (로그·에러 메시지에 키가 남지 않도록)
        return {"Content-Type": "application/json", "x-goog-api-key": self.api_key}

    def generate_text(self, prompt: str, max_output_tokens: Optional[int] = None, fast: bool = False) -> str:
        self.last_was_mock = False
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            logger.warning("[Gemini AI] GEMINI_API_KEY 미설정 - 시뮬레이션(Mock) 응답을 반환합니다.")
            self.last_was_mock = True
            return self._mock_generate(prompt)

        payload: dict = {"contents": [{"parts": [{"text": prompt}]}]}
        gen_config: dict = {}
        if max_output_tokens:
            gen_config["maxOutputTokens"] = max_output_tokens
        if fast:
            # Gemini 2.5 Flash의 thinking 단계를 끄면 응답이 훨씬 빨라짐 (간단한 Q&A용)
            gen_config["thinkingConfig"] = {"thinkingBudget": 0}
        if gen_config:
            payload["generationConfig"] = gen_config

        resp = requests.post(f"{self.BASE_URL}/{self.model}:generateContent", json=payload,
                             headers=self._headers(), timeout=120)
        if not resp.ok:
            raise RuntimeError(f"Gemini API 오류 [{resp.status_code}]: {resp.text[:300]}")
        data = resp.json()

        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
            if text:
                return text
        raise RuntimeError(f"Gemini 응답에 텍스트가 없습니다: {str(data)[:300]}")

    def generate_embedding(self, text: str) -> List[float]:
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            return self._mock_embedding(text)

        payload = {"content": {"parts": [{"text": text}]}}
        resp = requests.post(f"{self.BASE_URL}/{self.embedding_model}:embedContent", json=payload,
                             headers=self._headers(), timeout=30)
        if not resp.ok:
            raise RuntimeError(f"Gemini 임베딩 API 오류 [{resp.status_code}]: {resp.text[:300]}")
        data = resp.json()

        embedding = data.get("embedding", {}).get("values")
        if embedding:
            return embedding
        return self._mock_embedding(text)

    def _mock_generate(self, prompt: str) -> str:
        if "티켓 초안" in prompt or "엔지니어링 티켓" in prompt:
            return json.dumps({
                "title": "[스크럼] 2026-10-23 데일리 스크럼 이슈 및 액션 아이템 조치",
                "issue_type": "Task",
                "priority": "Medium",
                "labels": ["scrum", "daily", "platform"],
                "description": (
                    "## 이슈 개요\n"
                    "- 2026-10-23 데일리 스크럼 회의에서 논의된 플랫폼 엔지니어링 후속 조치 태스크\n\n"
                    "## 참조 지식\n"
                    "- [[2026-10-23_정기_데일리 스크럼 회의록]]\n\n"
                    "## 주요 액션 아이템\n"
                    "1. 스크럼 논의 사항 검토 및 배포 일정 점검"
                ),
                "suggested_assignee": "우준석"
            }, ensure_ascii=False, indent=2)
        else:
            # 원본 Confluence 내용에서 제목과 텍스트 추출 시도
            import re
            title_match = re.search(r'title: "([^"]+)"', prompt)
            title = title_match.group(1) if title_match else "Confluence 회의록 지식 문서"

            # HTML 태그 제거 및 텍스트 정리
            raw_match = re.search(r'\[원본 Confluence 내용\]:\s*([\s\S]*)', prompt)
            raw_html = raw_match.group(1) if raw_match else ""
            clean_text = re.sub(r'<[^>]+>', ' ', raw_html)
            clean_lines = [line.strip() for line in clean_text.splitlines() if line.strip()]
            summary_preview = clean_lines[0] if clean_lines else "사내 회의록 및 업무 공유 문서"
            body_content = "\n".join(f"- {line}" for line in clean_lines[:15]) if clean_lines else "회의 내용 요약"

            return f"""---
title: "{title}"
category: "knowledge"
tags: ["회의록", "스크럼", "사내지식", "업무공유"]
source_id: "confluence-3768355"
summary: "{title} - 주요 안건 및 팀별 업무 공유 내용"
---

# {title}

## 1. 개요 (Summary)
- **문서 제목**: {title}
- **기본 정보**: 사내 Confluence에서 직접 수집된 팀 정기 데일리 스크럼 회의록입니다.

## 2. 주요 논의 및 공유 내용 (Key Discussion)
{body_content}

## 3. 결정 사항 및 액션 아이템 (Decisions & Action Items)
- 각 팀별 진행 업무 및 블로커 이슈 공유 완료.
- 후속 조치가 필요한 사항은 지식 위키 및 티켓 시스템을 통해 지속 관리.

## 4. 관련 지식 및 참고 문서 (References)
- [[사내_개발_가이드라인]]
- [[플랫폼_엔지니어링_위키]]
"""

    def _mock_embedding(self, text: str) -> List[float]:
        vec = np.zeros(768, dtype=np.float32)
        for i, b in enumerate(text.encode("utf-8")):
            vec[i % 768] += float(b) / 255.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

class GemmaClient(BaseLLMClient):
    """Gemma AI (Ollama 또는 로컬/호스팅 REST API) 클라이언트"""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "gemma2:9b", embedding_model: str = "nomic-embed-text",
                 num_ctx: int = 8192):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.embedding_model = embedding_model
        self.num_ctx = num_ctx

    def generate_text(self, prompt: str, max_output_tokens: Optional[int] = None, fast: bool = False) -> str:
        self.last_was_mock = False
        url = f"{self.base_url}/api/generate"
        # Ollama 기본 컨텍스트(2048~4096)로는 긴 Confluence 원본이 잘리므로 확장
        options: dict = {"num_ctx": self.num_ctx}
        if max_output_tokens:
            options["num_predict"] = max_output_tokens
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": options,
        }
        try:
            # CPU 추론 시 긴 문서는 수 분이 걸리므로 읽기 타임아웃을 넉넉히 설정 (연결 10초, 응답 15분)
            resp = requests.post(url, json=payload, timeout=(10, 900))
            if resp.status_code == 200:
                return resp.json().get("response", "")
            logger.warning(f"[Gemma AI] 생성 API 응답 에러 [{resp.status_code}]: {resp.text} - 시뮬레이션 모드로 전환합니다.")
        except Exception as e:
            logger.warning(f"[Gemma AI] 로컬 Ollama 연결 실패 ({e}) - 시뮬레이션 모드로 전환합니다.")

        # Fallback to Mock
        self.last_was_mock = True
        return GeminiClient("", "")._mock_generate(prompt)

    def generate_embedding(self, text: str) -> List[float]:
        url = f"{self.base_url}/api/embeddings"
        payload = {
            "model": self.embedding_model,
            "prompt": text,
        }
        try:
            resp = requests.post(url, json=payload, timeout=20)
            if resp.status_code == 200:
                embedding = resp.json().get("embedding")
                if embedding:
                    return embedding
            else:
                logger.warning(f"[Gemma AI] 임베딩 API 응답 에러 [{resp.status_code}]: {resp.text} - 해시 임베딩을 사용합니다.")
        except Exception as e:
            logger.warning(f"[Gemma AI] 임베딩 서버 연결 실패 ({e}) - 해시 임베딩을 사용합니다.")

        return GeminiClient("", "")._mock_embedding(text)

class ClaudeClient(BaseLLMClient):
    """Anthropic Claude API 클라이언트 (Claude는 임베딩 API가 없어 임베딩은 embedder에 위임)"""

    def __init__(self, api_key: str, model: str = "claude-opus-5-5", embedder: Optional[BaseLLMClient] = None):
        import anthropic
        self.model = model
        self.embedder = embedder or GeminiClient("", "")
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else None

    def generate_text(self, prompt: str, max_output_tokens: Optional[int] = None, fast: bool = False) -> str:
        import anthropic
        self.last_was_mock = False
        if self.client is None:
            logger.warning("[Claude] ANTHROPIC_API_KEY 미설정 - 시뮬레이션(Mock) 응답을 반환합니다.")
            self.last_was_mock = True
            return GeminiClient("", "")._mock_generate(prompt)

        # thinking이 항상 켜져 있고 thinking 토큰도 max_tokens에 포함되므로, 짧은 답변용 상한도 여유를 둠
        max_tokens = max(max_output_tokens, 4000) if max_output_tokens else 64000
        try:
            # 긴 원본 요약은 응답이 길어 HTTP 타임아웃을 피하려고 스트리밍으로 받음
            # fallbacks="default": 안전 분류기가 거절하면 서버가 권장 모델로 다시 실행
            with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": "low" if fast else "medium"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            ) as stream:
                message = stream.get_final_message()
        except anthropic.APIStatusError as e:
            raise RuntimeError(f"Claude API 오류 [{e.status_code}]: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise RuntimeError(f"Claude API 연결 실패: {e}") from e

        if message.stop_reason == "refusal":
            raise RuntimeError(f"Claude가 요청을 거절했습니다: {message.stop_details}")
        text = "".join(b.text for b in message.content if b.type == "text")
        if text:
            return text
        raise RuntimeError(f"Claude 응답에 텍스트가 없습니다 (stop_reason={message.stop_reason})")

    def generate_embedding(self, text: str) -> List[float]:
        return self.embedder.generate_embedding(text)

def _gemma_client(config) -> GemmaClient:
    return GemmaClient(
        base_url=config.gemma_base_url,
        model=config.gemma_model,
        embedding_model=config.gemma_embedding_model,
        num_ctx=config.gemma_num_ctx,
    )

def _gemini_client(config) -> GeminiClient:
    return GeminiClient(
        api_key=config.gemini_api_key,
        model=config.gemini_model,
        embedding_model=config.gemini_embedding_model,
    )

def create_llm_client(config) -> BaseLLMClient:
    """설정에 따라 Gemini AI, Gemma AI 또는 Claude 클라이언트를 생성"""
    if config.llm_backend == "gemma":
        logger.info(f"LLM 백엔드: Gemma AI ({config.gemma_model} @ {config.gemma_base_url})")
        return _gemma_client(config)
    elif config.llm_backend == "claude":
        # 임베딩 백엔드를 바꾸면 기존 RAG 인덱스와 벡터 차원이 달라지므로 'index'를 다시 실행해야 함
        embedder = _gemini_client(config) if config.claude_embedding_backend == "gemini" else _gemma_client(config)
        logger.info(f"LLM 백엔드: Claude ({config.claude_model}, 임베딩 {config.claude_embedding_backend})")
        return ClaudeClient(api_key=config.claude_api_key, model=config.claude_model, embedder=embedder)
    else:
        logger.info(f"LLM 백엔드: Gemini AI ({config.gemini_model}, 임베딩 {config.gemini_embedding_model})")
        return _gemini_client(config)
