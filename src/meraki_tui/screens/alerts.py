# screens/alerts.py — Alert System Screen
from textual.app import ComposeResult
from textual.widgets import DataTable, TabbedContent, TabPane, Label, Button, Input
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual import work
import asyncio
from datetime import datetime as dt_module
from ..api_client import get_api_client
from ..models import Organization, Network, AlertSeverity
from ..utils import format_relative_time, truncate


class AddWebhookModal(ModalScreen):
    def compose(self) -> ComposeResult:
        with Container(id="modal-container"):
            yield Label("Add Webhook Server", id="modal-title")
            yield Input(placeholder="Name", id="webhook-name")
            yield Input(placeholder="URL (https://…)", id="webhook-url")
            yield Input(placeholder="Shared Secret (optional)", id="webhook-secret")
            with Horizontal():
                yield Button("Add", id="add-btn", variant="primary")
                yield Button("Cancel", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        else:
            self.dismiss({
                "name": self.query_one("#webhook-name", Input).value,
                "url": self.query_one("#webhook-url", Input).value,
                "secret": self.query_one("#webhook-secret", Input).value,
            })


class AlertsScreen(Container):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._org = None
        self._network = None

    def compose(self) -> ComposeResult:
        yield Label("", id="alert-stats")
        with TabbedContent():
            with TabPane("Incident Log", id="tab-log"):
                yield DataTable(id="alerts-table")
            with TabPane("Webhooks", id="tab-webhooks"):
                yield Button("+ Add Webhook", id="add-webhook-btn")
                yield DataTable(id="webhooks-table")
            with TabPane("Alert Settings", id="tab-settings"):
                yield Label("Alert settings will appear here.", id="alert-settings-label")

    def on_mount(self) -> None:
        at = self.query_one("#alerts-table", DataTable)
        at.add_columns("", "Time", "Type", "Device", "Message", "Age")
        wt = self.query_one("#webhooks-table", DataTable)
        wt.add_columns("Name", "URL", "ID")

    def update_context(self, org: Organization, network: Network) -> None:
        self._org = org
        self._network = network
        self._load_all()

    @work(exclusive=True)
    async def _load_all(self) -> None:
        if not self._network: return
        client = get_api_client()
        org_id = self._org.id if self._org else "global"
        results = await asyncio.gather(
            client.get_network_events(self._network.id, org_id, "appliance"),
            client.get_network_events(self._network.id, org_id, "wireless"),
            client.get_network_events(self._network.id, org_id, "switch"),
            return_exceptions=True
        )
        all_alerts = []
        for r in results:
            if not isinstance(r, Exception):
                all_alerts.extend(r)
        all_alerts.sort(key=lambda a: a.occurred_at or dt_module.min, reverse=True)
        critical = sum(1 for a in all_alerts if a.severity == AlertSeverity.CRITICAL)
        warning = sum(1 for a in all_alerts if a.severity == AlertSeverity.WARNING)
        self.query_one("#alert-stats").update(
            f"Total: {len(all_alerts)} · Critical: {critical} · Warning: {warning}")
        at = self.query_one("#alerts-table", DataTable)
        at.clear()
        for a in all_alerts[:100]:
            at.add_row(a.severity_icon, format_relative_time(a.occurred_at),
                a.alert_type, truncate(a.device_name, 20),
                truncate(a.message, 50), a.age_human)

    def action_refresh(self) -> None:
        if self._network:
            for pt in ["appliance","wireless","switch"]:
                get_api_client().cache.invalidate_prefix(f"events:{self._network.id}:{pt}")
        self._load_all()
