from datetime import datetime
import logging
from pathlib import Path
import re
from typing import Dict, List, Optional
from llm_wiki.wiki.document import PAGE_TYPES, WikiDocument, WikiFrontmatter

logger = logging.getLogger(__name__)

RESERVED_FILES = ("index.md", "log.md")

# index.md 섹션 순서와 제목 (LLM이 질문을 받으면 index.md를 가장 먼저 읽음)
INDEX_SECTIONS = [
    ("overview", None, "🧭 개요 (Overview)", "전체를 한눈에 보는 안내 페이지"),
    ("synthesis", None, "🧩 종합 (Synthesis)", "여러 원본을 엮은 현재 현황·결론"),
    ("entity", None, "👤 엔티티 (Entities)", "사람·팀·시스템·도구"),
    ("concept", None, "💡 개념 (Concepts)", "주제·용어·아이디어"),
    ("comparison", None, "⚖️ 비교 (Comparisons)", "두 개 이상을 나란히 비교"),
    ("summary", "meetings", "🗓️ 요약 · 회의록 (Summaries / Meetings)", "Confluence 회의록 1건당 1페이지"),
    ("summary", "slack", "💬 요약 · Slack (Summaries / Slack)", "Slack 채널 하루당 1페이지"),
    ("summary", "issues", "🚨 요약 · 이슈 (Summaries / Issues)", "장애·이슈 분석"),
    ("summary", "knowledge", "📄 요약 · 기타 문서 (Summaries / Knowledge)", "그 외 업무 문서"),
]

def safe_filename(title: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", title)

class WikiManager:
    """storage/wiki/ 위키 저장소 관리

    storage/wiki/
    ├── index.md        모든 페이지 링크 + 한 줄 요약 (종류별) - LLM이 질문 시 가장 먼저 읽음
    ├── log.md          작업 기록 (덧붙이기만 함)
    ├── overview/       개요
    ├── synthesis/      종합
    ├── entities/       엔티티
    ├── concepts/       개념
    ├── comparisons/    비교
    └── summaries/{meetings,slack,issues,knowledge}/  원본 1개당 요약
    """

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    def path_for(self, fm: WikiFrontmatter) -> Path:
        folder = self.base_dir / PAGE_TYPES[fm.type]
        if fm.type == "summary":
            folder = folder / (fm.category or "knowledge")
        return folder / f"{safe_filename(fm.title)}.md"

    def load_all_documents(self) -> List[WikiDocument]:
        """위키 저장소 내의 모든 .md 문서를 재귀적으로 스캔 (index.md, log.md 제외)"""
        docs: List[WikiDocument] = []
        if not self.base_dir.exists():
            return docs

        for path in self.base_dir.rglob("*.md"):
            if path.name in RESERVED_FILES:
                continue
            try:
                content = path.read_text(encoding="utf-8")
                doc = WikiDocument.parse(content, path)
                docs.append(doc)
            except Exception as e:
                logger.warning(f"문서 파싱 실패 {path}: {e}")
        return docs

    def find_by_title(self, title: str) -> Optional[WikiDocument]:
        """제목 또는 별칭(aliases)으로 페이지 찾기"""
        for doc in self.load_all_documents():
            if doc.frontmatter.title == title or title in doc.frontmatter.aliases:
                return doc
        return None

    def save_wiki_document(self, doc: WikiDocument, update_index: bool = True) -> Path:
        """페이지 종류(type)에 맞는 폴더에 저장. 같은 제목의 문서가 다른 위치에 있으면 옮김"""
        doc.frontmatter.updated = datetime.now().strftime("%Y-%m-%d")
        file_path = self.path_for(doc.frontmatter)
        old_path = doc.path if doc.path and doc.path.suffix == ".md" else None

        doc.save_to_file(file_path)
        if old_path and old_path.exists() and old_path.resolve() != file_path.resolve():
            old_path.unlink()
        doc.path = file_path
        logger.info(f"위키 문서 저장 완료: {file_path}")

        if update_index:
            self.update_wiki_index()
        return file_path

    @staticmethod
    def add_links(doc: WikiDocument, heading: str, titles: List[str]) -> bool:
        """본문의 `## {heading}` 섹션에 [[링크]]를 추가 (이미 있는 링크는 건너뜀). 변경 여부 반환"""
        new = [t for t in dict.fromkeys(titles) if f"[[{t}]]" not in doc.body and t != doc.frontmatter.title]
        if not new:
            return False
        items = "\n".join(f"- [[{t}]]" for t in new)
        m = re.search(rf"^## {re.escape(heading)}\s*$", doc.body, re.M)
        if m:
            # 섹션 끝(다음 ## 또는 문서 끝) 바로 앞에 추가
            nxt = re.search(r"^## ", doc.body[m.end():], re.M)
            pos = m.end() + nxt.start() if nxt else len(doc.body)
            doc.body = doc.body[:pos].rstrip() + "\n" + items + "\n\n" + doc.body[pos:].lstrip()
        else:
            doc.body = doc.body.rstrip() + f"\n\n## {heading}\n{items}\n"
        doc.backlinks = WikiDocument.extract_backlinks(doc.body)
        return True

    def update_wiki_index(self) -> None:
        """index.md 재생성: 모든 페이지의 [[링크]] + 한 줄 요약을 종류별로 정리"""
        docs = self.load_all_documents()
        groups: Dict[tuple, List[WikiDocument]] = {}
        for d in docs:
            key = (d.frontmatter.type, d.frontmatter.category if d.frontmatter.type == "summary" else None)
            groups.setdefault(key, []).append(d)

        counts = ", ".join(
            f"{name} {sum(1 for d in docs if d.frontmatter.type == t)}"
            for t, name in [("overview", "개요"), ("synthesis", "종합"), ("entity", "엔티티"),
                            ("concept", "개념"), ("comparison", "비교"), ("summary", "요약")]
        )
        lines = [
            "# 📚 LLM-Wiki 색인 (index.md)",
            "",
            "> **LLM은 질문을 받으면 이 파일을 가장 먼저 읽고**, 관련 페이지를 골라 답합니다.",
            "> 모든 페이지의 링크와 한 줄 요약을 종류별로 정리한 목차이며, 위키가 바뀔 때마다 자동 갱신됩니다.",
            f"> 전체 {len(docs)}개 페이지 ({counts}) · 갱신: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
        ]
        for page_type, category, heading, desc in INDEX_SECTIONS:
            items = groups.get((page_type, category), [])
            if page_type == "summary" and not items:
                continue  # 원본이 없는 요약 분류는 생략
            lines += [f"## {heading}", f"*{desc}*", ""]
            if not items:
                lines.append("- (아직 없음)")
            # 요약은 최신순, 나머지는 가나다순
            items.sort(key=lambda d: d.frontmatter.title, reverse=(page_type == "summary"))
            for d in items:
                summary = d.frontmatter.summary or "요약 없음"
                lines.append(f"- [[{d.frontmatter.title}]] - {summary}")
            lines.append("")

        (self.base_dir / "index.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        logger.info("최상위 index.md 색인 갱신 완료")
