import json
import os

import requests

try:
    from ..simfea_api.logger import create_logger
except ImportError:
    from simfea_api.logger import create_logger

log = create_logger("inference")

_OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_LLM_MODEL = os.getenv("SIMFEA_LLM_MODEL", "qwen2.5:7b")
_EMBEDDING_MODEL = os.getenv("SIMFEA_EMBEDDING_MODEL", "nomic-embed-text")
_REQUEST_TIMEOUT = int(os.getenv("SIMFEA_LLM_TIMEOUT", "120"))


def _ollama_chat(messages: list[dict], model: str | None = None) -> str:
    """Send a chat request to Ollama and return the assistant's reply."""
    url = f"{_OLLAMA_BASE}/api/chat"
    payload = {
        "model": model or _LLM_MODEL,
        "messages": messages,
        "stream": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()["message"]["content"]
    except requests.exceptions.ConnectionError:
        log.error(f"Ollama not reachable at {_OLLAMA_BASE}")
        raise ConnectionError(
            f"无法连接 Ollama ({_OLLAMA_BASE})。请确认 Ollama 已启动。"
        )
    except requests.exceptions.Timeout:
        log.error(f"Ollama request timed out after {_REQUEST_TIMEOUT}s")
        raise TimeoutError(f"Ollama 请求超时（{_REQUEST_TIMEOUT} 秒）。")
    except requests.exceptions.HTTPError as exc:
        log.error(f"Ollama HTTP error: {exc}")
        raise RuntimeError(f"Ollama 返回错误：{exc}")


def _ollama_embed(text: str, model: str | None = None) -> list[float]:
    """Get embedding vector for text from Ollama."""
    url = f"{_OLLAMA_BASE}/api/embeddings"
    payload = {
        "model": model or _EMBEDDING_MODEL,
        "prompt": text,
    }
    try:
        resp = requests.post(url, json=payload, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()["embedding"]
    except requests.exceptions.ConnectionError:
        log.error(f"Ollama not reachable at {_OLLAMA_BASE}")
        raise ConnectionError(
            f"无法连接 Ollama ({_OLLAMA_BASE})。请确认 Ollama 已启动。"
        )


def completions(data: dict) -> dict:
    """Handle the /v1/completions endpoint.

    Expects ``{"prompt": "..."}`` or ``{"prompt": "...", "system": "..."}``.
    """
    try:
        prompt: str = data["prompt"]
        system_prompt: str = data.get("system", "")
    except KeyError:
        log.error("Expected format {'prompt':'text string here'}")
        raise ValueError("请求格式错误：缺少 'prompt' 字段")

    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        reply = _ollama_chat(messages)
        log.info(f"Prompt: '{prompt[:80]}...' → Reply: '{reply[:80]}...'")
        return {"message": reply}
    except (ConnectionError, TimeoutError, RuntimeError) as exc:
        log.error(str(exc))
        return {"message": f"[错误] {exc}"}


def generate_embedding(text: str) -> list[float]:
    """Generate an embedding vector for *text*.

    Used by knowledge.py for document chunk indexing.
    """
    if not text.strip():
        return []
    return _ollama_embed(text)


def chat_with_context(
    user_question: str,
    context_chunks: list[dict],
    system_prompt: str = "",
    model: str | None = None,
) -> str:
    """Chat with context chunks (RAG-style).

    *context_chunks* is a list of ``{"text": "...", "source": "..."}`` dicts.

    Returns the assistant's text reply.
    """
    if not system_prompt:
        system_prompt = (
            "你是一个 FEA 仿真学习助手。请基于提供的资料内容回答用户的问题。"
            "如果资料中没有相关信息，请诚实地说明。引用资料时标注来源。"
        )

    context_text = "\n\n---\n\n".join(
        f"[来源: {chunk.get('source', '未知')}]\n{chunk['text']}"
        for chunk in context_chunks
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"参考资料：\n\n{context_text}\n\n用户问题：{user_question}",
        },
    ]

    return _ollama_chat(messages, model=model)


def translate_task_to_run(description: str, available_solvers: list[dict]) -> dict:
    """Translate a natural-language simulation task into a solver configuration.

    *available_solvers* is a list of ``{"alias": "...", "label": "...", "kind": "..."}`` dicts.

    Returns a dict with keys: ``solver``, ``case_name``, ``explanation``, ``suggested_params``.
    """
    solver_list = "\n".join(
        f"- {s['alias']} ({s.get('label', s['alias'])}): {s.get('kind', '求解器')}"
        for s in available_solvers
    )

    system_prompt = (
        "你是一个 FEA 仿真任务分析助手。用户会用自然语言描述一个仿真任务，"
        "你需要分析任务、选择合适的求解器、提取参数。\n\n"
        "回复必须是严格的 JSON 格式，不要包含任何其他文字：\n"
        "{\n"
        '  "solver": "求解器 alias",\n'
        '  "case_name": "建议的算例名称（英文，snake_case）",\n'
        '  "explanation": "你的分析过程（中文，1-2 句）",\n'
        '  "suggested_params": {\n'
        '    "参数名": "参数值（带单位）"\n'
        "  }\n"
        "}\n\n"
        f"当前可用的求解器：\n{solver_list}"
    )

    prompt = (
        f"用户描述：{description}\n\n"
        "请分析这个仿真任务，选择合适的求解器和参数。"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    try:
        raw = _ollama_chat(messages)
        # Try to extract JSON from the response (LLM may wrap it in markdown)
        json_start = raw.find("{")
        json_end = raw.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            raw = raw[json_start:json_end]
        result = json.loads(raw)
        log.info(f"Translated task '{description[:60]}...' → solver={result.get('solver', '?')}")
        return result
    except (json.JSONDecodeError, KeyError) as exc:
        log.error(f"Failed to parse LLM task translation: {exc}")
        return {
            "solver": available_solvers[0]["alias"] if available_solvers else "",
            "case_name": "custom_task",
            "explanation": f"无法解析 LLM 响应，使用默认配置。（错误：{exc}）",
            "suggested_params": {},
        }
