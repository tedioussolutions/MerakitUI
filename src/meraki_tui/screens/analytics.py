# screens/analytics.py — Network Analytics Screen
from textual.app import ComposeResult
from textual.widgets import DataTable, TabbedContent, TabPane, Label
from textual.containers import Container, Vertical
from textual import work
import asyncio
from ..api_client import get_api_client
from ..models import Organization, Network
from ..utils import format_bytes, format_kbps, make_sparkline, truncate


class BandwidthWidget(Container):
    def compose(self) -> ComposeResult:
        yield Label("Bandwidth", id="bw-label")
        yield Label("▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁", id="bw-sparkline")
        yield Label("Now: — · Peak: — · Avg: —", id="bw-stats")

    def update(self, data, current, peak, avg) -> None:
        self.query_one("#bw-sparkline").update(make_sparkline(data, 40))
        self.query_one("#bw-stats").update(
            f"Now: {format_kbps(current)} · Peak: {format_kbps(peak)} · Avg: {format_kbps(avg)}")


class AnalyticsScreen(Container):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._org = None
        self._network = None

    def compose(self) -> ComposeResult:
        with TabbedContent():
            with TabPane("Bandwidth", id="tab-bw"):
                yield BandwidthWidget(id="bw-widget")
                yield DataTable(id="apps-table")
            with TabPane("Top Clients", id="tab-clients"):
                yield DataTable(id="top-clients-table")
            with TabPane("Wireless", id="tab-wireless"):
                yield Label("Wireless stats will appear here.", id="wireless-label")

    def on_mount(self) -> None:
        apps = self.query_one("#apps-table", DataTable)
        apps.add_columns("Application", "Category", "Sent", "Received", "Total")
        tc = self.query_one("#top-clients-table", DataTable)
        tc.add_columns("Name", "MAC", "Usage", "Sent", "Received")

    def update_context(self, org: Organization, network: Network) -> None:
        self._org = org
        self._network = network
        self._load_all()

    @work(exclusive=True)
    async def _load_all(self) -> None:
        if not self._network: return
        client = get_api_client()
        org_id = self._org.id if self._org else "global"
        try:
            traffic = await client.get_network_traffic(self._network.id, org_id)
        except Exception:
            traffic = None
        if traffic:
            data = [a.get("recv",0)+a.get("sent",0) for a in traffic.top_applications]
            peak = max(data) if data else 0
            avg = sum(data)/len(data) if data else 0
            current = data[0] if data else 0
            self.query_one(BandwidthWidget).update(data, current, peak, avg)
            apps = self.query_one("#apps-table", DataTable)
            apps.clear()
            for a in traffic.top_applications:
                apps.add_row(
                    truncate(a.get("application","Unknown"), 30),
                    a.get("category","—"),
                    format_bytes(int(a.get("sent",0)*1024)),
                    format_bytes(int(a.get("recv",0)*1024)),
                    format_bytes(int((a.get("sent",0)+a.get("recv",0))*1024))
                )

    def action_refresh(self) -> None:
        if self._network:
            get_api_client().cache.invalidate_prefix(f"traffic:{self._network.id}")
        self._load_all()
