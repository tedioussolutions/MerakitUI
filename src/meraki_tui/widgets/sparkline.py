# widgets/sparkline.py — Sparkline Visualization Widget
from textual.app import ComposeResult
from textual.widgets import Label
from textual.containers import Container
from typing import List, Callable, Optional
from ..utils import make_sparkline, format_kbps


class SparklineWidget(Container):
    def __init__(self, data: Optional[List[float]] = None,
                 label: str = "Bandwidth",
                 unit_formatter: Callable = format_kbps,
                 width: int = 40, **kwargs):
        super().__init__(**kwargs)
        self._data = data or []
        self._label = label
        self._formatter = unit_formatter
        self._width = width

    def compose(self) -> ComposeResult:
        yield Label(self._label, id="spark-label")
        yield Label("", id="spark-line")
        yield Label("", id="spark-stats")

    def on_mount(self) -> None:
        self._render()

    def update_data(self, data: List[float]) -> None:
        self._data = data
        self._render()

    def _render(self) -> None:
        if not self._data:
            self.query_one("#spark-line").update("─" * self._width)
            self.query_one("#spark-stats").update("Now: — · Peak: — · Avg: —")
            return
        self.query_one("#spark-line").update(make_sparkline(self._data, self._width))
        current = self._data[-1]
        peak = max(self._data)
        avg = sum(self._data) / len(self._data)
        self.query_one("#spark-stats").update(
            f"Now: {self._formatter(current)} · "
            f"Peak: {self._formatter(peak)} · "
            f"Avg: {self._formatter(avg)}"
        )
