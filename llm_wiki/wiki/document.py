from pathlib import Path
import re
from typing import List, Optional
from pydantic import BaseModel
import yaml

# 위키 페이지 종류 (Karpathy LLM-Wiki 패턴) → 저장 폴더
PAGE_TYPES = {
    "overview": "overview",        # 개요: 전체를 한눈에 보는 안내 페이지
    "synthesis": "synthesis",      # 종합: 여러 원본을 엮은 결론, 계속 발전하는 현황·논지
    "entity": "entities",          # 엔티티: 사람·팀·시스템·도구 등 대상별 페이지
    "concept": "concepts",         # 개념: 주제·용어·아이디어별 페이지
    "comparison": "comparisons",   # 비교: 두 개 이상을 나란히 비교
    "summary": "summaries",        # 요약: 원본 1개(회의록 1건, Slack 하루 등)당 요약 페이지
}
# 요약 페이지의 원본 종류 → summaries/ 하위 폴더
SUMMARY_CATEGORIES = ("meetings", "slack", "issues", "knowledge")

class WikiFrontmatter(BaseModel):
    title: str
    type: str = "summary"
    category: str = "knowledge"      # summary 페이지의 원본 종류 (meetings / slack / issues / knowledge)
    tags: List[str] = []
    source_id: Optional[str] = None
    summary: Optional[str] = None    # index.md에 쓰이는 한 줄 요약
    aliases: List[str] = []          # 엔티티·개념의 다른 이름 (예: 사용자 ID, 영문명)
    updated: Optional[str] = None

class WikiDocument:
    def __init__(self, path: Path, frontmatter: WikiFrontmatter, body: str, backlinks: List[str]):
        self.path = path
        self.frontmatter = frontmatter
        self.body = body
        self.backlinks = backlinks

    @classmethod
    def parse(cls, raw_markdown: str, file_path: Path) -> "WikiDocument":
        """마크다운 문자열에서 YAML Frontmatter, 본문, 백링크를 분리 추출"""
        fm_data = {}
        # LLM이 문서 전체나 Frontmatter를 ```yaml / ```markdown 코드 블록으로 감싸 출력하는 경우 펜스 제거
        raw_markdown = raw_markdown.strip()
        fence = re.match(r"^```[\w-]*\s*\n(---\n[\s\S]*?\n---)\s*\n?```?\s*\n?", raw_markdown)
        if fence:
            raw_markdown = fence.group(1) + "\n" + raw_markdown[fence.end():]
        elif raw_markdown.startswith("```"):
            raw_markdown = re.sub(r"^```[\w-]*\s*\n", "", raw_markdown)
            raw_markdown = re.sub(r"\n```\s*$", "", raw_markdown)
        body = raw_markdown

        if raw_markdown.startswith("---"):
            parts = raw_markdown.split("---", 2)
            if len(parts) >= 3:
                try:
                    fm_data = yaml.safe_load(parts[1]) or {}
                except Exception:
                    fm_data = {}
                body = parts[2].strip()

        if not fm_data.get("title"):
            fm_data["title"] = file_path.stem
        # 페이지 종류가 없던 기존 문서는 원본 요약(summary)으로 간주
        if fm_data.get("type") not in PAGE_TYPES:
            fm_data["type"] = "summary"
        fm_data = {k: v for k, v in fm_data.items() if k in WikiFrontmatter.model_fields}

        frontmatter = WikiFrontmatter(**fm_data)
        backlinks = cls.extract_backlinks(body)
        return cls(file_path, frontmatter, body, backlinks)

    @staticmethod
    def extract_backlinks(content: str) -> List[str]:
        """`[[문서명]]` 백링크 문법 파싱 (`[[문서명|표시명]]`은 문서명만)"""
        return [link.split("|")[0].strip() for link in re.findall(r"\[\[(.*?)\]\]", content)]

    def save_to_file(self, target_path: Path) -> None:
        """YAML Frontmatter와 본문을 결합하여 마크다운 파일 저장"""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        fm_dict = self.frontmatter.model_dump(exclude_none=True)
        # 요약 페이지가 아니면 category는 의미가 없으므로 생략, 빈 목록도 생략
        if self.frontmatter.type != "summary":
            fm_dict.pop("category", None)
        fm_dict = {k: v for k, v in fm_dict.items() if v != []}
        fm_yaml = yaml.dump(fm_dict, allow_unicode=True, default_flow_style=False, sort_keys=False)
        content = f"---\n{fm_yaml}---\n\n{self.body}\n"
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
