from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

# log.md 작업 종류
LOG_OPS = ("ingest", "query", "lint", "update", "index")

class WikiLog:
    """storage/wiki/log.md - 언제 무엇을 넣고(ingest), 묻고(query), 점검(lint)했는지 시간순 기록 (덧붙이기만 함)

    형식: `## [YYYY-MM-DD HH:MM] 작업 | 제목` + 상세 불릿
    최근 기록 보기: Select-String -Path log.md -Pattern '^## \\[' | Select-Object -Last 5
    """

    HEADER = (
        "# 📜 LLM-Wiki 작업 기록 (log.md)\n\n"
        "> 위키에 원본을 넣고(ingest), 질문하고(query), 점검(lint)·수정(update)한 이력입니다.\n"
        "> **덧붙이기만 하고 수정·삭제하지 않습니다.** 형식: `## [날짜 시각] 작업 | 제목`\n"
    )

    def __init__(self, wiki_dir: Path):
        self.path = wiki_dir / "log.md"

    def append(self, op: str, title: str, details: Optional[Iterable[str]] = None, when: Optional[datetime] = None) -> None:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(self.HEADER, encoding="utf-8")
        stamp = (when or datetime.now()).strftime("%Y-%m-%d %H:%M")
        lines: List[str] = ["", f"## [{stamp}] {op} | {title}"]
        lines += [f"- {d}" for d in (details or [])]
        with open(self.path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def recent(self, n: int = 5) -> List[str]:
        """최근 n개 작업 제목줄"""
        if not self.path.exists():
            return []
        heads = [line for line in self.path.read_text(encoding="utf-8").splitlines() if line.startswith("## [")]
        return heads[-n:]
