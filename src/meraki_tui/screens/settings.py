# screens/settings.py — App Settings and Saved Views Screen
from textual.app import ComposeResult
from textual.widgets import (DataTable, TabbedContent, TabPane, Label,
    Button, Input, Select)
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual import work
from ..config import get_config
from ..utils import truncate


class SaveViewModal(ModalScreen):
    def compose(self) -> ComposeResult:
        with Container(id="modal-container"):
            yield Label("Save Current View", id="modal-title")
            yield Input(placeholder="View name…", id="view-name-input")
            with Horizontal():
                yield Button("Save", id="save-btn", variant="primary")
                yield Button("Cancel", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        else:
            self.dismiss(self.query_one("#view-name-input", Input).value)


class SettingsScreen(Container):
    def compose(self) -> ComposeResult:
        with TabbedContent():
            with TabPane("General", id="tab-general"):
                with Vertical():
                    yield Label("Refresh Interval (seconds):")
                    yield Input(id="refresh-interval", placeholder="30")
                    yield Label("Theme:")
                    yield Select(
                        [("Dark", "dark"), ("Light", "light"), ("Nord", "nord")],
                        id="theme-select"
                    )
                    yield Button("Save Settings", id="save-general-btn", variant="primary")
            with TabPane("API Config", id="tab-api"):
                with Vertical():
                    yield Label("API Key:")
                    yield Input(id="api-key-input", password=True,
                                placeholder="Enter Meraki API key…")
                    yield Label("Default Org ID:")
                    yield Input(id="default-org-input", placeholder="Optional")
                    yield Label("Default Network ID:")
                    yield Input(id="default-network-input", placeholder="Optional")
                    yield Button("Save API Config", id="save-api-btn", variant="primary")
            with TabPane("Saved Views", id="tab-views"):
                yield DataTable(id="views-table")
                yield Button("Save Current View", id="save-view-btn")

    def on_mount(self) -> None:
        config = get_config()
        self.query_one("#refresh-interval", Input).value = str(config.refresh_interval)
        self.query_one("#api-key-input", Input).value = config.api_key
        self.query_one("#default-org-input", Input).value = config.default_org_id
        self.query_one("#default-network-input", Input).value = config.default_network_id
        vt = self.query_one("#views-table", DataTable)
        vt.add_columns("Name", "Org", "Network", "Screen", "Created")
        self._load_views()

    def _load_views(self) -> None:
        config = get_config()
        vt = self.query_one("#views-table", DataTable)
        vt.clear()
        for name, data in config.saved_views.items():
            vt.add_row(name, truncate(data.get("org_name",""),20),
                truncate(data.get("network_name",""),20),
                data.get("screen",""), data.get("created",""), key=name)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        config = get_config()
        if event.button.id == "save-general-btn":
            try:
                config.refresh_interval = int(self.query_one("#refresh-interval", Input).value)
                config.save()
                self.notify("Settings saved!")
            except ValueError:
                self.notify("Invalid refresh interval", severity="error")
        elif event.button.id == "save-api-btn":
            config.api_key = self.query_one("#api-key-input", Input).value
            config.default_org_id = self.query_one("#default-org-input", Input).value
            config.default_network_id = self.query_one("#default-network-input", Input).value
            config.save()
            self.notify("API config saved!")
        elif event.button.id == "save-view-btn":
            self.app.push_screen(SaveViewModal(), self._handle_save_view)

    def _handle_save_view(self, name: str) -> None:
        if name:
            self.app.save_current_view(name)
            self._load_views()
