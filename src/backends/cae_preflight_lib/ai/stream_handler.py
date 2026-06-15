# stream_handler.py
"""
StreamHandler — SSE / token-by-token 流式输出处理

使用 rich.live.Live 实现实时刷新显示。
"""
from __future__ import annotations

from typing import Iterator, Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text


class StreamHandler:
    """
    流式输出处理器。

    使用 rich.live.Live 实时显示 AI 生成内容，
    每个 token 更新面板内容，提升用户体验。
    """

    def __init__(self, console: Optional[Console] = None) -> None:
        self._console = console or Console()
        self._text_buffer: list[str] = []

    def stream_tokens(self, token_iterator: Iterator[str]) -> str:
        """
        消费 token 迭代器，实时显示在终端。

        Args:
            token_iterator: LLM 返回的 token 迭代器

        Returns:
            完整的生成文本
        """
        self._text_buffer = []
        full_text: list[str] = []

        def make_panel() -> Panel:
            text = Text("".join(full_text), style="cyan")
            return Panel(text, title="AI 正在生成...", border_style="cyan")

        try:
            with Live(make_panel(), console=self._console, refresh_per_second=10) as live:
                for token in token_iterator:
                    full_text.append(token)
                    self._text_buffer.append(token)
                    live.update(make_panel())
        except KeyboardInterrupt:
            pass  # 用户中断，优雅退出

        return "".join(self._text_buffer)

    def clear(self) -> None:
        """清空内部缓冲区。"""
        self._text_buffer.clear()
