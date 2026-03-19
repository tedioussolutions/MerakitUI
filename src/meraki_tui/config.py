# config.py — Configuration management for Meraki TUI
from __future__ import annotations
import os, logging
from pathlib import Path
from typing import Optional, Dict, Any
import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_DIR = Path.home() / ".meraki_tui"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.yaml"
DEFAULT_LOG_FILE = DEFAULT_CONFIG_DIR / "meraki_tui.log"

DEFAULT_CONFIG: Dict[str, Any] = {
    "api": {
        "key": "",
        "base_url": "https://api.meraki.com/api/v1",
        "wait_on_rate_limit": True,
        "maximum_retries": 3,
    },
    "app": {
        "default_org_id": "",
        "default_network_id": "",
        "refresh_interval": 30,
        "client_timespan": 86400,
        "event_timespan": 86400,
        "analytics_timespan": 7200,
        "theme": "dark",
        "log_level": "WARNING",
    },
    "cache": {
        "device_status_ttl": 30,
        "client_list_ttl": 60,
        "topology_ttl": 300,
        "analytics_ttl": 120,
        "security_events_ttl": 60,
        "ids_settings_ttl": 300,
    },
    "saved_views": {},
    "orgs": {},
}


class Config:
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or DEFAULT_CONFIG_FILE
        self._data: Dict[str, Any] = {}
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.load()

    def load(self) -> None:
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    loaded = yaml.safe_load(f) or {}
                self._data = self._deep_merge(DEFAULT_CONFIG.copy(), loaded)
            except yaml.YAMLError:
                self._data = DEFAULT_CONFIG.copy()
        else:
            self._data = DEFAULT_CONFIG.copy()
            self.save()

    def save(self) -> None:
        with open(self.config_path, "w") as f:
            yaml.dump(self._data, f, default_flow_style=False, sort_keys=False)

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    @property
    def api_key(self) -> str:
        return os.environ.get("MERAKI_DASHBOARD_API_KEY","") or self._data["api"].get("key","")

    @api_key.setter
    def api_key(self, value: str) -> None:
        self._data["api"]["key"] = value

    @property
    def refresh_interval(self) -> int:
        return int(self._data["app"]["refresh_interval"])

    @refresh_interval.setter
    def refresh_interval(self, value: int) -> None:
        self._data["app"]["refresh_interval"] = value

    @property
    def client_timespan(self) -> int:
        return int(self._data["app"]["client_timespan"])

    @property
    def analytics_timespan(self) -> int:
        return int(self._data["app"]["analytics_timespan"])

    @property
    def event_timespan(self) -> int:
        return int(self._data["app"]["event_timespan"])

    @property
    def default_org_id(self) -> str:
        return self._data["app"].get("default_org_id","")

    @default_org_id.setter
    def default_org_id(self, value: str) -> None:
        self._data["app"]["default_org_id"] = value

    @property
    def default_network_id(self) -> str:
        return self._data["app"].get("default_network_id","")

    @default_network_id.setter
    def default_network_id(self, value: str) -> None:
        self._data["app"]["default_network_id"] = value

    @property
    def cache_ttls(self) -> Dict[str, int]:
        return self._data["cache"]

    @property
    def saved_views(self) -> Dict[str, Any]:
        return self._data.get("saved_views", {})

    def save_view(self, name: str, view_data: Dict[str, Any]) -> None:
        self._data.setdefault("saved_views", {})[name] = view_data
        self.save()

    def delete_view(self, name: str) -> None:
        self._data.get("saved_views", {}).pop(name, None)
        self.save()

    @property
    def log_level(self) -> str:
        return self._data["app"].get("log_level","WARNING")

    @property
    def theme(self) -> str:
        return self._data["app"].get("theme","dark")

    @theme.setter
    def theme(self, value: str) -> None:
        self._data["app"]["theme"] = value


_config_instance = None
def get_config(config_path: Optional[Path] = None) -> Config:
    global _config_instance
    if _config_instance is None:
        _config_instance = Config(config_path)
    return _config_instance
