import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import yaml

logger = logging.getLogger(__name__)

def jira_markup_to_markdown(text: str) -> str:
    """Jira 위키 마크업을 로컬 기록용 Markdown으로 단순 변환 (헤딩, 목록, 링크)"""
    out: List[str] = []
    for line in (text or "").splitlines():
        m = re.match(r"^h([1-6])\.\s+(.*)", line)
        if m:
            line = "#" * int(m.group(1)) + " " + m.group(2)
        else:
            m = re.match(r"^([*#]+)\s+(.*)", line)
            if m:
                marks = m.group(1)
                indent = "   " * (len(marks) - 1)
                bullet = "1." if marks[-1] == "#" else "-"
                line = f"{indent}{bullet} {m.group(2)}"
        line = re.sub(r"\[([^|\]]+)\|([^\]]+)\]", r"[\1](\2)", line)
        out.append(line)
    return "\n".join(out)

class TicketRecorder:
    """발행된 티켓을 storage/tickets/{프로젝트 키}/에 Markdown으로 기록하고 index.md 색인을 갱신"""

    def __init__(self, tickets_dir: Path):
        self.tickets_dir = tickets_dir

    def record_jira_issue(self, issue: Dict[str, Any], source: Optional[str] = None) -> Path:
        """Jira 이슈 상세(jira_get_issue 결과)를 {프로젝트 키}/{KEY}.md로 저장"""
        key = issue["key"]
        project = key.split("-")[0]
        project_dir = self.tickets_dir / project
        project_dir.mkdir(parents=True, exist_ok=True)
        fm = {
            "key": key,
            "provider": "jira_server",
            "url": issue.get("url"),
            "project": project,
            "summary": issue.get("summary"),
            "issue_type": issue.get("issue_type"),
            "priority": issue.get("priority"),
            "status": issue.get("status"),
            "assignee": issue.get("assignee"),
            "reporter": issue.get("reporter"),
            "labels": issue.get("labels", []),
            "created": issue.get("created"),
            "source": source,
        }
        fm = {k: v for k, v in fm.items() if v not in (None, "")}
        fm_yaml = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
        body = jira_markup_to_markdown(issue.get("description") or "")
        content = (
            f"---\n{fm_yaml}---\n\n"
            f"# [{key}] {issue.get('summary')}\n\n"
            f"- **Jira**: {issue.get('url')}\n"
            f"- **유형 / 우선순위 / 상태**: {issue.get('issue_type')} / {issue.get('priority')} / {issue.get('status')}\n"
            f"- **담당 / 보고자**: {issue.get('assignee') or '미지정'} / {issue.get('reporter')}\n"
            f"- **발행일시**: {issue.get('created')}\n"
            f"- **출처**: {source or '-'}\n\n"
            f"---\n\n{body}\n"
        )
        path = project_dir / f"{key}.md"
        path.write_text(content, encoding="utf-8")
        logger.info(f"티켓 기록 저장 완료: {path}")
        self.update_index()
        return path

    def update_index(self) -> None:
        """storage/tickets/index.md에 발행된 전체 티켓 목록 갱신 (최신순)"""
        rows = []
        for path in self.tickets_dir.rglob("*.md"):
            if path.name == "index.md":
                continue
            text = path.read_text(encoding="utf-8")
            fm: Dict[str, Any] = {}
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    fm = yaml.safe_load(parts[1]) or {}
            if not fm:
                # 로컬 프로바이더(TICKET-*.md)는 Frontmatter가 없으므로 첫 줄 제목 사용
                fm = {"key": path.stem, "provider": "local_markdown", "project": path.parent.name,
                      "summary": text.splitlines()[0].lstrip("# ")}
            fm["_file"] = path.relative_to(self.tickets_dir).as_posix()
            fm["_mtime"] = path.stat().st_mtime
            rows.append(fm)

        rows.sort(key=lambda r: str(r.get("created") or r["_mtime"]), reverse=True)
        lines = [
            "# 🎫 발행 티켓 목록",
            "",
            f"> 총 {len(rows)}건 (최신순, 자동 생성)",
            "",
            "| 티켓 | 프로젝트 | 제목 | 담당 | 우선순위 | 상태 | 발행일 | 출처 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for r in rows:
            created = str(r.get("created") or "")[:10]
            lines.append(
                f"| [{r.get('key')}]({r['_file']}) | {r.get('project', '-')} | {r.get('summary', '')} | "
                f"{r.get('assignee', '-')} | {r.get('priority', '-')} | {r.get('status', '-')} | {created} | {r.get('source', '-')} |"
            )
        (self.tickets_dir / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
