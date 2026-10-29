from datetime import datetime
import logging
from pathlib import Path
from llm_wiki.ticket.base import TicketDraft, TicketProvider, TicketResult

logger = logging.getLogger(__name__)

class LocalMarkdownTicketProvider(TicketProvider):
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def provider_name(self) -> str:
        return "local_markdown"

    def issue_ticket(self, draft: TicketDraft) -> TicketResult:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ticket_id = f"TICKET-{timestamp}"
        file_path = self.output_dir / f"{ticket_id}.md"

        content = f"""# [{draft.issue_type}] {draft.title}

- **티켓 ID**: {ticket_id}
- **유형**: {draft.issue_type}
- **우선순위**: {draft.priority}
- **라벨**: {", ".join(draft.labels)}
- **추천 담당**: {draft.suggested_assignee or "미지정"}
- **발행일시**: {datetime.now().isoformat()}

---

{draft.description}
"""
        file_path.write_text(content, encoding="utf-8")
        logger.info(f"로컬 티켓 생성 완료: {file_path}")

        return TicketResult(
            provider=self.provider_name(),
            ticket_id=ticket_id,
            url=str(file_path.resolve()),
            status="CREATED",
        )
