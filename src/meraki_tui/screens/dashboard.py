# screens/dashboard.py — Device Management Dashboard
from textual.app import ComposeResult
from textual.widgets import DataTable, Input, Label, Button
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual import work
from ..api_client import get_api_client
from ..models import Organization, Network, Device, DeviceStatus
from ..utils import format_relative_time, truncate


class DeviceSummaryBar(Container):
    def compose(self) -> ComposeResult:
        yield Label("", id="summary-online")
        yield Label("", id="summary-offline")
        yield Label("", id="summary-alerting")

    def update(self, online: int, offline: int, alerting: int) -> None:
        self.query_one("#summary-online").update(f"🟢 Online: {online}")
        self.query_one("#summary-offline").update(f"🔴 Offline: {offline}")
        self.query_one("#summary-alerting").update(f"🟡 Alerting: {alerting}")


class DeviceDetailModal(ModalScreen):
    def __init__(self, device: Device):
        super().__init__()
        self.device = device

    def compose(self) -> ComposeResult:
        d = self.device
        with Container(id="modal-container"):
            yield Label(f"{d.device_type_icon} {d.name}", id="modal-title")
            yield Label(f"Serial: {d.serial}")
            yield Label(f"Model: {d.model}")
            yield Label(f"Status: {d.status_icon} {d.status.value}")
            yield Label(f"IP: {d.ip}")
            yield Label(f"MAC: {d.mac}")
            yield Label(f"Firmware: {d.firmware}")
            yield Label(f"WAN1: {d.wan1_ip or 'N/A'}")
            yield Label(f"WAN2: {d.wan2_ip or 'N/A'}")
            yield Label(f"Last Seen: {format_relative_time(d.last_reported)}")
            yield Label(f"Tags: {', '.join(d.tags) or 'None'}")
            yield Button("Close", id="close-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()


class DashboardScreen(Container):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._org = None
        self._network = None
        self._devices = []
        self._filter = ""

    def compose(self) -> ComposeResult:
        yield DeviceSummaryBar(id="summary-bar")
        yield Input(placeholder="Filter by name, model, IP, serial…", id="filter-input")
        yield DataTable(id="device-table")

    def on_mount(self) -> None:
        table = self.query_one("#device-table", DataTable)
        table.add_columns("", "Name", "Model", "Status", "IP", "Firmware", "Last Seen")

    def update_context(self, org: Organization, network: Network) -> None:
        self._org = org
        self._network = network
        self._load_devices()

    @work(exclusive=True)
    async def _load_devices(self) -> None:
        if not self._org: return
        client = get_api_client()
        self._devices = await client.get_org_device_statuses(self._org.id)
        self._render_table()

    def _render_table(self) -> None:
        table = self.query_one("#device-table", DataTable)
        table.clear()
        filtered = [d for d in self._devices
                    if not self._filter or self._filter.lower() in
                    f"{d.name} {d.model} {d.ip} {d.serial} {d.mac}".lower()]
        online = sum(1 for d in filtered if d.status == DeviceStatus.ONLINE)
        offline = sum(1 for d in filtered if d.status == DeviceStatus.OFFLINE)
        alerting = sum(1 for d in filtered if d.status == DeviceStatus.ALERTING)
        self.query_one(DeviceSummaryBar).update(online, offline, alerting)
        for d in sorted(filtered, key=lambda x: (
                x.status != DeviceStatus.ALERTING,
                x.status != DeviceStatus.OFFLINE)):
            table.add_row(
                d.device_type_icon, truncate(d.name, 30), d.model,
                f"{d.status_icon} {d.status.value}", d.ip or "—",
                d.firmware or "—", format_relative_time(d.last_reported),
                key=d.serial
            )

    def on_input_changed(self, event: Input.Changed) -> None:
        self._filter = event.value
        self._render_table()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        device = next((d for d in self._devices if d.serial == event.row_key.value), None)
        if device:
            self.app.push_screen(DeviceDetailModal(device))

    def action_refresh(self) -> None:
        get_api_client().cache.invalidate_prefix("device_statuses:")
        self._load_devices()
