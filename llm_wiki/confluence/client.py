import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
from llm_wiki.confluence.credential import get_windows_credential
from llm_wiki.confluence.models import ConfluencePage

logger = logging.getLogger(__name__)

class ConfluenceClient:
    def __init__(
        self,
        base_url: str = "http://wiki.example.com/confluence",
        email: Optional[str] = None,
        api_token: Optional[str] = None,
        use_windows_credential: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.api_token = api_token

        # Windows 자격 증명 관리자에서 자동 로드
        if use_windows_credential and (not self.email or not self.api_token):
            target = "wiki.example.com" if "wiki.example.com" in self.base_url else "confluence"
            win_user, win_pass = get_windows_credential(target)
            if win_user and win_pass:
                self.email = win_user
                self.api_token = win_pass
                logger.info(f"Windows 자격 증명 관리자의 계정({win_user})을 사용하여 Confluence에 연동합니다.")

    def _get_auth(self) -> Optional[tuple]:
        if self.email and self.api_token:
            # Confluence Server/DC는 이메일 전체가 아닌 계정명(아이디)을 사용자명으로 요구하는 경우가 많음
            username = self.email.split("@")[0] if "@" in self.email and "wiki.example.com" in self.base_url else self.email
            return (username, self.api_token)
        return None

    def get_current_user(self) -> Dict[str, Any]:
        """Confluence 현재 로그인 사용자 정보 확인 (/rest/api/user/current)"""
        url = f"{self.base_url}/rest/api/user/current"
        auth = self._get_auth()
        resp = requests.get(url, auth=auth, headers={"Accept": "application/json"}, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def fetch_page_by_id(self, page_id: str) -> ConfluencePage:
        """Confluence Server/DC REST API v1을 통해 특정 단일 페이지(회의록 등) 수집"""
        url = f"{self.base_url}/rest/api/content/{page_id}?expand=body.storage,version,history,space"
        auth = self._get_auth()
        logger.info(f"Confluence 페이지 수집 요청: {url} (인증: {'계정 인증' if auth else '익명'})")

        resp = requests.get(url, auth=auth, headers={"Accept": "application/json"}, timeout=20)
        if resp.status_code == 404:
            raise PermissionError(
                f"페이지 [{page_id}]를 찾을 수 없거나 접근 권한이 없습니다 (404/Forbidden).\n"
                "Windows 자격 증명 관리자에 올바른 Confluence 계정/비밀번호가 등록되어 있는지 확인해 주세요."
            )
        resp.raise_for_status()
        data = resp.json()

        title = data.get("title", f"Confluence Page {page_id}")
        space_key = data.get("space", {}).get("key")
        body_val = (
            data.get("body", {})
            .get("storage", {})
            .get("value", "")
        )
        version_num = data.get("version", {}).get("number")
        author_id = data.get("history", {}).get("createdBy", {}).get("displayName") or data.get("history", {}).get("createdBy", {}).get("username")
        created_at = data.get("history", {}).get("createdDate")

        return ConfluencePage(
            id=str(page_id),
            title=title,
            space_id=space_key,
            status=data.get("status", "current"),
            author_id=author_id,
            created_at=created_at,
            version_number=version_num,
            body_storage_value=body_val,
        )

    def fetch_pages_by_space(self, space_id_or_key: str) -> List[ConfluencePage]:
        """Confluence Space 내의 페이지들을 수집"""
        auth = self._get_auth()
        # 1. Cloud API v2 시도
        url_v2 = f"{self.base_url}/api/v2/spaces/{space_id_or_key}/pages"
        try:
            resp = requests.get(url_v2, auth=auth, headers={"Accept": "application/json"}, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                pages = []
                for item in data.get("results", []):
                    body_val = item.get("body", {}).get("storage", {}).get("value", "")
                    pages.append(ConfluencePage(
                        id=str(item.get("id", "")),
                        title=item.get("title", ""),
                        space_id=space_id_or_key,
                        status=item.get("status"),
                        author_id=item.get("authorId"),
                        created_at=item.get("createdAt"),
                        version_number=item.get("version", {}).get("number"),
                        body_storage_value=body_val,
                    ))
                return pages
        except Exception:
            pass

        # 2. Server/DC API v1 fallback (/rest/api/content?spaceKey=...)
        url_v1 = f"{self.base_url}/rest/api/content?spaceKey={space_id_or_key}&expand=body.storage,version,history"
        resp = requests.get(url_v1, auth=auth, headers={"Accept": "application/json"}, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        pages = []
        for item in data.get("results", []):
            body_val = item.get("body", {}).get("storage", {}).get("value", "")
            pages.append(ConfluencePage(
                id=str(item.get("id", "")),
                title=item.get("title", ""),
                space_id=space_id_or_key,
                status=item.get("status"),
                author_id=item.get("history", {}).get("createdBy", {}).get("displayName"),
                created_at=item.get("history", {}).get("createdDate"),
                version_number=item.get("version", {}).get("number"),
                body_storage_value=body_val,
            ))
        return pages

    @staticmethod
    def save_raw_pages(raw_dir: Path, pages: List[ConfluencePage]) -> None:
        """수집된 원본 페이지를 storage/raw/confluence/{스페이스 키}/에 JSON으로 안전 보존"""
        for page in pages:
            space_dir = raw_dir / (page.space_id or "UNKNOWN")
            space_dir.mkdir(parents=True, exist_ok=True)
            file_path = space_dir / f"confluence_page_{page.id}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(page.model_dump(), f, ensure_ascii=False, indent=2)

    @staticmethod
    def generate_sample_raw_pages(raw_dir: Path) -> List[ConfluencePage]:
        sample_pages = [
            ConfluencePage(
                id="3768355",
                title="2026-10-23 플랫폼 엔지니어링 및 결제 아키텍처 주간 회의록",
                space_id="PROJ",
                status="current",
                author_id="user",
                created_at="2026-10-23T10:00:00Z",
                version_number=1,
                body_storage_value="""
                <h1>회의 개요</h1>
                <p>일시: 2026년 10월 23일 오전 10시<br/>참석자: 홍길동, 백엔드팀, 인프라팀<br/>안건: 결제 타임아웃 장애 대책 및 Kafka 비동기 큐 전환 검토</p>
                <h2>주요 논의 내용</h2>
                <p>1. 결제 모듈 504 장애 원인은 동시 결제 500 TPS 인입 시 HikariCP 풀 고갈(10개)로 밝혀짐.<br/>
                2. 임시로 풀 30으로 확장 조치하였으며, 주말 간 안정성 유지됨.<br/>
                3. 영구 대책으로 Kafka 기반 결제 대기열 파이프라인 도입 일정 합의 필요.</p>
                <h2>최종 결정 사항 (Decisions)</h2>
                <p>- 11월 1주차까지 Kafka 비동기 결제 PoC 개발 완료<br/>
                - K8s 파드 리소스 limit을 request의 1.5배로 상향 조정</p>
                <h2>액션 아이템 (Action Items)</h2>
                <p>- [홍길동] Kafka 토픽 파티션 설계 및 티켓 발행<br/>
                - [인프라팀] 결제 네임스페이스 리소스 쿼터 재할당</p>
                """,
            )
        ]
        # 샘플은 실제 스페이스 폴더와 섞이지 않도록 _sample/ 아래에 저장
        sample_dir = raw_dir / "_sample"
        sample_dir.mkdir(parents=True, exist_ok=True)
        for page in sample_pages:
            (sample_dir / f"confluence_page_{page.id}.json").write_text(
                json.dumps(page.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return sample_pages
