# utils.py — Utility functions, formatters, and helpers for Meraki TUI
from __future__ import annotations
import re, logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Any
from dateutil import parser as dateutil_parser

logger = logging.getLogger(__name__)

SPARKLINE_CHARS = "▁▂▃▄▅▆▇█"


def format_bytes(num_bytes: int) -> str:
    if num_bytes < 0: return "N/A"
    for unit in ["B","KB","MB","GB","TB"]:
        if abs(num_bytes) < 1024.0: return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"


def format_kbps(kbps: float) -> str:
    if kbps < 0: return "N/A"
    if kbps < 1000: return f"{kbps:.1f} Kbps"
    if kbps < 1_000_000: return f"{kbps/1000:.1f} Mbps"
    return f"{kbps/1_000_000:.1f} Gbps"


def format_uptime(seconds: int) -> str:
    if seconds <= 0: return "N/A"
    d, h, m = seconds//86400, (seconds%86400)//3600, (seconds%3600)//60
    if d > 0: return f"{d}d {h}h {m}m"
    if h > 0: return f"{h}h {m}m"
    return f"{m}m"


def format_relative_time(dt: Optional[datetime]) -> str:
    if dt is None: return "N/A"
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
    total = int((now - dt).total_seconds())
    if total < 0: return "just now"
    if total < 60: return f"{total}s ago"
    if total < 3600: return f"{total//60}m ago"
    if total < 86400: return f"{total//3600}h ago"
    return f"{total//86400}d ago"


def parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str: return None
    try: return dateutil_parser.parse(dt_str)
    except (ValueError, TypeError): return None


def make_sparkline(data: List[float], width: int = 20) -> str:
    if not data: return "─" * width
    if len(data) > width: data = data[-width:]
    elif len(data) < width: data = [0.0] * (width - len(data)) + data
    min_val, max_val = min(data), max(data)
    if max_val == min_val: return SPARKLINE_CHARS[0] * width
    return "".join(
        SPARKLINE_CHARS[int((v - min_val) / (max_val - min_val) * (len(SPARKLINE_CHARS)-1))]
        for v in data
    )


def infer_device_type(model: str) -> str:
    m = model.upper()
    if m.startswith("MS"): return "switch"
    if m.startswith("MR") or m.startswith("CW"): return "wireless"
    if m.startswith("MX") or m.startswith("Z"): return "appliance"
    if m.startswith("MV"): return "camera"
    if m.startswith("MG"): return "cellularGateway"
    return "other"


def status_color(status: str) -> str:
    return {"online":"green","offline":"red","alerting":"yellow","dormant":"dim white"}.get(status.lower(),"white")


def severity_color(severity: str) -> str:
    return {"critical":"bold red","warning":"yellow","informational":"cyan","info":"cyan"}.get(severity.lower(),"white")


def truncate(text: str, max_len: int, ellipsis: str = "…") -> str:
    if len(text) <= max_len: return text
    return text[:max_len - len(ellipsis)] + ellipsis


def safe_get(d: Any, *keys: str, default: Any = None) -> Any:
    current = d
    for key in keys:
        if isinstance(current, dict): current = current.get(key, default)
        elif isinstance(current, list) and key.isdigit():
            idx = int(key)
            current = current[idx] if idx < len(current) else default
        else: return default
        if current is None: return default
    return current


def extract_usage_bytes(usage_dict: Any) -> Tuple[int, int]:
    if not isinstance(usage_dict, dict): return 0, 0
    sent = usage_dict.get("sent", 0) or 0
    recv = usage_dict.get("recv", 0) or 0
    return int(sent * 1024), int(recv * 1024)


MAC_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}$")

def is_valid_mac(mac: str) -> bool:
    return bool(MAC_PATTERN.match(mac.strip()))

def normalize_mac(mac: str) -> str:
    clean = re.sub(r"[:\-.]", "", mac).lower()
    if len(clean) != 12: return mac
    return ":".join(clean[i:i+2] for i in range(0, 12, 2))
