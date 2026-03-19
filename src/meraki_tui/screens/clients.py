# screens/clients.py — Client Monitoring Screen
from textual.app import ComposeResult
from textual.widgets import DataTable, Input, Label, Button, Switch
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual import work
from ..api_client import get_api_client
from ..models import Organization, Network, Client
from ..utils import format_relative_time, truncate


class ClientDetailModal(ModalScreen):
    def __init__(self, client: Client):
        super().__init__()
        self.client = client

    def compose(self) -> ComposeResult:
        c = self.client
        with Container(id="modal-container"):
            yield Label(f"{c.status_icon} {c.display_name}", id="modal-title")
            yield Label(f"MAC: {c.mac}")
            yield Label(f"IP: {c.ip or 'N/A'}")
            yield Label(f"IPv6: {c.ip6 or 'N/A'}")
            yield Label(f"SSID: {c.ssid or 'Wired'}")
            yield Label(f"VLAN: {c.vlan}")
            yield Label(f"OS: {c.os or 'Unknown'}")
            yield Label(f"Manufacturer: {c.manufacturer or 'Unknown'}")
            yield Label(f"Usage: {c.usage_human}")
            yield Label(f"Last Seen: {format_relative_time(c.last_seen)}")
            yield Button("Close", id="close-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()


class ClientsScreen(Container):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._org = None
        self._network = None
        self._clients = []
        self._filter = ""
        self._online_only = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="clients-toolbar"):
            yield Input(placeholder="Search MAC, IP, name, SSID…", id="search-input")
            yield Label("Online only:")
            yield Switch(id="online-toggle")
        yield Label("", id="clients-stats")
        yield DataTable(id="clients-table")

    def on_mount(self) -> None:
        table = self.query_one("#clients-table", DataTable)
        table.add_columns("", "Name", "MAC", "IP", "SSID", "VLAN", "Usage", "Last Seen")

    def update_context(self, org: Organization, network: Network) -> None:
        self._org = org
        self._network = network
        self._load_clients()

    @work(exclusive=True)
    async def _load_clients(self) -> None:
        if not self._network: return
        client = get_api_client()
        self._clients = await client.get_network_clients(self._network.id)
        self._render_table()

    def _render_table(self) -> None:
        table = self.query_one("#clients-table", DataTable)
        table.clear()
        filtered = self._clients
        if self._filter:
            q = self._filter.lower()
            filtered = [c for c in filtered if q in
                f"{c.display_name} {c.mac} {c.ip} {c.ssid} {c.user} {c.os} {c.manufacturer}".lower()]
        if self._online_only:
            filtered = [c for c in filtered if c.status == "Online"]
        filtered.sort(key=lambda c: c.sent_bytes + c.recv_bytes, reverse=True)
        online = sum(1 for c in filtered if c.status == "Online")
        total_bytes = sum(c.sent_bytes + c.recv_bytes for c in filtered)
        from ..utils import format_bytes
        self.query_one("#clients-stats").update(
            f"Showing {len(filtered)} clients · {online} online · Total: {format_bytes(total_bytes)}")
        for c in filtered:
            table.add_row(
                c.status_icon, truncate(c.display_name, 25), c.mac,
                c.ip or "—", c.ssid or "Wired", str(c.vlan),
                c.usage_human, format_relative_time(c.last_seen),
                key=c.id
            )

    def on_input_changed(self, event: Input.Changed) -> None:
        self._filter = event.value
        self._render_table()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        self._online_only = event.value
        self._render_table()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        client = next((c for c in self._clients if c.id == event.row_key.value), None)
        if client:
            self.app.push_screen(ClientDetailModal(client))

    def action_refresh(self) -> None:
        if self._network:
            get_api_client().cache.invalidate_prefix(f"clients:{self._network.id}")
        self._load_clients()
