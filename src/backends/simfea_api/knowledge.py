"""Knowledge base: document ingest, chunk, search, and RAG query helpers."""

import re
from pathlib import Path

import numpy as np

try:
    from ..inference.infer_text_api import generate_embedding
    from ..simfea_api.knowledge_store import (
        delete_document,
        get_all_chunks_with_embeddings,
        insert_document,
        list_documents,
    )
    from ..simfea_api.logger import create_logger
except ImportError:
    from inference.infer_text_api import generate_embedding
    from simfea_api.knowledge_store import (
        delete_document,
        get_all_chunks_with_embeddings,
        insert_document,
        list_documents,
    )
    from simfea_api.logger import create_logger

log = create_logger("knowledge")

_CHUNK_SIZE = 500
_CHUNK_OVERLAP = 50


def _read_text_file(file_path: Path) -> str:
    """Read a plain-text or markdown file."""
    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return file_path.read_text(encoding="gbk", errors="replace")


def _read_pdf_file(file_path: Path) -> str:
    """Extract text from a PDF file using PyPDF2."""
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        raise ImportError(
            "需要 PyPDF2 库来读取 PDF 文件。请运行: pip install PyPDF2"
        )

    reader = PdfReader(str(file_path))
    pages: list[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n\n".join(pages)


def _extract_text(file_path: Path) -> str:
    """Extract text from a supported file type."""
    suffix = file_path.suffix.lower()
    if suffix in (".txt", ".md", ".markdown"):
        return _read_text_file(file_path)
    elif suffix == ".pdf":
        return _read_pdf_file(file_path)
    else:
        raise ValueError(f"不支持的文件格式: {suffix}。支持 .txt, .md, .pdf")


def _chunk_text(text: str, chunk_size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks by character count.

    Prefers splitting at paragraph or sentence boundaries when possible.
    """
    if not text.strip():
        return []

    paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current) + len(para) + 2 <= chunk_size:
            current = f"{current}\n\n{para}" if current else para
        else:
            if current:
                chunks.append(current.strip())
            # If a single paragraph exceeds chunk_size, split by sentence
            if len(para) > chunk_size:
                sentences = re.split(r"(?<=[。.!?！？])\s*", para)
                current = ""
                for sent in sentences:
                    sent = sent.strip()
                    if not sent:
                        continue
                    if len(current) + len(sent) <= chunk_size:
                        current = f"{current}{sent}" if current else sent
                    else:
                        if current:
                            chunks.append(current.strip())
                        current = sent
                if current:
                    current = current  # will be added on next iteration or at end
            else:
                current = para

    if current.strip():
        chunks.append(current.strip())

    # Apply overlap
    if overlap > 0 and len(chunks) > 1:
        overlapped: list[str] = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_tail = chunks[i - 1][-overlap:] if len(chunks[i - 1]) > overlap else chunks[i - 1]
            overlapped.append(prev_tail + "\n" + chunks[i])
        chunks = overlapped

    return chunks


def ingest_document(file_path: Path) -> dict:
    """Read, chunk, embed, and store a document. Returns doc info."""
    name = file_path.name
    text = _extract_text(file_path)
    chunks = _chunk_text(text)

    if not chunks:
        raise ValueError(f"文件 '{name}' 没有可提取的文本内容。")

    log.info(f"Ingesting '{name}': {len(chunks)} chunks")
    embeddings = []
    for i, chunk in enumerate(chunks):
        try:
            emb = generate_embedding(chunk)
            embeddings.append(emb)
        except Exception as exc:
            log.error(f"Failed to embed chunk {i} of '{name}': {exc}")
            raise

    doc_id = insert_document(
        name=name,
        chunks=chunks,
        embeddings=embeddings,
        original_path=str(file_path),
    )

    return {
        "doc_id": doc_id,
        "name": name,
        "chunk_count": len(chunks),
    }


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors using numpy."""
    a_arr = np.array(a, dtype=np.float64)
    b_arr = np.array(b, dtype=np.float64)
    norm_a = np.linalg.norm(a_arr)
    norm_b = np.linalg.norm(b_arr)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / (norm_a * norm_b))


def search_knowledge(query: str, top_k: int = 5, doc_ids: list[str] | None = None) -> list[dict]:
    """Search knowledge base for chunks relevant to *query*.

    If *doc_ids* is provided, only search chunks from those documents.

    Returns a list of ``{"text": "...", "score": 0.95, "source": "doc.pdf"}`` dicts.
    """
    if not query.strip():
        return []

    query_embedding = generate_embedding(query)
    if not query_embedding:
        return []

    all_chunks = get_all_chunks_with_embeddings(doc_ids=doc_ids)
    if not all_chunks:
        return []

    scored: list[tuple[float, dict]] = []
    for chunk in all_chunks:
        score = _cosine_similarity(query_embedding, chunk["embedding"])
        scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)

    results: list[dict] = []
    for score, chunk in scored[:top_k]:
        results.append({
            "text": chunk["text"],
            "score": round(score, 4),
            "source": chunk["doc_name"],
        })

    return results
