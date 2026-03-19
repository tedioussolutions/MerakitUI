# screens/security.py — Security Management Screen
from textual.app import ComposeResult
from textual.widgets import DataTable, TabbedContent, TabPane, Label
from textual.containers import Container
from textual import work
import asyncio
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional
from typing import cast
from ..api_client import get_api_client
from ..models import Organization, Network, IDSMode, IDSSettings, IDSOrgSettings, SecurityEvent
from ..utils import format_relative_time, truncate, make_sparkline


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
            with TabPane("IDS/IPS", id="tab-ids"):
                yield Label("", id="ids-status")
                yield Label("", id="ids-sparkline-label")
                yield Label("IDS Events (last 24h):", id="ids-spark-header")
                yield Label("", id="ids-sparkline")
                yield Label("IDS Events:", id="ids-events-header")
                yield DataTable(id="ids-events-table")
                yield Label("Top Attackers:", id="ids-attackers-header")
                yield DataTable(id="ids-attackers-table")

    def on_mount(self) -> None:
        fw = self.query_one("#fw-table", DataTable)
        fw.add_columns("#", "Policy", "Protocol", "Src CIDR", "Src Port",
                       "Dest CIDR", "Dest Port", "Comment")
        ev = self.query_one("#events-table", DataTable)
        ev.add_columns("", "Time", "Type", "Src IP", "Dest IP", "Protocol", "Message", "Blocked")
        ids_ev = self.query_one("#ids-events-table", DataTable)
        ids_ev.add_columns("Time", "Signature", "Classification", "Priority", "Src IP", "Dest IP", "Action")
        ids_at = self.query_one("#ids-attackers-table", DataTable)
        ids_at.add_columns("Source IP", "Hit Count", "Last Seen")

    def update_context(self, org: Organization, network: Network) -> None:
        self._org = org
        self._network = network
        self._load_all()

    @work(exclusive=True)
    async def _load_all(self) -> None:
        if not self._network: return
        client = get_api_client()
        org_id = self._org.id if self._org else "global"
        fw_rules, sec_events, ids_settings, ids_org = await asyncio.gather(
            client.get_firewall_rules(self._network.id, org_id),
            client.get_security_events(self._network.id, org_id),
            client.get_network_ids_settings(self._network.id, org_id),
            client.get_org_ids_settings(org_id),
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

        # --- IDS/IPS tab ---
        self._update_ids_tab(
            cast(Optional["IDSSettings"], ids_settings if not isinstance(ids_settings, Exception) else None),
            cast(Optional["IDSOrgSettings"], ids_org if not isinstance(ids_org, Exception) else None),
            cast(List["SecurityEvent"], sec_events if not isinstance(sec_events, Exception) else []),
        )

    def _update_ids_tab(
        self,
        ids_settings: Optional[IDSSettings],
        ids_org: Optional[IDSOrgSettings],
        sec_events: List[SecurityEvent],
    ) -> None:
        # Status panel
        status_label = self.query_one("#ids-status", Label)
        if ids_settings is None:
            status_label.update(
                "IDS/IPS: Not available (network may not have an MX appliance)")
        else:
            mode = ids_settings.mode
            mode_colors = {
                IDSMode.DISABLED: "🔴 Disabled",
                IDSMode.DETECTION: "🟡 Detection",
                IDSMode.PREVENTION: "🟢 Prevention",
            }
            mode_str = mode_colors.get(mode, mode.value)
            ruleset = ids_settings.ids_rulesets or "—"
            pn = ids_settings.protected_networks
            pn_str = "Default" if (pn is None or pn.use_default) else (
                f"{len(pn.included_cidr)} included, {len(pn.excluded_cidr)} excluded")
            allowed_count = len(ids_org.allowed_rules) if ids_org else 0
            status_label.update(
                f"Mode: {mode_str}  |  Ruleset: {ruleset}  |  "
                f"Protected Networks: {pn_str}  |  Allowed Rules: {allowed_count}")

        # Filter IDS events
        ids_events: List[SecurityEvent] = [e for e in sec_events if e.is_ids_event] if sec_events else []
        ids_events.sort(key=lambda e: e.occurred_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

        # Sparkline — bucket by hour over last 24h
        now = datetime.now(timezone.utc)
        hourly: List[float] = [0.0] * 24
        for e in ids_events:
            if e.occurred_at:
                try:
                    ts = e.occurred_at if e.occurred_at.tzinfo else e.occurred_at.replace(tzinfo=timezone.utc)
                    delta_h = int((now - ts).total_seconds() // 3600)
                    if 0 <= delta_h < 24:
                        hourly[23 - delta_h] += 1
                except Exception:
                    pass
        spark = make_sparkline(hourly, 24)
        total_ids = len(ids_events)
        peak = int(max(hourly))
        self.query_one("#ids-sparkline", Label).update(spark)
        self.query_one("#ids-sparkline-label", Label).update(
            f"Events last 24h: {total_ids}  ·  Peak/hr: {peak}")

        # IDS events table
        ids_ev = self.query_one("#ids-events-table", DataTable)
        ids_ev.clear()
        priority_icons: Dict[int, str] = {1: "🔴", 2: "🟡"}
        for e in ids_events[:200]:
            pri_icon = priority_icons.get(e.priority, "")
            pri_str = f"{pri_icon} {e.priority}" if e.priority else "—"
            action = "Blocked" if e.blocked else ("Alerted" if e.event_type == "ids-alerts" else "—")
            ids_ev.add_row(
                format_relative_time(e.occurred_at),
                truncate(e.signature, 35),
                truncate(e.classification, 25),
                pri_str,
                e.src_ip,
                e.dest_ip,
                action,
            )

        # Top attackers table
        ids_at = self.query_one("#ids-attackers-table", DataTable)
        ids_at.clear()
        attacker_counts: Counter[str] = Counter()
        attacker_last_seen: Dict[str, datetime] = {}
        for e in ids_events:
            if e.src_ip:
                attacker_counts[e.src_ip] += 1
                ts = e.occurred_at
                if ts and (e.src_ip not in attacker_last_seen or ts > attacker_last_seen[e.src_ip]):
                    attacker_last_seen[e.src_ip] = ts
        for ip, count in attacker_counts.most_common(10):
            last = attacker_last_seen.get(ip)
            ids_at.add_row(ip, str(count), format_relative_time(last))

    def action_refresh(self) -> None:
        if self._network:
            get_api_client().cache.invalidate_prefix(f"fw_rules:{self._network.id}")
            get_api_client().cache.invalidate_prefix(f"sec_events:{self._network.id}")
            get_api_client().cache.invalidate_prefix(f"ids_net:{self._network.id}")
            if self._org:
                get_api_client().cache.invalidate_prefix(f"ids_org:{self._org.id}")
        self._load_all()
