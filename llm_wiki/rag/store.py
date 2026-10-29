import json
import logging
from pathlib import Path
import math
import re
from typing import Dict, List, Optional, Set, Tuple
import numpy as np
from llm_wiki.rag.embedder import EmbeddedChunk

logger = logging.getLogger(__name__)

KEYWORD_WEIGHT = 0.5        # 하이브리드 점수에서 키워드 일치율 비중
TRANSCRIPT_PENALTY = 0.85   # Slack 원문 대화 청크 가중치

class SearchResult:
    def __init__(self, chunk: EmbeddedChunk, score: float):
        self.chunk = chunk
        self.score = score

class VectorStore:
    def __init__(self, index_dir: Path):
        self.index_file = index_dir / "vector_index.json"
        self.chunks: List[EmbeddedChunk] = []
        self._load()

    def _load(self) -> None:
        if self.index_file.exists():
            try:
                data = json.loads(self.index_file.read_text(encoding="utf-8"))
                self.chunks = [EmbeddedChunk(**item) for item in data]
            except Exception as e:
                logger.warning(f"벡터 인덱스 로드 실패 {self.index_file}: {e}")
                self.chunks = []

    def clear(self) -> None:
        self.chunks = []

    def add_chunks(self, new_chunks: List[EmbeddedChunk]) -> None:
        self.chunks.extend(new_chunks)

    def save(self) -> None:
        self.index_file.parent.mkdir(parents=True, exist_ok=True)
        data = [c.model_dump() for c in self.chunks]
        self.index_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"벡터 인덱스 저장 완료: {self.index_file} (총 {len(self.chunks)}개 청크)")

    def _chunk_grams(self) -> List[Set[str]]:
        if getattr(self, "_grams_cache", None) is None or len(self._grams_cache) != len(self.chunks):
            self._grams_cache = [
                self._bigrams(f"{c.chunk.document_title} {c.chunk.section_title} {c.chunk.content}") for c in self.chunks
            ]
        return self._grams_cache

    @staticmethod
    def _bigrams(text: str) -> Set[str]:
        """어절별 글자 2-gram (한국어는 조사가 붙어 단어 일치가 어려우므로 2글자 단위로 비교)"""
        grams: Set[str] = set()
        for token in re.findall(r"[0-9A-Za-z가-힣]+", text.lower()):
            if len(token) == 1:
                continue
            grams.update(token[i:i + 2] for i in range(len(token) - 1))
        return grams

    def search(self, query_vec: List[float], top_k: int = 3, query_text: Optional[str] = None) -> List[SearchResult]:
        """하이브리드 검색: 코사인 유사도 + (query_text가 있으면) 키워드 2-gram 일치율

        - 임베딩만 쓰면 '회의' 같은 흔한 단어가 들어간 짧은 청크가 상위를 차지하므로 키워드 일치를 함께 반영
        - Slack 원문 대화 청크(메시지 1개 단위)는 수가 많아 정리된 페이지보다 약간 낮게 가중
        """
        if not self.chunks:
            return []

        q_arr = np.array(query_vec, dtype=np.float32)
        q_norm = np.linalg.norm(q_arr)
        if q_norm == 0:
            return []
        if len(self.chunks[0].embedding) != len(q_arr):
            # LLM 백엔드(임베딩 모델)를 바꾼 뒤 인덱스를 다시 만들지 않은 경우
            raise RuntimeError(
                f"벡터 인덱스의 임베딩 차원({len(self.chunks[0].embedding)})이 현재 임베딩 모델({len(q_arr)})과 다릅니다. "
                "'python main.py index'로 인덱스를 다시 만들어 주세요."
            )
        q_grams = self._bigrams(query_text) if query_text else set()
        idf: Dict[str, float] = {}
        if q_grams:
            # 흔한 2-gram('회의' 등)보다 드문 2-gram('잡기', '이사' 등)에 더 큰 가중치 (IDF)
            chunk_grams = self._chunk_grams()
            n = len(chunk_grams)
            for g in q_grams:
                df = sum(1 for cg in chunk_grams if g in cg)
                idf[g] = math.log((n + 1) / (df + 1)) if df else 0.0   # 위키에 없는 2-gram(조사 등)은 무시
        idf_total = sum(idf.values())

        results: List[Tuple[EmbeddedChunk, float]] = []
        for i, chunk in enumerate(self.chunks):
            c_arr = np.array(chunk.embedding, dtype=np.float32)
            c_norm = np.linalg.norm(c_arr)
            score = 0.0 if c_norm == 0 else float(np.dot(q_arr, c_arr) / (q_norm * c_norm))
            if idf_total:
                c = chunk.chunk
                keyword = sum(w for g, w in idf.items() if g in self._grams_cache[i]) / idf_total
                score = (1 - KEYWORD_WEIGHT) * score + KEYWORD_WEIGHT * keyword
                if c.section_title.startswith("["):   # Slack 원문 대화 메시지 청크
                    score *= TRANSCRIPT_PENALTY
            results.append((chunk, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return [SearchResult(chunk=c, score=s) for c, s in results[:top_k]]

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)
