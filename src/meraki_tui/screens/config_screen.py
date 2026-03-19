# screens/config_screen.py — Configuration Tools Screen
from textual.app import ComposeResult
from textual.widgets import DataTable, TabbedContent, TabPane, Label, Button, Input, Switch
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual import work
from ..api_client import get_api_client
from ..models import Organization, Network, SSID
from ..utils import truncate


class EditSSIDModal(ModalScreen):
    def __init__(self, ssid: SSID):
        super().__init__()
        self.ssid = ssid

    def compose(self) -> ComposeResult:
        with Container(id="modal-container"):
            yield Label(f"Edit SSID #{self.ssid.number}", id="modal-title")
            yield Input(value=self.ssid.name, placeholder="SSID Name", id="ssid-name")
            with Horizontal():
                yield Label("Enabled:")
                yield Switch(value=self.ssid.enabled, id="ssid-enabled")
            with Horizontal():
                yield Label("Visible:")
                yield Switch(value=self.ssid.visible, id="ssid-visible")
            with Horizontal():
                yield Button("Save", id="save-btn", variant="primary")
                yield Button("Cancel", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        else:
            self.dismiss({
                "name": self.query_one("#ssid-name", Input).value,
                "enabled": self.query_one("#ssid-enabled", Switch).value,
                "visible": self.query_one("#ssid-visible", Switch).value,
            })


class ConfigScreen(Container):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._org = None
        self._network = None
        self._ssids = []

    def compose(self) -> ComposeResult:
        with TabbedContent():
            with TabPane("SSIDs", id="tab-ssids"):
                yield DataTable(id="ssids-table")
            with TabPane("Switch Ports", id="tab-ports"):
                yield DataTable(id="ports-table")
            with TabPane("Bulk Ops", id="tab-bulk"):
                yield Label("Bulk Operations", id="bulk-title")
                yield Button("Enable All SSIDs", id="enable-all-btn", variant="success")
                yield Button("Disable All SSIDs", id="disable-all-btn", variant="error")
                yield Label("", id="bulk-status")
            with TabPane("Action Batches", id="tab-batches"):
                yield Label("Recent action batches will appear here.", id="batches-label")

    def on_mount(self) -> None:
        st = self.query_one("#ssids-table", DataTable)
        st.add_columns("#", "Name", "Enabled", "Auth Mode", "Band", "Visible")
        pt = self.query_one("#ports-table", DataTable)
        pt.add_columns("Port", "Name", "Enabled", "Speed", "Duplex", "VLAN", "PoE")

    def update_context(self, org: Organization, network: Network) -> None:
        self._org = org
        self._network = network
        self._load_ssids()

    @work(exclusive=True)
    async def _load_ssids(self) -> None:
        if not self._network: return
        client = get_api_client()
        org_id = self._org.id if self._org else "global"
        self._ssids = await client.get_ssids(self._network.id, org_id)
        st = self.query_one("#ssids-table", DataTable)
        st.clear()
        for s in self._ssids:
            st.add_row(str(s.number), truncate(s.name, 30),
                "Yes" if s.enabled else "No",
                s.auth_mode, s.band_selection,
                "Yes" if s.visible else "No", key=str(s.number))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "ssids-table":
            ssid = next((s for s in self._ssids if str(s.number) == event.row_key.value), None)
            if ssid:
                self.app.push_screen(EditSSIDModal(ssid), self._handle_ssid_edit)

    def _handle_ssid_edit(self, result) -> None:
        if result:
            self.notify(f"SSID updated: {result['name']}")
            if self._network:
                get_api_client().cache.invalidate_prefix(f"ssids:{self._network.id}")
            self._load_ssids()

    def action_refresh(self) -> None:
        if self._network:
            get_api_client().cache.invalidate_prefix(f"ssids:{self._network.id}")
        self._load_ssids()
