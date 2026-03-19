# widgets/status_bar.py — Bottom Status Bar Widget
from textual.app import ComposeResult
from textual.widgets import Label
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from datetime import datetime
from typing import Optional
from ..models import Organization, Network
from ..api_client import get_api_client


class StatusBarWidget(Container):
    countdown = reactive(30)
    auto_refresh = reactive(True)

    def __init__(self, refresh_interval: int = 30, **kwargs):
        super().__init__(**kwargs)
        self._refresh_interval = refresh_interval
        self.countdown = refresh_interval
        self._org_name = "No Org"
        self._network_name = "No Network"
        self._last_refresh = datetime.utcnow()

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label("", id="sb-context")
            yield Label("", id="sb-timer")
            yield Label("", id="sb-api-stats")

    def on_mount(self) -> None:
        self.set_interval(1.0, self._tick)
        self._update_display()

    def _tick(self) -> None:
        if self.auto_refresh:
            self.countdown -= 1
            if self.countdown <= 0:
                self.countdown = self._refresh_interval
                self._last_refresh = datetime.utcnow()
                try:
                    self.app.trigger_auto_refresh()
                except Exception:
                    pass
        self._update_display()

    def _update_display(self) -> None:
        client = get_api_client()
        self.query_one("#sb-context").update(
            f"Org: {self._org_name} | Net: {self._network_name}")
        icon = "▶" if self.auto_refresh else "⏸"
        self.query_one("#sb-timer").update(
            f"{icon} Refresh in: {self.countdown}s")
        self.query_one("#sb-api-stats").update(
            f"API calls: {client.api_call_count} | "
            f"Errors: {client.api_error_count} | "
            f"Cache: {client.cache.size} | "
            f"Last: {self._last_refresh.strftime('%H:%M:%S')}")

    def update_context(self, org: Optional[Organization], network: Optional[Network]) -> None:
        self._org_name = org.name if org else "No Org"
        self._network_name = network.name if network else "No Network"

    def mark_refreshed(self) -> None:
        self.countdown = self._refresh_interval
        self._last_refresh = datetime.utcnow()

    def toggle_auto_refresh(self) -> None:
        self.auto_refresh = not self.auto_refresh
