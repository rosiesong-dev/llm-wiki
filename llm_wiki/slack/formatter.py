from datetime import datetime
import re
from typing import Any, Dict, List
from llm_wiki.slack.client import KST

def clean_slack_text(text: str) -> str:
    """Slack mrkdwn을 일반 텍스트로 변환 (<url|label>, <@U..>, <#C..|name>, HTML 엔티티)"""
    text = text or ""
    text = re.sub(r"<(https?://[^|>]+)\|([^>]+)>", r"\2 (\1)", text)
    text = re.sub(r"<(https?://[^>]+)>", r"\1", text)
    text = re.sub(r"<@([A-Z0-9]+)(?:\|[^>]+)?>", r"@\1", text)
    text = re.sub(r"<#[A-Z0-9]+\|([^>]+)>", r"#\1", text)
    text = re.sub(r"<!(here|channel|everyone)>", r"@\1", text)
    return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")

def _author(m: Dict[str, Any]) -> str:
    return m.get("_user_name") or m.get("user") or m.get("username") or m.get("bot_id") or "unknown"

def _time(m: Dict[str, Any]) -> str:
    return datetime.fromtimestamp(float(m["ts"]), KST).strftime("%H:%M")

def _files(m: Dict[str, Any]) -> str:
    names = [f.get("name") or f.get("title") for f in m.get("files", []) if f.get("name") or f.get("title")]
    return f" [첨부: {', '.join(names)}]" if names else ""

def _is_noise(m: Dict[str, Any]) -> bool:
    # 입장·퇴장 등 시스템 메시지는 지식이 아니므로 제외
    return m.get("subtype") in {"channel_join", "channel_leave", "channel_topic", "channel_purpose", "bot_add"}

def day_to_llm_text(day: Dict[str, Any]) -> str:
    """LLM 입력용 대화 텍스트 (스레드 댓글은 들여쓰기)"""
    lines: List[str] = []
    for m in day["messages"]:
        if _is_noise(m):
            continue
        lines.append(f"[{_time(m)}] {_author(m)}: {clean_slack_text(m.get('text', ''))}{_files(m)}")
        for r in m.get("_replies", []):
            lines.append(f"    └ [{_time(r)}] {_author(r)}: {clean_slack_text(r.get('text', ''))}{_files(r)}")
    return "\n".join(lines)

def day_to_transcript_md(day: Dict[str, Any]) -> str:
    """위키에 그대로 붙일 원문 대화 섹션. 메시지(스레드) 단위 ### 제목으로 나눠 RAG 청크가 되도록 함"""
    out = ["## 원문 대화", "", "> Slack 원본 메시지를 그대로 옮긴 기록입니다. (LLM 요약 아님)", ""]
    for m in day["messages"]:
        if _is_noise(m):
            continue
        first_line = clean_slack_text(m.get("text", "")).strip().splitlines()[0:1] or [""]
        out.append(f"### [{_time(m)}] {_author(m)} - {first_line[0][:40]}")
        out.append("")
        out.append(clean_slack_text(m.get("text", "")).strip() + _files(m))
        for r in m.get("_replies", []):
            out.append("")
            out.append(f"> **↳ [{_time(r)}] {_author(r)}**: " + clean_slack_text(r.get("text", "")).strip().replace("\n", "\n> ") + _files(r))
        out.append("")
    return "\n".join(out)
