from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel

class TicketDraft(BaseModel):
    title: str
    issue_type: str
    priority: str
    labels: List[str] = []
    description: str
    suggested_assignee: Optional[str] = None

class TicketResult(BaseModel):
    provider: str
    ticket_id: str
    url: Optional[str] = None
    status: str

class TicketProvider(ABC):
    """다양한 티켓 시스템(Jira, GitHub Issues, 로컬 마크다운 등) 연동을 위한 추상 베이스 클래스"""

    @abstractmethod
    def provider_name(self) -> str:
        """프로바이더 고유 식별자 (예: local_markdown, jira_cloud, github_issues)"""
        pass

    @abstractmethod
    def issue_ticket(self, draft: TicketDraft) -> TicketResult:
        """티켓 초안을 대상 시스템에 발행"""
        pass
