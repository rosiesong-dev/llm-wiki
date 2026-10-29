import json
import logging
import re
from typing import Dict, List
from llm_wiki.llm.client import BaseLLMClient
from llm_wiki.llm.prompts import Prompts
from llm_wiki.wiki.document import WikiDocument, WikiFrontmatter
from llm_wiki.wiki.manager import WikiManager

logger = logging.getLogger(__name__)

MAX_ITEMS = 8   # 원본 1개당 엔티티·개념 각각 최대 개수

class WikiLinker:
    """Ingest 후처리: 요약 페이지에서 엔티티·개념을 뽑아 해당 페이지를 만들거나 갱신하고 서로 [[링크]]로 연결

    - LLM은 이름·설명·사실만 추출하고, 페이지 생성·추가는 코드가 결정적으로 수행
    - 원문(source_text)에 실제로 등장하지 않는 이름은 버림 (소형 모델의 환각 방지)
    """

    def __init__(self, llm: BaseLLMClient, manager: WikiManager):
        self.llm = llm
        self.manager = manager

    def link_source(self, summary_doc: WikiDocument, source_text: str) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {"created": [], "updated": []}
        title = summary_doc.frontmatter.title
        # 요약 페이지 본문 중 원문 대화 섹션은 제외하고 LLM에 전달 (토큰 절약)
        summary_part = summary_doc.body.split("## 원문 대화", 1)[0]
        resp = self.llm.generate_text(Prompts.build_entity_extraction_prompt(title, summary_part))
        if self.llm.last_was_mock:
            logger.warning("LLM 호출 실패로 엔티티·개념 연결을 건너뜁니다.")
            return result
        try:
            m = re.search(r"\{[\s\S]*\}", resp)
            data = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError as e:
            logger.warning(f"엔티티·개념 JSON 파싱 실패: {e}")
            return result

        haystack = source_text + "\n" + summary_part
        linked: List[str] = []
        for page_type, key in (("entity", "entities"), ("concept", "concepts")):
            for item in (data.get(key) or [])[:MAX_ITEMS]:
                name = str(item.get("name", "")).strip()
                if not name or name == title or name not in haystack:
                    continue
                facts = [str(f).strip() for f in item.get("facts", []) if str(f).strip()]
                page, created = self._get_or_create(page_type, name, item)
                if self._add_source_facts(page, title, facts):
                    self.manager.save_wiki_document(page, update_index=False)
                    result["created" if created else "updated"].append(page.frontmatter.title)
                linked.append(page.frontmatter.title)

        if self.manager.add_links(summary_doc, "관련 페이지", linked):
            self.manager.save_wiki_document(summary_doc, update_index=False)
        self.manager.update_wiki_index()
        return result

    def _get_or_create(self, page_type: str, name: str, item: dict):
        existing = self.manager.find_by_title(name)
        if existing:
            return existing, False
        description = str(item.get("description", "")).strip()
        kind = str(item.get("kind", "")).strip()
        fm = WikiFrontmatter(
            title=name,
            type=page_type,
            tags=[kind] if kind else [],
            summary=description or None,
        )
        body = f"# {name}\n\n{description}\n\n## 출처별 내용\n"
        return WikiDocument(self.manager.path_for(fm), fm, body, []), True

    @staticmethod
    def _add_source_facts(page: WikiDocument, source_title: str, facts: List[str]) -> bool:
        """`## 출처별 내용`에 `### [[원본 요약 제목]]` + 사실 목록 추가 (같은 출처는 한 번만)"""
        marker = f"### [[{source_title}]]"
        if marker in page.body:
            return False
        block = marker + "\n" + ("\n".join(f"- {f}" for f in facts) if facts else "- (언급됨)") + "\n"
        if "## 출처별 내용" not in page.body:
            page.body = page.body.rstrip() + "\n\n## 출처별 내용\n"
        # 출처별 내용 섹션의 끝(다음 ## 섹션 앞)에 추가
        head, _, rest = page.body.partition("## 출처별 내용")
        nxt = re.search(r"^## ", rest, re.M)
        if nxt:
            page.body = head + "## 출처별 내용" + rest[:nxt.start()].rstrip() + "\n\n" + block + "\n" + rest[nxt.start():]
        else:
            page.body = head + "## 출처별 내용" + rest.rstrip() + "\n\n" + block
        page.backlinks = WikiDocument.extract_backlinks(page.body)
        return True
