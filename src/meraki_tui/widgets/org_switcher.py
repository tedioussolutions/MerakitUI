# widgets/org_switcher.py — Org and Network Selector Sidebar
from textual.app import ComposeResult
from textual.message import Message
from textual.widgets import ListView, ListItem, Label, Button
from textual.containers import Container, Vertical
from textual import work
from ..api_client import get_api_client
from ..config import get_config
from ..models import Organization, Network
from ..utils import truncate


class OrgSwitcherWidget(Container):
    class OrgSelected(Message):
        def __init__(self, org: Organization):
            super().__init__()
            self.org = org

    class NetworkSelected(Message):
        def __init__(self, network: Network):
            super().__init__()
            self.network = network

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._orgs = []
        self._networks = []
        self._selected_org = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Organizations", id="orgs-label")
            yield ListView(id="orgs-list")
            yield Label("Networks", id="networks-label")
            yield ListView(id="networks-list")
            yield Button("Refresh", id="refresh-orgs-btn", variant="default")

    def on_mount(self) -> None:
        self._load_orgs()

    @work(exclusive=True)
    async def _load_orgs(self) -> None:
        client = get_api_client()
        self._orgs = await client.get_organizations()
        orgs_list = self.query_one("#orgs-list", ListView)
        await orgs_list.clear()
        config = get_config()
        for org in self._orgs:
            await orgs_list.append(ListItem(Label(truncate(org.name, 24)), id=f"org-{org.id}"))
        if config.default_org_id:
            default = next((o for o in self._orgs if o.id == config.default_org_id), None)
            if default:
                self._selected_org = default
                self.post_message(self.OrgSelected(default))
                self._load_networks(default.id)

    @work(exclusive=True)
    async def _load_networks(self, org_id: str) -> None:
        client = get_api_client()
        self._networks = await client.get_networks(org_id)
        networks_list = self.query_one("#networks-list", ListView)
        await networks_list.clear()
        config = get_config()
        for net in self._networks:
            types = "/".join(net.product_types[:2])
            label = f"{truncate(net.name, 20)} [{types}]"
            await networks_list.append(ListItem(Label(label), id=f"net-{net.id}"))
        if config.default_network_id:
            default = next((n for n in self._networks if n.id == config.default_network_id), None)
            if default:
                self.post_message(self.NetworkSelected(default))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id.startswith("org-"):
            org_id = item_id[4:]
            org = next((o for o in self._orgs if o.id == org_id), None)
            if org:
                self._selected_org = org
                self.post_message(self.OrgSelected(org))
                self._load_networks(org_id)
        elif item_id.startswith("net-"):
            net_id = item_id[4:]
            net = next((n for n in self._networks if n.id == net_id), None)
            if net:
                self.post_message(self.NetworkSelected(net))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh-orgs-btn":
            get_api_client().cache.invalidate("orgs:all")
            if self._selected_org:
                get_api_client().cache.invalidate(f"networks:{self._selected_org.id}")
            self._load_orgs()
