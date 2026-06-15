"""Knowledge base endpoints."""

import json
from pathlib import Path

from fastapi import APIRouter, Body, File, HTTPException, UploadFile

try:
    from ..simfea_api.config import settings
    from ..simfea_api.knowledge import (
        ingest_document as knowledge_ingest_document,
        search_knowledge as knowledge_search,
        list_documents as knowledge_list_documents,
    )
    from ..simfea_api.knowledge_store import delete_document as knowledge_delete_document
    from ..simfea_api.security import safe_child_dir, safe_upload_path
    from ..simfea_api.run_archive import read_optional_text
    from ..inference import infer_text_api
except ImportError:
    from simfea_api.config import settings
    from simfea_api.knowledge import (
        ingest_document as knowledge_ingest_document,
        search_knowledge as knowledge_search,
        list_documents as knowledge_list_documents,
    )
    from simfea_api.knowledge_store import delete_document as knowledge_delete_document
    from simfea_api.security import safe_child_dir, safe_upload_path
    from simfea_api.run_archive import read_optional_text
    from inference import infer_text_api

knowledge_router = APIRouter(prefix="/v1")


@knowledge_router.post("/knowledge/documents")
async def upload_knowledge_document(file: UploadFile = File(...)):
    """Upload a document (PDF/MD/TXT) to the knowledge base."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名。")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".pdf", ".md", ".txt", ".markdown"):
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {suffix}。支持 .pdf, .md, .txt",
        )

    tmp_dir = Path(settings().runs_root).parent / "knowledge" / "uploads"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        tmp_path = safe_upload_path(tmp_dir, file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        content = await file.read()
        tmp_path.write_bytes(content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {exc}")

    try:
        doc_info = knowledge_ingest_document(tmp_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    return {
        "message": f"文档 '{file.filename}' 已上传并处理完成。",
        "data": doc_info,
    }


@knowledge_router.post("/knowledge/documents/by-path")
def ingest_knowledge_by_path(payload: dict = Body(...)):
    """Index a document by its local file path."""
    file_path = payload.get("path", "").strip()
    if not file_path:
        raise HTTPException(status_code=400, detail="缺少 'path' 字段。")
    p = Path(file_path).expanduser().resolve()
    if not p.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")
    try:
        doc_info = knowledge_ingest_document(p)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"message": f"已索引: {p.name}", "data": doc_info}


@knowledge_router.get("/knowledge/documents")
def list_knowledge_documents():
    """List all documents in the knowledge base."""
    docs = knowledge_list_documents()
    return {
        "message": f"共 {len(docs)} 份文档。",
        "data": {"documents": docs},
    }


@knowledge_router.delete("/knowledge/documents/{doc_id}")
def delete_knowledge_document(doc_id: str):
    """Delete a document and all its chunks from the knowledge base."""
    deleted = knowledge_delete_document(doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"文档 '{doc_id}' 不存在。")
    return {
        "message": f"文档 '{doc_id}' 已删除。",
        "data": {"deleted": True},
    }


@knowledge_router.post("/knowledge/ask")
def ask_knowledge(payload: dict = Body(...)):
    """RAG query: retrieve relevant knowledge + run context, then answer via LLM."""
    run_id = payload.get("run_id", "")
    question = payload.get("question", "").strip()
    doc_ids = payload.get("doc_ids") or None

    if not question:
        raise HTTPException(status_code=400, detail="缺少 'question' 字段。")

    try:
        search_results = knowledge_search(question, top_k=5, doc_ids=doc_ids)
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    run_context = ""
    if run_id:
        try:
            run_dir = safe_child_dir(Path(settings().runs_root), run_id)
            note = read_optional_text(run_dir / "note.md", "")
            report = read_optional_text(run_dir / "learning_report.md", "")
            meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8")) if (run_dir / "meta.json").exists() else {}
            run_context = (
                f"运行状态: {meta.get('status', '未知')}\n"
                f"求解器: {meta.get('solver', '未知')}\n"
                f"算例: {meta.get('case_name', '未知')}\n"
                f"学习笔记: {note[:500] if note else '无'}\n"
                f"学习报告: {report[:500] if report else '无'}\n"
            )
        except Exception:
            run_context = ""

    context_chunks = [{"text": r["text"], "source": r["source"]} for r in search_results]
    if run_context:
        context_chunks.insert(0, {"text": run_context, "source": "当前运行上下文"})

    try:
        answer = infer_text_api.chat_with_context(question, context_chunks)
    except (ConnectionError, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return {
        "message": "查询完成。",
        "data": {
            "answer": answer,
            "sources": [
                {"text": r["text"][:200], "source": r["source"], "score": r["score"]}
                for r in search_results
            ],
        },
    }
