import json
import logging
import re
from typing import List, Tuple
from llm_wiki.llm.client import BaseLLMClient
from llm_wiki.llm.prompts import Prompts
from llm_wiki.rag.store import SearchResult, VectorStore
from llm_wiki.ticket.base import TicketDraft

logger = logging.getLogger(__name__)

class TicketDrafter:
    def __init__(self, llm_client: BaseLLMClient, vector_store: VectorStore):
        self.llm_client = llm_client
        self.vector_store = vector_store

    def draft_ticket(self, requirement: str) -> Tuple[TicketDraft, List[SearchResult]]:
        """신규 이슈/요구사항에 대해 RAG로 관련 위키를 탐색하고 고품질 티켓 초안을 작성"""
        logger.info("티켓 초안 생성을 위한 관련 위키 지식 탐색 시작...")
        query_vec = self.llm_client.generate_embedding(requirement)
        search_results = self.vector_store.search(query_vec, top_k=3, query_text=requirement)

        context_lines: List[str] = []
        for i, res in enumerate(search_results):
            context_lines.append(
                f"--- [문서 {i+1}]: {res.chunk.chunk.document_title} ({res.chunk.chunk.section_title}) (유사도: {res.score:.2f}) ---\n"
                f"{res.chunk.chunk.content}\n"
            )
        context = "\n".join(context_lines)

        prompt = Prompts.build_ticket_draft_prompt(requirement, context)
        resp_text = self.llm_client.generate_text(prompt)

        cleaned_json = self._extract_json_block(resp_text)
        try:
            draft_data = json.loads(cleaned_json)
            draft = TicketDraft(**draft_data)
        except Exception as e:
            logger.error(f"티켓 JSON 파싱 실패: {e}\n원본 응답: {resp_text}")
            raise ValueError(f"티켓 JSON 파싱 실패: {e}")

        return draft, search_results

    @staticmethod
    def _extract_json_block(text: str) -> str:
        trimmed = text.strip()
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", trimmed)
        if m:
            return m.group(1).strip()
        return trimmed
