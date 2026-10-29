from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import keyring
import requests

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
CREDENTIAL_TARGET = "slack"
CREDENTIAL_USER = "bot"

def save_slack_token(token: str) -> None:
    """Slack Bot 토큰을 Windows 자격 증명 관리자에 저장 (target=slack, user=bot)"""
    keyring.set_password(CREDENTIAL_TARGET, CREDENTIAL_USER, token)

class SlackClient:
    """Slack Web API 수집기 (Bot 토큰은 Windows 자격 증명 관리자에서 로드)"""

    def __init__(self, token: Optional[str] = None):
        self.token = token or keyring.get_password(CREDENTIAL_TARGET, CREDENTIAL_USER)
        if not self.token:
            raise RuntimeError(
                "Slack Bot 토큰이 없습니다. 'python main.py set-slack-token'으로 먼저 등록해 주세요."
            )
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        self._user_cache: Dict[str, Optional[str]] = {}

    def _call(self, method: str, **params: Any) -> Dict[str, Any]:
        while True:
            resp = self.session.get(f"https://slack.com/api/{method}", params=params, timeout=20)
            if resp.status_code == 429:
                # Rate limit: Retry-After(초) 만큼 대기 후 재시도
                wait = int(resp.headers.get("Retry-After", "5"))
                logger.warning(f"Slack rate limit - {wait}초 대기 후 재시도 ({method})")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(f"Slack API 오류 ({method}): {data.get('error')}")
            return data

    def get_channel(self, channel_id: str) -> Dict[str, Any]:
        return self._call("conversations.info", channel=channel_id)["channel"]

    def fetch_history(self, channel_id: str, oldest: Optional[float] = None) -> List[Dict[str, Any]]:
        """채널 메시지 전체 수집 (페이지네이션). 스레드가 있는 메시지는 '_replies'에 댓글 포함"""
        messages: List[Dict[str, Any]] = []
        cursor = None
        while True:
            params: Dict[str, Any] = {"channel": channel_id, "limit": 200}
            if oldest:
                params["oldest"] = f"{oldest:.6f}"
            if cursor:
                params["cursor"] = cursor
            data = self._call("conversations.history", **params)
            messages.extend(data.get("messages", []))
            cursor = (data.get("response_metadata") or {}).get("next_cursor")
            if not data.get("has_more") or not cursor:
                break

        for m in messages:
            if m.get("reply_count"):
                m["_replies"] = self.fetch_replies(channel_id, m["ts"])
            m["_user_name"] = self.get_user_name(m.get("user"))
        messages.sort(key=lambda m: float(m["ts"]))
        return messages

    def fetch_replies(self, channel_id: str, thread_ts: str) -> List[Dict[str, Any]]:
        replies: List[Dict[str, Any]] = []
        cursor = None
        while True:
            params: Dict[str, Any] = {"channel": channel_id, "ts": thread_ts, "limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = self._call("conversations.replies", **params)
            # 첫 메시지는 부모(원글) 자신이므로 제외
            replies.extend(r for r in data.get("messages", []) if r.get("ts") != thread_ts)
            cursor = (data.get("response_metadata") or {}).get("next_cursor")
            if not data.get("has_more") or not cursor:
                break
        for r in replies:
            r["_user_name"] = self.get_user_name(r.get("user"))
        return replies

    def get_user_name(self, user_id: Optional[str]) -> Optional[str]:
        """사용자 ID → 표시 이름 (users:read 권한이 없으면 None)"""
        if not user_id:
            return None
        if user_id not in self._user_cache:
            try:
                user = self._call("users.info", user=user_id)["user"]
                profile = user.get("profile", {})
                self._user_cache[user_id] = profile.get("display_name") or profile.get("real_name") or user.get("name")
            except RuntimeError as e:
                if "missing_scope" in str(e):
                    logger.info("users:read 권한이 없어 사용자 ID로 저장합니다.")
                    # 같은 오류를 반복 호출하지 않도록 이후 조회는 모두 생략
                    self.get_user_name = lambda _uid: None  # type: ignore[method-assign]
                    return None
                self._user_cache[user_id] = None
        return self._user_cache[user_id]

    @staticmethod
    def save_raw_by_date(raw_dir: Path, channel: Dict[str, Any], messages: List[Dict[str, Any]]) -> List[Path]:
        """storage/raw/slack/{채널명}/YYYY-MM-DD.json 으로 날짜(KST)별 저장"""
        channel_dir = raw_dir / channel["name"]
        channel_dir.mkdir(parents=True, exist_ok=True)

        by_date: Dict[str, List[Dict[str, Any]]] = {}
        for m in messages:
            day = datetime.fromtimestamp(float(m["ts"]), KST).strftime("%Y-%m-%d")
            by_date.setdefault(day, []).append(m)

        saved = []
        fetched_at = datetime.now(KST).isoformat(timespec="seconds")
        for day, msgs in sorted(by_date.items()):
            path = channel_dir / f"{day}.json"
            payload = {
                "channel": {"id": channel["id"], "name": channel["name"]},
                "date": day,
                "fetched_at": fetched_at,
                "message_count": len(msgs),
                "messages": msgs,
            }
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            saved.append(path)
        return saved
