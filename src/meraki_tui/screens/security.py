# screens/security.py — Security Management Screen
from textual.app import ComposeResult
from textual.widgets import DataTable, TabbedContent, TabPane, Label
from textual.containers import Container
from textual import work
import asyncio
from ..api_client import get_api_client
from ..models import Organization, Network
from ..utils import format_relative_time, truncate


class SecurityScreen(Container):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._org = None
        self._network = None

    def compose(self) -> ComposeResult:
        with TabbedContent():
            with TabPane("Firewall Rules", id="tab-fw"):
                yield DataTable(id="fw-table")
            with TabPane("Security Events", id="tab-events"):
                yield DataTable(id="events-table")
            with TabPane("Content Filter", id="tab-cf"):
                yield Label("Select a network to view content filtering.", id="cf-label")

    def on_mount(self) -> None:
        fw = self.query_one("#fw-table", DataTable)
        fw.add_columns("#", "Policy", "Protocol", "Src CIDR", "Src Port",
                       "Dest CIDR", "Dest Port", "Comment")
        ev = self.query_one("#events-table", DataTable)
        ev.add_columns("", "Time", "Type", "Src IP", "Dest IP", "Protocol", "Message", "Blocked")

    def update_context(self, org: Organization, network: Network) -> None:
        self._org = org
        self._network = network
        self._load_all()

    @work(exclusive=True)
    async def _load_all(self) -> None:
        if not self._network: return
        client = get_api_client()
        org_id = self._org.id if self._org else "global"
        fw_rules, sec_events = await asyncio.gather(
            client.get_firewall_rules(self._network.id, org_id),
            client.get_security_events(self._network.id, org_id),
            return_exceptions=True
        )
        if not isinstance(fw_rules, Exception):
            fw = self.query_one("#fw-table", DataTable)
            fw.clear()
            for r in fw_rules:
                fw.add_row(str(r.order+1), f"{r.policy_icon} {r.policy}",
                    r.protocol, r.src_cidr, r.src_port,
                    r.dest_cidr, r.dest_port, truncate(r.comment, 40))
        if not isinstance(sec_events, Exception):
            ev = self.query_one("#events-table", DataTable)
            ev.clear()
            for e in sec_events:
                ev.add_row(e.severity_icon,
                    format_relative_time(e.occurred_at),
                    e.event_type, e.src_ip, e.dest_ip, e.protocol,
                    truncate(e.message, 50), "Yes" if e.blocked else "No")

    def action_refresh(self) -> None:
        if self._network:
            get_api_client().cache.invalidate_prefix(f"fw_rules:{self._network.id}")
            get_api_client().cache.invalidate_prefix(f"sec_events:{self._network.id}")
        self._load_all()
