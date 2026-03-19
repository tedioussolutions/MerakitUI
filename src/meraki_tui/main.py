#!/usr/bin/env python3
# main.py — Entry point for Meraki TUI Monitoring Suite
"""
Meraki TUI — Cisco Meraki Dashboard Monitoring Suite

Usage:
    python -m meraki_tui
    python -m meraki_tui --api-key YOUR_KEY
    python -m meraki_tui --org ORG_ID --network NETWORK_ID --theme dark

Requirements:
    pip install textual meraki pyyaml rich aiohttp python-dateutil
"""
from __future__ import annotations
import argparse, asyncio, logging, sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header
from textual.containers import Container, Horizontal
from textual import work

from .config import get_config, DEFAULT_LOG_FILE
from .api_client import get_api_client
from .models import Organization, Network
from .widgets.org_switcher import OrgSwitcherWidget
from .widgets.status_bar import StatusBarWidget
from .screens.dashboard import DashboardScreen
from .screens.clients import ClientsScreen
from .screens.security import SecurityScreen
from .screens.analytics import AnalyticsScreen
from .screens.alerts import AlertsScreen
from .screens.config_screen import ConfigScreen
from .screens.settings import SettingsScreen


class MerakiTUIApp(App):
    """
    Meraki TUI — Main Application

    Keyboard shortcuts:
        1-7     Switch between screens
        r       Refresh current screen
        R       Refresh all (clear cache)
        o       Focus org switcher
        /       Search (on supported screens)
        F5      Toggle auto-refresh
        F10     Save current view
        ?       Show help
        q       Quit
    """
    TITLE = "Meraki TUI — Network Monitoring Suite"
    SUB_TITLE = "Cisco Meraki Dashboard"

    CSS = """
    MerakiTUIApp { layout: horizontal; }
    #sidebar { width: 30; height: 100%; dock: left; }
    #main-content { width: 1fr; height: 100%; layout: vertical; }
    """

    BINDINGS = [
        Binding("1", "switch_screen('dashboard')", "Dashboard"),
        Binding("2", "switch_screen('clients')", "Clients"),
        Binding("3", "switch_screen('security')", "Security"),
        Binding("4", "switch_screen('analytics')", "Analytics"),
        Binding("5", "switch_screen('alerts')", "Alerts"),
        Binding("6", "switch_screen('config')", "Config"),
        Binding("7", "switch_screen('settings')", "Settings"),
        Binding("r", "refresh_current", "Refresh", show=False),
        Binding("R", "refresh_all", "Refresh All", show=False),
        Binding("o", "focus_org_switcher", "Orgs", show=False),
        Binding("f5", "toggle_auto_refresh", "Auto-Refresh", show=False),
        Binding("f10", "save_view_prompt", "Save View", show=False),
        Binding("question_mark", "show_help", "Help", show=False),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.config = get_config()
        if api_key:
            self.config.api_key = api_key
        self._current_org: Optional[Organization] = None
        self._current_network: Optional[Network] = None
        self._current_screen_name: str = "dashboard"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="app-body"):
            yield OrgSwitcherWidget(id="sidebar")
            with Container(id="main-content"):
                yield DashboardScreen(id="screen-dashboard")
                yield ClientsScreen(id="screen-clients")
                yield SecurityScreen(id="screen-security")
                yield AnalyticsScreen(id="screen-analytics")
                yield AlertsScreen(id="screen-alerts")
                yield ConfigScreen(id="screen-config")
                yield SettingsScreen(id="screen-settings")
        yield StatusBarWidget(
            refresh_interval=self.config.refresh_interval,
            id="status-bar"
        )
        yield Footer()

    def on_mount(self) -> None:
        for name in ["clients","security","analytics","alerts","config","settings"]:
            self.query_one(f"#screen-{name}").display = False
        if not self.config.api_key:
            self.notify(
                "No API key! Set MERAKI_DASHBOARD_API_KEY or press 7 for Settings",
                severity="warning", timeout=10
            )

    def on_org_switcher_widget_org_selected(self, message):
        self._current_org = message.org
        self._propagate_context()
        self.query_one("#status-bar", StatusBarWidget).update_context(
            self._current_org, self._current_network
        )

    def on_org_switcher_widget_network_selected(self, message):
        self._current_network = message.network
        self._propagate_context()
        self.query_one("#status-bar", StatusBarWidget).update_context(
            self._current_org, self._current_network
        )

    def _propagate_context(self) -> None:
        for sid in ["dashboard","clients","security","analytics","alerts","config"]:
            try:
                screen = self.query_one(f"#screen-{sid}")
                if hasattr(screen, "update_context"):
                    screen.update_context(self._current_org, self._current_network)
            except Exception:
                pass

    def action_switch_screen(self, screen_name: str) -> None:
        for name in ["dashboard","clients","security","analytics","alerts","config","settings"]:
            self.query_one(f"#screen-{name}").display = (name == screen_name)
        self._current_screen_name = screen_name

    def action_refresh_current(self) -> None:
        screen = self.query_one(f"#screen-{self._current_screen_name}")
        if hasattr(screen, "action_refresh"):
            screen.action_refresh()
        self.query_one("#status-bar", StatusBarWidget).mark_refreshed()

    def action_refresh_all(self) -> None:
        get_api_client().cache.clear()
        self._propagate_context()
        self.notify("All caches cleared — refreshing…", timeout=3)

    def trigger_auto_refresh(self) -> None:
        self.action_refresh_current()

    def save_current_view(self, name: str) -> None:
        self.config.save_view(name, {
            "org_id": self._current_org.id if self._current_org else "",
            "org_name": self._current_org.name if self._current_org else "",
            "network_id": self._current_network.id if self._current_network else "",
            "network_name": self._current_network.name if self._current_network else "",
            "screen": self._current_screen_name,
            "created": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
        })
        self.notify(f"View '{name}' saved")

    def load_saved_view(self, view_data: Dict[str, Any]) -> None:
        self.action_switch_screen(view_data.get("screen", "dashboard"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Meraki TUI")
    parser.add_argument("--api-key", "-k", default=None)
    parser.add_argument("--config", "-c", default=None, type=Path)
    parser.add_argument("--org", default=None)
    parser.add_argument("--network", default=None)
    parser.add_argument("--theme", default=None, choices=["dark","light","nord"])
    args = parser.parse_args()

    config = get_config(Path(args.config) if args.config else None)
    if args.org: config.default_org_id = args.org
    if args.network: config.default_network_id = args.network
    if args.theme: config.theme = args.theme

    MerakiTUIApp(api_key=args.api_key).run()

if __name__ == "__main__":
    main()
