from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel
import os

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent

GEMINI_CREDENTIAL = ("gemini", "api_key")   # Windows 자격 증명 관리자 (target, user)
CLAUDE_CREDENTIAL = ("claude", "api_key")

def _api_key(env_name: str, credential: tuple) -> str:
    """환경변수 → 없으면 Windows 자격 증명 관리자(set-gemini-key / set-claude-key로 저장)에서 조회"""
    key = os.getenv(env_name, "")
    if key and not key.startswith("your_"):
        return key
    try:
        import keyring
        return keyring.get_password(*credential) or ""
    except Exception:
        return ""

class AppConfig(BaseModel):
    # LLM 설정: "gemini", "gemma" 또는 "claude"
    llm_backend: str = "gemini"

    # Gemini AI 설정
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "gemini-embedding-001"

    # Gemma AI 설정 (Ollama 또는 로컬/호스팅 엔드포인트)
    gemma_base_url: str = "http://localhost:11434"
    gemma_model: str = "gemma2:9b"
    gemma_embedding_model: str = "nomic-embed-text"
    gemma_num_ctx: int = 8192

    # Claude 설정 (Anthropic API). Claude는 임베딩 API가 없어 임베딩은 "gemma" 또는 "gemini"에 맡김
    claude_api_key: str = ""
    claude_model: str = "claude-opus-5-5"
    claude_embedding_backend: str = "gemma"

    # Confluence API 설정 (Atlassian Cloud)
    confluence_base_url: Optional[str] = None
    confluence_email: Optional[str] = None
    confluence_api_token: Optional[str] = None
    confluence_space_key: Optional[str] = "DEV"

    # Slack 설정 (Bot 토큰은 Windows 자격 증명 관리자에 저장: set-slack-token)
    slack_channel_id: Optional[str] = None

    # Jira 연동 설정 (선택 사항)
    jira_base_url: Optional[str] = None
    jira_email: Optional[str] = None
    jira_api_token: Optional[str] = None
    jira_project_key: str = "DEV"

    # 저장소 경로 설정
    raw_storage_path: Path = PROJECT_ROOT / "storage" / "raw"
    wiki_storage_path: Path = PROJECT_ROOT / "storage" / "wiki"
    index_storage_path: Path = PROJECT_ROOT / "storage" / "index"
    tickets_storage_path: Path = PROJECT_ROOT / "storage" / "tickets"

    @classmethod
    def load(cls) -> "AppConfig":
        raw_env = os.getenv("RAW_STORAGE_PATH")
        wiki_env = os.getenv("WIKI_STORAGE_PATH")
        index_env = os.getenv("INDEX_STORAGE_PATH")
        tickets_env = os.getenv("TICKETS_STORAGE_PATH")

        def resolve_path(env_val: Optional[str], default_rel: str) -> Path:
            if env_val:
                p = Path(env_val)
                return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()
            return (PROJECT_ROOT / default_rel).resolve()

        return cls(
            llm_backend=os.getenv("LLM_BACKEND", "gemini").lower(),
            gemini_api_key=_api_key("GEMINI_API_KEY", GEMINI_CREDENTIAL),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            gemini_embedding_model=os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
            gemma_base_url=os.getenv("GEMMA_BASE_URL", "http://localhost:11434"),
            gemma_model=os.getenv("GEMMA_MODEL", "gemma2:9b"),
            gemma_embedding_model=os.getenv("GEMMA_EMBEDDING_MODEL", "nomic-embed-text"),
            gemma_num_ctx=int(os.getenv("GEMMA_NUM_CTX", "8192")),
            claude_api_key=_api_key("ANTHROPIC_API_KEY", CLAUDE_CREDENTIAL),
            claude_model=os.getenv("CLAUDE_MODEL", "claude-opus-5-5"),
            claude_embedding_backend=os.getenv("CLAUDE_EMBEDDING_BACKEND", "gemma").lower(),
            confluence_base_url=os.getenv("CONFLUENCE_BASE_URL"),
            confluence_email=os.getenv("CONFLUENCE_EMAIL"),
            confluence_api_token=os.getenv("CONFLUENCE_API_TOKEN"),
            confluence_space_key=os.getenv("CONFLUENCE_SPACE_KEY", "DEV"),
            slack_channel_id=os.getenv("SLACK_CHANNEL_ID"),
            jira_base_url=os.getenv("JIRA_BASE_URL"),
            jira_email=os.getenv("JIRA_EMAIL"),
            jira_api_token=os.getenv("JIRA_API_TOKEN"),
            jira_project_key=os.getenv("JIRA_PROJECT_KEY", "DEV"),
            raw_storage_path=resolve_path(raw_env, "storage/raw"),
            wiki_storage_path=resolve_path(wiki_env, "storage/wiki"),
            index_storage_path=resolve_path(index_env, "storage/index"),
            tickets_storage_path=resolve_path(tickets_env, "storage/tickets"),
        )

    def ensure_directories(self) -> None:
        self.raw_storage_path.mkdir(parents=True, exist_ok=True)
        self.wiki_storage_path.mkdir(parents=True, exist_ok=True)
        self.index_storage_path.mkdir(parents=True, exist_ok=True)
        self.tickets_storage_path.mkdir(parents=True, exist_ok=True)
        (self.wiki_storage_path / "issues").mkdir(parents=True, exist_ok=True)
        (self.wiki_storage_path / "knowledge").mkdir(parents=True, exist_ok=True)
        (self.wiki_storage_path / "meetings").mkdir(parents=True, exist_ok=True)
        (self.wiki_storage_path / "slack").mkdir(parents=True, exist_ok=True)
        (self.raw_storage_path / "confluence").mkdir(parents=True, exist_ok=True)
        (self.raw_storage_path / "slack").mkdir(parents=True, exist_ok=True)
