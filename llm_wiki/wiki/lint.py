from dataclasses import dataclass, field
from typing import Dict, List
from llm_wiki.wiki.manager import WikiManager

@dataclass
class LintReport:
    broken_links: Dict[str, List[str]] = field(default_factory=dict)   # 페이지 → 없는 페이지로의 링크
    orphans: List[str] = field(default_factory=list)                   # 들어오는 링크가 없는 페이지
    no_summary: List[str] = field(default_factory=list)                # index.md 한 줄 요약이 없는 페이지
    unsourced: List[str] = field(default_factory=list)                 # 출처가 없는 엔티티·개념

    @property
    def issue_count(self) -> int:
        return sum(len(v) for v in self.broken_links.values()) + len(self.orphans) + len(self.no_summary) + len(self.unsourced)

def lint_wiki(manager: WikiManager) -> LintReport:
    """구조 점검 (코드로 판단 가능한 것만). 내용의 사실 여부는 사람이 판단"""
    docs = manager.load_all_documents()
    titles = {d.frontmatter.title for d in docs} | {a for d in docs for a in d.frontmatter.aliases}
    inbound: Dict[str, int] = {d.frontmatter.title: 0 for d in docs}
    report = LintReport()

    for d in docs:
        missing = sorted({link for link in d.backlinks if link not in titles})
        if missing:
            report.broken_links[d.frontmatter.title] = missing
        for link in set(d.backlinks):
            if link in inbound and link != d.frontmatter.title:
                inbound[link] += 1
        if not d.frontmatter.summary:
            report.no_summary.append(d.frontmatter.title)
        if d.frontmatter.type in ("entity", "concept") and "### [[" not in d.body:
            report.unsourced.append(d.frontmatter.title)

    # 개요는 진입점이므로 들어오는 링크가 없어도 고아로 보지 않음
    report.orphans = sorted(
        t for t, n in inbound.items()
        if n == 0 and next(d for d in docs if d.frontmatter.title == t).frontmatter.type != "overview"
    )
    return report
