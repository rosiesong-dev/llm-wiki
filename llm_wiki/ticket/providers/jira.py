import logging
from typing import Optional
import requests
from llm_wiki.ticket.base import TicketDraft, TicketProvider, TicketResult

logger = logging.getLogger(__name__)

class JiraTicketProvider(TicketProvider):
    def __init__(self, base_url: str, project_key: str, email: Optional[str] = None, api_token: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.project_key = project_key
        self.email = email
        self.api_token = api_token

    def provider_name(self) -> str:
        return "jira_cloud"

    def issue_ticket(self, draft: TicketDraft) -> TicketResult:
        logger.info(f"Jira Cloud 연동: 프로젝트 [{self.project_key}]에 티켓 발행 중... (제목: {draft.title})")

        # 실제 Jira API 키가 설정되어 있으면 REST API 호출
        if self.email and self.api_token and self.api_token != "your_jira_api_token_here":
            url = f"{self.base_url}/rest/api/3/issue"
            payload = {
                "fields": {
                    "project": {"key": self.project_key},
                    "summary": draft.title,
                    "description": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": draft.description}]
                            }
                        ]
                    },
                    "issuetype": {"name": "Task" if draft.issue_type not in ["Bug", "Task"] else draft.issue_type},
                    "labels": draft.labels,
                }
            }
            try:
                resp = requests.post(
                    url,
                    json=payload,
                    auth=(self.email, self.api_token),
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                    timeout=15,
                )
                if resp.status_code in [200, 201]:
                    data = resp.json()
                    key = data.get("key", f"{self.project_key}-NEW")
                    ticket_url = f"{self.base_url}/browse/{key}"
                    logger.info(f"Jira 티켓 발행 성공: {ticket_url}")
                    return TicketResult(
                        provider=self.provider_name(),
                        ticket_id=key,
                        url=ticket_url,
                        status="CREATED",
                    )
                else:
                    logger.warning(f"Jira API 응답 에러 [{resp.status_code}]: {resp.text} -> 시뮬레이션 모드로 전환")
            except Exception as e:
                logger.warning(f"Jira API 요청 실패: {e} -> 시뮬레이션 모드로 전환")

        # Fallback / Mock
        simulated_key = f"{self.project_key}-101"
        simulated_url = f"{self.base_url}/browse/{simulated_key}"
        return TicketResult(
            provider=self.provider_name(),
            ticket_id=simulated_key,
            url=simulated_url,
            status="SIMULATED_SUCCESS",
        )
