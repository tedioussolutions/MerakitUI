# models.py — Data models and dataclasses for Meraki TUI
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any


class DeviceStatus(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    ALERTING = "alerting"
    DORMANT = "dormant"
    UNKNOWN = "unknown"


class DeviceType(Enum):
    SWITCH = "switch"
    WIRELESS = "wireless"
    APPLIANCE = "appliance"
    CAMERA = "camera"
    CELLULAR = "cellularGateway"
    OTHER = "other"


class AlertSeverity(Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "informational"


@dataclass
class Organization:
    id: str
    name: str
    url: str = ""
    api_enabled: bool = True
    networks: List["Network"] = field(default_factory=list)


@dataclass
class Network:
    id: str
    name: str
    organization_id: str
    product_types: List[str] = field(default_factory=list)
    time_zone: str = "UTC"
    tags: List[str] = field(default_factory=list)
    devices: List["Device"] = field(default_factory=list)


@dataclass
class Device:
    serial: str
    name: str
    model: str
    network_id: str
    status: DeviceStatus = DeviceStatus.UNKNOWN
    device_type: DeviceType = DeviceType.OTHER
    ip: str = ""
    mac: str = ""
    firmware: str = ""
    last_reported: Optional[datetime] = None
    uptime_seconds: int = 0
    tags: List[str] = field(default_factory=list)
    address: str = ""
    notes: str = ""
    wan1_ip: str = ""
    wan2_ip: str = ""

    @property
    def status_icon(self) -> str:
        return {"online":"🟢","offline":"🔴","alerting":"🟡",
                "dormant":"⚪","unknown":"❓"}.get(self.status.value,"❓")

    @property
    def device_type_icon(self) -> str:
        return {"switch":"🔀","wireless":"📡","appliance":"🛡️",
                "camera":"📷","cellularGateway":"📶","other":"📦"}.get(self.device_type.value,"📦")

    @property
    def uptime_human(self) -> str:
        s = self.uptime_seconds
        if s <= 0: return "N/A"
        d, h, m = s//86400, (s%86400)//3600, (s%3600)//60
        return f"{d}d {h}h" if d > 0 else (f"{h}h {m}m" if h > 0 else f"{m}m")


@dataclass
class Client:
    id: str
    mac: str
    description: str = ""
    ip: str = ""
    ip6: str = ""
    user: str = ""
    network_id: str = ""
    ssid: str = ""
    vlan: int = 0
    switchport: str = ""
    status: str = "Offline"
    last_seen: Optional[datetime] = None
    first_seen: Optional[datetime] = None
    sent_bytes: int = 0
    recv_bytes: int = 0
    rssi: int = 0
    os: str = ""
    manufacturer: str = ""

    @property
    def display_name(self) -> str:
        return self.description or self.user or self.mac

    @property
    def usage_human(self) -> str:
        total = self.sent_bytes + self.recv_bytes
        for unit in ["B","KB","MB","GB","TB"]:
            if abs(total) < 1024.0: return f"{total:.1f} {unit}"
            total /= 1024.0
        return f"{total:.1f} PB"

    @property
    def status_icon(self) -> str:
        return "🟢" if self.status == "Online" else "⚫"


@dataclass
class FirewallRule:
    policy: str
    protocol: str
    src_cidr: str = "Any"
    src_port: str = "Any"
    dest_cidr: str = "Any"
    dest_port: str = "Any"
    comment: str = ""
    syslog_enabled: bool = False
    order: int = 0

    @property
    def policy_icon(self) -> str:
        return "✅" if self.policy == "allow" else "🚫"


@dataclass
class SecurityEvent:
    event_type: str
    occurred_at: Optional[datetime] = None
    network_id: str = ""
    src_ip: str = ""
    dest_ip: str = ""
    protocol: str = ""
    message: str = ""
    severity: AlertSeverity = AlertSeverity.INFO
    blocked: bool = False

    @property
    def severity_icon(self) -> str:
        return {"critical":"🔴","warning":"🟡","informational":"🔵"}.get(self.severity.value,"🔵")


@dataclass
class Alert:
    id: str
    alert_type: str
    network_id: str = ""
    network_name: str = ""
    occurred_at: Optional[datetime] = None
    severity: AlertSeverity = AlertSeverity.INFO
    device_serial: str = ""
    device_name: str = ""
    message: str = ""
    resolved: bool = False

    @property
    def severity_icon(self) -> str:
        return {"critical":"🔴","warning":"🟡","informational":"🔵"}.get(self.severity.value,"🔵")

    @property
    def age_human(self) -> str:
        if not self.occurred_at: return "Unknown"
        from datetime import timezone
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        dt = self.occurred_at
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        delta = int((now - dt).total_seconds())
        if delta < 60: return f"{delta}s ago"
        if delta < 3600: return f"{delta//60}m ago"
        if delta < 86400: return f"{delta//3600}h ago"
        return f"{delta//86400}d ago"


@dataclass
class BandwidthSample:
    timestamp: datetime
    sent_kbps: float
    recv_kbps: float

    @property
    def total_kbps(self) -> float:
        return self.sent_kbps + self.recv_kbps


@dataclass
class NetworkTraffic:
    network_id: str
    samples: List[BandwidthSample] = field(default_factory=list)
    top_applications: List[Dict[str, Any]] = field(default_factory=list)
    top_clients: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def current_kbps(self) -> float:
        return self.samples[-1].total_kbps if self.samples else 0.0

    @property
    def sparkline_data(self) -> List[float]:
        return [s.total_kbps for s in self.samples[-20:]]


@dataclass
class WebhookServer:
    id: str
    name: str
    url: str
    network_id: str = ""
    shared_secret: str = ""


@dataclass
class SSID:
    number: int
    name: str
    network_id: str
    enabled: bool = True
    auth_mode: str = "open"
    band_selection: str = "Dual band operation"
    visible: bool = True
    client_count: int = 0
