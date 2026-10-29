from typing import List
from pydantic import BaseModel
from llm_wiki.llm.client import BaseLLMClient
from llm_wiki.rag.chunker import TextChunk

class EmbeddedChunk(BaseModel):
    chunk: TextChunk
    embedding: List[float]

class Embedder:
    def __init__(self, llm_client: BaseLLMClient):
        self.llm_client = llm_client

    def embed_chunk(self, chunk: TextChunk) -> EmbeddedChunk:
        """청크 텍스트에 대한 벡터 임베딩 생성"""
        text_to_embed = f"{chunk.document_title}: {chunk.section_title}\n{chunk.content}"
        embedding = self.llm_client.generate_embedding(text_to_embed)
        return EmbeddedChunk(chunk=chunk, embedding=embedding)
