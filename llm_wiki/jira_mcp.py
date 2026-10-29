"""사내 Jira Server(7.13) 연동 MCP 서버 (stdio)

Jira 7.13은 PAT/API 토큰을 지원하지 않으므로 Windows 자격 증명 관리자에 저장된
계정(기본 타겟: wiki.example.com)으로 Basic 인증하여 REST API v2를 호출합니다.

실행: python -m llm_wiki.jira_mcp
"""
import logging
import os
import sys
from typing import Any, Dict, List, Optional
import requests
from mcp.server.mcpserver import MCPServer
from llm_wiki.config import AppConfig
from llm_wiki.confluence.credential import get_windows_credential
from llm_wiki.ticket.record import TicketRecorder

# stdio 전송은 stdout을 프로토콜에 사용하므로 로그는 반드시 stderr로 출력
logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("llm-wiki.jira-mcp")

JIRA_BASE_URL = os.getenv("LLM_WIKI_JIRA_BASE_URL", "http://wiki.example.com/jira").rstrip("/")
CREDENTIAL_TARGET = os.getenv("LLM_WIKI_JIRA_CREDENTIAL_TARGET", "wiki.example.com")

class JiraServerClient:
    """Jira Server/DC REST API v2 클라이언트"""

    def __init__(self, base_url: str, credential_target: str):
        self.base_url = base_url
        self.credential_target = credential_target
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})

    def _ensure_auth(self) -> None:
        if self.session.auth:
            return
        user, password = get_windows_credential(self.credential_target)
        if not user or not password:
            raise RuntimeError(
                f"Windows 자격 증명 관리자에 '{self.credential_target}' 계정이 없습니다. "
                "'python main.py set-credential'로 먼저 등록해 주세요."
            )
        # Jira Server는 이메일이 아닌 계정명(아이디)으로 로그인
        self.session.auth = (user.split("@")[0], password)

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        self._ensure_auth()
        resp = self.session.request(method, f"{self.base_url}/rest/api/2{path}", timeout=20, **kwargs)
        if not resp.ok:
            raise RuntimeError(f"Jira API 오류 [{resp.status_code}] {method} {path}: {resp.text[:500]}")
        return resp.json() if resp.content else {}

jira = JiraServerClient(JIRA_BASE_URL, CREDENTIAL_TARGET)
recorder = TicketRecorder(AppConfig.load().tickets_storage_path)
mcp = MCPServer(
    name="llm-wiki-jira",
    instructions=(
        f"사내 Jira Server ({JIRA_BASE_URL}) 연동 도구입니다. "
        "이슈 본문(description, comment)은 Markdown이 아닌 Jira 위키 마크업을 사용합니다 "
        "(예: h2. 제목, * 불릿, # 번호목록, {code}...{code}, [링크|URL])."
    ),
)

def _issue_summary(issue: Dict[str, Any]) -> Dict[str, Any]:
    f = issue.get("fields", {})
    return {
        "key": issue.get("key"),
        "url": f"{JIRA_BASE_URL}/browse/{issue.get('key')}",
        "summary": f.get("summary"),
        "issue_type": (f.get("issuetype") or {}).get("name"),
        "status": (f.get("status") or {}).get("name"),
        "priority": (f.get("priority") or {}).get("name"),
        "assignee": (f.get("assignee") or {}).get("displayName"),
        "reporter": (f.get("reporter") or {}).get("displayName"),
        "labels": f.get("labels", []),
        "created": f.get("created"),
        "updated": f.get("updated"),
    }

@mcp.tool()
def jira_list_projects() -> List[Dict[str, str]]:
    """접근 가능한 Jira 프로젝트 목록(key, name)을 조회합니다."""
    return [{"key": p["key"], "name": p["name"]} for p in jira.request("GET", "/project")]

@mcp.tool()
def jira_get_issue_types(project_key: str) -> List[Dict[str, Any]]:
    """프로젝트에서 생성 가능한 이슈 유형과 각 유형의 필수 필드를 조회합니다."""
    data = jira.request(
        "GET", "/issue/createmeta",
        params={"projectKeys": project_key, "expand": "projects.issuetypes.fields"},
    )
    result = []
    for proj in data.get("projects", []):
        for it in proj.get("issuetypes", []):
            required = [
                f"{k} ({v.get('name')})" for k, v in it.get("fields", {}).items() if v.get("required")
            ]
            result.append({"name": it["name"], "subtask": it.get("subtask", False), "required_fields": required})
    return result

@mcp.tool()
def jira_create_issue(
    project_key: str,
    summary: str,
    description: str = "",
    issue_type: str = "Task",
    priority: Optional[str] = None,
    labels: Optional[List[str]] = None,
    assignee: Optional[str] = None,
    parent_key: Optional[str] = None,
    source: Optional[str] = None,
) -> Dict[str, str]:
    """Jira 이슈를 생성하고 storage/tickets/{KEY}.md에 발행 기록을 남깁니다.

    Args:
        project_key: 프로젝트 키 (예: DEV)
        summary: 이슈 제목
        description: 본문 (Jira 위키 마크업)
        issue_type: Task, Story, Bug, Sub-task 등 (Epic은 Epic Name 필드가 필요해 미지원)
        priority: Highest, High, Medium, Low, Lowest
        labels: 라벨 목록 (공백 불가)
        assignee: 담당자 Jira 계정명(아이디, 예: user)
        parent_key: Sub-task 생성 시 상위 이슈 키
        source: 티켓 근거 문서 (예: confluence-4653163 또는 위키 문서 제목) - 로컬 기록에 남김
    """
    fields: Dict[str, Any] = {
        "project": {"key": project_key},
        "summary": summary,
        "issuetype": {"name": issue_type},
    }
    if description:
        fields["description"] = description
    if priority:
        fields["priority"] = {"name": priority}
    if labels:
        fields["labels"] = labels
    if assignee:
        fields["assignee"] = {"name": assignee}
    if parent_key:
        fields["parent"] = {"key": parent_key}

    created = jira.request("POST", "/issue", json={"fields": fields})
    key = created["key"]
    logger.info(f"Jira 이슈 생성 완료: {key}")
    result = {"key": key, "url": f"{JIRA_BASE_URL}/browse/{key}"}
    try:
        result["record"] = str(recorder.record_jira_issue(jira_get_issue(key), source=source))
    except Exception as e:
        # 기록 실패가 이미 생성된 이슈의 결과를 가리지 않도록 경고만 남김
        logger.warning(f"티켓 로컬 기록 실패 {key}: {e}")
    return result

@mcp.tool()
def jira_record_issue(issue_key: str, source: Optional[str] = None) -> Dict[str, str]:
    """이미 발행된 Jira 이슈를 storage/tickets/에 기록(또는 최신 상태로 갱신)합니다."""
    path = recorder.record_jira_issue(jira_get_issue(issue_key), source=source)
    return {"key": issue_key, "record": str(path)}

@mcp.tool()
def jira_get_issue(issue_key: str) -> Dict[str, Any]:
    """이슈 상세(요약 정보, 본문, 최근 댓글 5개)를 조회합니다."""
    issue = jira.request("GET", f"/issue/{issue_key}")
    detail = _issue_summary(issue)
    f = issue.get("fields", {})
    detail["description"] = f.get("description")
    comments = (f.get("comment") or {}).get("comments", [])[-5:]
    detail["comments"] = [
        {"author": (c.get("author") or {}).get("displayName"), "created": c.get("created"), "body": c.get("body")}
        for c in comments
    ]
    return detail

@mcp.tool()
def jira_search(jql: str, max_results: int = 20) -> List[Dict[str, Any]]:
    """JQL로 이슈를 검색합니다. (예: project = DEV AND assignee = currentUser() ORDER BY updated DESC)"""
    data = jira.request(
        "POST", "/search",
        json={
            "jql": jql,
            "maxResults": max_results,
            "fields": ["summary", "issuetype", "status", "priority", "assignee", "reporter", "labels", "created", "updated"],
        },
    )
    return [_issue_summary(i) for i in data.get("issues", [])]

@mcp.tool()
def jira_add_comment(issue_key: str, body: str) -> Dict[str, str]:
    """이슈에 댓글을 추가합니다. (Jira 위키 마크업)"""
    c = jira.request("POST", f"/issue/{issue_key}/comment", json={"body": body})
    return {"id": c.get("id", ""), "url": f"{JIRA_BASE_URL}/browse/{issue_key}?focusedCommentId={c.get('id', '')}"}

if __name__ == "__main__":
    mcp.run("stdio")
