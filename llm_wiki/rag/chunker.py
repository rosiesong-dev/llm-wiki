from typing import List
from pydantic import BaseModel
from llm_wiki.wiki.document import WikiDocument

class TextChunk(BaseModel):
    document_title: str
    section_title: str
    content: str

class MarkdownChunker:
    @staticmethod
    def chunk_document(doc: WikiDocument) -> List[TextChunk]:
        """위키 마크다운 문서를 H2/H3 섹션 및 단락 단위로 분할"""
        chunks: List[TextChunk] = []
        lines = doc.body.splitlines()

        current_section = "기본"
        current_buf: List[str] = []

        for line in lines:
            if line.startswith("## ") or line.startswith("### "):
                if current_buf:
                    content = "\n".join(current_buf).strip()
                    if content:
                        chunks.append(TextChunk(
                            document_title=doc.frontmatter.title,
                            section_title=current_section,
                            content=content
                        ))
                    current_buf.clear()
                current_section = line.lstrip("#").strip()
            else:
                current_buf.append(line)

        if current_buf:
            content = "\n".join(current_buf).strip()
            if content:
                chunks.append(TextChunk(
                    document_title=doc.frontmatter.title,
                    section_title=current_section,
                    content=content
                ))

        if not chunks and doc.body.strip():
            chunks.append(TextChunk(
                document_title=doc.frontmatter.title,
                section_title="전체",
                content=doc.body.strip()
            ))

        return chunks
