import html
import re
from typing import Optional
from pydantic import BaseModel

class ConfluencePage(BaseModel):
    id: str
    title: str
    space_id: Optional[str] = None
    status: Optional[str] = None
    author_id: Optional[str] = None
    created_at: Optional[str] = None
    version_number: Optional[int] = None
    body_storage_value: str

    def to_plain_text(self) -> str:
        """Storage 포맷(XHTML)을 LLM 입력용 텍스트로 변환 (헤딩은 #, 목록은 -, 표 셀은 | 구분)

        태그를 그대로 보내면 토큰이 2~3배로 늘어 로컬 LLM에서 느려지고 컨텍스트가 잘린다.
        """
        # 태그 사이 소스 줄바꿈 제거 (줄바꿈은 아래에서 블록 태그 기준으로만 생성)
        t = re.sub(r">\s+<", "><", self.body_storage_value)
        # 셀 안의 <p>/<br>이 줄바꿈으로 바뀌어 행이 흩어지지 않도록 셀 내용을 한 줄로 합침
        t = re.sub(r"<t([dh])(\s[^>]*)?>(.*?)</t\1>", lambda m: re.sub(r"<[^>]+>", " ", m.group(3)) + " | ", t, flags=re.S)
        t = re.sub(r"<tr[^>]*>", "\n| ", t)
        t = re.sub(r"<h(\d)[^>]*>", lambda m: "\n" + "#" * int(m.group(1)) + " ", t)
        t = re.sub(r"<li[^>]*>", "\n- ", t)
        t = re.sub(r"<(br|/p|/h\d|/ul|/ol|/table)[^>]*>", "\n", t)
        t = re.sub(r"<[^>]+>", "", t)
        t = html.unescape(t)
        lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in t.splitlines()]
        return "\n".join(line for line in lines if line)
