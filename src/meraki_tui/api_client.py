# api_client.py — Async Meraki API wrapper with caching and rate limiting
from __future__ import annotations
import asyncio, logging, time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import meraki, meraki.aio
from .config import get_config
from .models import (Alert, AlertSeverity, BandwidthSample, Client, Device,
    DeviceStatus, DeviceType, FirewallRule, IDSAllowedRule, IDSMode,
    IDSOrgSettings, IDSProtectedNetworks, IDSSettings, Network, NetworkTraffic,
    Organization, SecurityEvent, SSID, WebhookServer)
from .utils import infer_device_type, parse_datetime, safe_get, extract_usage_bytes

logger = logging.getLogger(__name__)


class TTLCache:
    """Simple in-memory TTL cache keyed by string."""
    def __init__(self):
        self._store: Dict[str, Tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        if key in self._store:
            value, expires_at = self._store[key]
            if time.monotonic() < expires_at:
                return value
            del self._store[key]
        return None

    def set(self, key: str, value: Any, ttl: int) -> None:
        self._store[key] = (value, time.monotonic() + ttl)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def invalidate_prefix(self, prefix: str) -> None:
        for k in [k for k in self._store if k.startswith(prefix)]:
            del self._store[k]

    def clear(self) -> None:
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)


class RateLimiter:
    """Token bucket — max 8 req/sec per org (safe under Meraki's 10/sec limit)."""
    def __init__(self, rate: float = 8.0):
        self.rate = rate
        self._tokens: Dict[str, float] = {}
        self._last_check: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, org_id: str = "global") -> None:
        async with self._lock:
            now = time.monotonic()
            if org_id not in self._tokens:
                self._tokens[org_id] = self.rate
                self._last_check[org_id] = now
            elapsed = now - self._last_check[org_id]
            self._tokens[org_id] = min(self.rate, self._tokens[org_id] + elapsed * self.rate)
            self._last_check[org_id] = now
            if self._tokens[org_id] < 1.0:
                await asyncio.sleep((1.0 - self._tokens[org_id]) / self.rate)
                self._tokens[org_id] = 0.0
            else:
                self._tokens[org_id] -= 1.0


class MerakiAPIClient:
    """Async Meraki API client with TTL caching, rate limiting, error handling."""

    def __init__(self):
        self.config = get_config()
        self.cache = TTLCache()
        self.rate_limiter = RateLimiter(rate=8.0)
        self._dashboard: Optional[meraki.aio.AsyncDashboardAPI] = None
        self._lock = asyncio.Lock()
        self.last_api_call: Optional[datetime] = None
        self.api_error_count: int = 0
        self.api_call_count: int = 0

    async def _get_dashboard(self) -> meraki.aio.AsyncDashboardAPI:
        if self._dashboard is None:
            async with self._lock:
                if self._dashboard is None:
                    api_key = self.config.api_key
                    if not api_key:
                        raise ValueError("No API key configured.")
                    self._dashboard = meraki.aio.AsyncDashboardAPI(
                        api_key=api_key,
                        wait_on_rate_limit=True,
                        maximum_retries=3,
                        print_console=False,
                        suppress_logging=True,
                        output_log=False,
                    )
        return self._dashboard

    async def _call(self, org_id: str, coro) -> Any:
        await self.rate_limiter.acquire(org_id)
        try:
            result = await coro
            self.last_api_call = datetime.utcnow()
            self.api_call_count += 1
            return result
        except meraki.AsyncAPIError as e:
            self.api_error_count += 1
            if e.status == 401: raise ValueError("Invalid API key")
            elif e.status in (400, 404): return None
            raise

    async def get_organizations(self) -> List[Organization]:
        cached = self.cache.get("orgs:all")
        if cached: return cached
        dashboard = await self._get_dashboard()
        raw = await self._call("global", dashboard.organizations.getOrganizations())
        orgs = [Organization(id=o["id"], name=o["name"], url=o.get("url",""))
                for o in (raw or []) if o.get("api",{}).get("enabled", True)]
        self.cache.set("orgs:all", orgs, self.config.cache_ttls["topology_ttl"])
        return orgs

    async def get_networks(self, org_id: str) -> List[Network]:
        cached = self.cache.get(f"networks:{org_id}")
        if cached: return cached
        dashboard = await self._get_dashboard()
        raw = await self._call(org_id,
            dashboard.organizations.getOrganizationNetworks(org_id, total_pages="all"))
        networks = [Network(id=n["id"], name=n["name"], organization_id=org_id,
            product_types=n.get("productTypes",[]), time_zone=n.get("timeZone","UTC"))
            for n in (raw or [])]
        self.cache.set(f"networks:{org_id}", networks, self.config.cache_ttls["topology_ttl"])
        return networks

    async def get_org_device_statuses(self, org_id: str) -> List[Device]:
        cached = self.cache.get(f"device_statuses:{org_id}")
        if cached: return cached
        dashboard = await self._get_dashboard()
        statuses_raw, inventory_raw = await asyncio.gather(
            self._call(org_id, dashboard.organizations.getOrganizationDevicesStatuses(
                org_id, total_pages="all")),
            self._call(org_id, dashboard.organizations.getOrganizationDevices(
                org_id, total_pages="all")),
            return_exceptions=True
        )
        if isinstance(statuses_raw, Exception): statuses_raw = []
        if isinstance(inventory_raw, Exception): inventory_raw = []
        inv_map = {i["serial"]: i for i in (inventory_raw or [])}
        devices = []
        for s in (statuses_raw or []):
            serial = s.get("serial","")
            inv = inv_map.get(serial, {})
            model = inv.get("model", s.get("model",""))
            dtype_str = infer_device_type(model)
            dtype = DeviceType(dtype_str) if dtype_str in [e.value for e in DeviceType] else DeviceType.OTHER
            try: status = DeviceStatus(s.get("status","unknown").lower())
            except ValueError: status = DeviceStatus.UNKNOWN
            devices.append(Device(
                serial=serial, name=inv.get("name") or s.get("name") or serial,
                model=model, network_id=s.get("networkId",""), status=status,
                device_type=dtype, ip=s.get("lanIp",""), mac=inv.get("mac",""),
                firmware=s.get("firmware",""), last_reported=parse_datetime(s.get("lastReportedAt")),
                tags=inv.get("tags",[]), wan1_ip=s.get("wan1Ip",""), wan2_ip=s.get("wan2Ip",""),
            ))
        self.cache.set(f"device_statuses:{org_id}", devices, self.config.cache_ttls["device_status_ttl"])
        return devices

    async def get_network_clients(self, network_id: str, org_id: str = "global",
                                   timespan: Optional[int] = None) -> List[Client]:
        timespan = timespan or self.config.client_timespan
        cached = self.cache.get(f"clients:{network_id}:{timespan}")
        if cached: return cached
        dashboard = await self._get_dashboard()
        raw = await self._call(org_id, dashboard.networks.getNetworkClients(
            network_id, timespan=timespan, perPage=1000, total_pages="all"))
        clients = []
        for c in (raw or []):
            sent, recv = extract_usage_bytes(c.get("usage", {}))
            clients.append(Client(
                id=c.get("id", c.get("mac","")), mac=c.get("mac",""),
                description=c.get("description",""), ip=c.get("ip",""),
                user=c.get("user",""), network_id=network_id,
                ssid=c.get("ssid",""), vlan=int(c.get("vlan",0) or 0),
                status=c.get("status","Offline"),
                last_seen=parse_datetime(c.get("lastSeen")),
                sent_bytes=sent, recv_bytes=recv,
                os=c.get("os",""), manufacturer=c.get("manufacturer",""),
            ))
        self.cache.set(f"clients:{network_id}:{timespan}", clients, self.config.cache_ttls["client_list_ttl"])
        return clients

    async def get_firewall_rules(self, network_id: str, org_id: str = "global") -> List[FirewallRule]:
        cached = self.cache.get(f"fw_rules:{network_id}")
        if cached: return cached
        dashboard = await self._get_dashboard()
        raw = await self._call(org_id,
            dashboard.appliance.getNetworkApplianceFirewallL3FirewallRules(network_id))
        rules_data = raw.get("rules",[]) if isinstance(raw, dict) else (raw or [])
        rules = [FirewallRule(policy=r.get("policy","deny"), protocol=r.get("protocol","any"),
            src_cidr=r.get("srcCidr","Any"), src_port=r.get("srcPort","Any"),
            dest_cidr=r.get("destCidr","Any"), dest_port=r.get("destPort","Any"),
            comment=r.get("comment",""), order=i) for i, r in enumerate(rules_data)]
        self.cache.set(f"fw_rules:{network_id}", rules, 120)
        return rules

    async def get_security_events(self, network_id: str, org_id: str = "global",
                                   timespan: Optional[int] = None) -> List[SecurityEvent]:
        timespan = timespan or self.config.event_timespan
        cached = self.cache.get(f"sec_events:{network_id}:{timespan}")
        if cached: return cached
        dashboard = await self._get_dashboard()
        raw = await self._call(org_id,
            dashboard.appliance.getNetworkApplianceSecurityEvents(
                network_id, timespan=timespan, perPage=100, total_pages=3))
        events = []
        for e in (raw or []):
            msg = e.get("ruleMessage","").lower()
            sev = (AlertSeverity.CRITICAL if "critical" in msg or "high" in msg
                   else AlertSeverity.WARNING if "medium" in msg else AlertSeverity.INFO)
            events.append(SecurityEvent(
                event_type=e.get("eventType", e.get("type","unknown")),
                occurred_at=parse_datetime(e.get("ts") or e.get("occurredAt")),
                network_id=network_id, src_ip=e.get("srcIp",""), dest_ip=e.get("destIp",""),
                protocol=e.get("protocol",""), message=e.get("ruleMessage",""),
                severity=sev, blocked=e.get("blocked", False),
                signature=e.get("signature", ""),
                classification=e.get("classification", ""),
                priority=e.get("priority", 0),
                sig_source=e.get("sigSource", ""),
                client_mac=e.get("clientMac", ""),
            ))
        self.cache.set(f"sec_events:{network_id}:{timespan}", events, self.config.cache_ttls["security_events_ttl"])
        return events

    async def get_network_traffic(self, network_id: str, org_id: str = "global",
                                   timespan: Optional[int] = None) -> NetworkTraffic:
        timespan = timespan or self.config.analytics_timespan
        cached = self.cache.get(f"traffic:{network_id}:{timespan}")
        if cached: return cached
        dashboard = await self._get_dashboard()
        raw = await self._call(org_id,
            dashboard.networks.getNetworkTraffic(network_id, timespan=timespan))
        traffic = NetworkTraffic(network_id=network_id)
        if raw:
            traffic.top_applications = sorted(raw,
                key=lambda x: x.get("recv",0)+x.get("sent",0), reverse=True)[:10]
        self.cache.set(f"traffic:{network_id}:{timespan}", traffic, self.config.cache_ttls["analytics_ttl"])
        return traffic

    async def get_network_events(self, network_id: str, org_id: str = "global",
                                  product_type: str = "appliance",
                                  timespan: Optional[int] = None) -> List[Alert]:
        cached = self.cache.get(f"events:{network_id}:{product_type}")
        if cached: return cached
        dashboard = await self._get_dashboard()
        raw = await self._call(org_id, dashboard.networks.getNetworkEvents(
            network_id, productType=product_type, perPage=100, total_pages=2))
        events_data = raw.get("events",[]) if isinstance(raw, dict) else (raw or [])
        alerts = [Alert(
            id=str(e.get("occurredAt",""))+e.get("type",""),
            alert_type=e.get("type", e.get("eventType","unknown")),
            network_id=network_id,
            occurred_at=parse_datetime(e.get("occurredAt")),
            severity=AlertSeverity.WARNING if "down" in e.get("type","").lower() else AlertSeverity.INFO,
            device_serial=e.get("deviceSerial",""), device_name=e.get("deviceName",""),
            message=e.get("description", e.get("type","")),
        ) for e in events_data]
        self.cache.set(f"events:{network_id}:{product_type}", alerts, 60)
        return alerts

    async def get_ssids(self, network_id: str, org_id: str = "global") -> List[SSID]:
        cached = self.cache.get(f"ssids:{network_id}")
        if cached: return cached
        dashboard = await self._get_dashboard()
        raw = await self._call(org_id, dashboard.wireless.getNetworkWirelessSsids(network_id))
        ssids = [SSID(number=s.get("number",0), name=s.get("name",""),
            network_id=network_id, enabled=s.get("enabled",False),
            auth_mode=s.get("authMode","open"), band_selection=s.get("bandSelection",""),
            visible=s.get("visible",True)) for s in (raw or [])]
        self.cache.set(f"ssids:{network_id}", ssids, 120)
        return ssids

    async def get_org_ids_settings(self, org_id: str) -> Optional[IDSOrgSettings]:
        """Fetch organization-level IDS/IPS settings."""
        cached = self.cache.get(f"ids_org:{org_id}")
        if cached: return cached
        dashboard = await self._get_dashboard()
        try:
            response = await self._call(org_id,
                dashboard.appliance.getOrganizationApplianceSecurityIntrusion(org_id))
            if response is None:
                return None
            allowed_rules = [
                IDSAllowedRule(
                    rule_id=r.get("ruleId", ""),
                    message=r.get("message", ""),
                )
                for r in response.get("allowedRules", [])
            ]
            result = IDSOrgSettings(allowed_rules=allowed_rules)
            self.cache.set(f".ids_org:{org_id}", result, 300)
            return result
        except Exception:
            return None

    async def get_network_ids_settings(self, network_id: str, org_id: str = "global") -> Optional[IDSSettings]:
        """Fetch network-level IDS/IPS settings."""
        cached = self.cache.get(f"ids_net:{network_id}")
        if cached: return cached
        dashboard = await self._get_dashboard()
        try:
            response = await self._call(org_id,
                dashboard.appliance.getNetworkApplianceSecurityIntrusion(network_id))
            if response is None:
                return None
            mode = IDSMode(response.get("mode", "disabled"))
            ids_rulesets = response.get("idsRulesets", "balanced")

            pn = response.get("protectedNetworks")
            protected_networks = None
            if pn:
                protected_networks = IDSProtectedNetworks(
                    use_default=pn.get("useDefault", True),
                    included_cidr=pn.get("includedCidr", []),
                    excluded_cidr=pn.get("excludedCidr", []),
                )

            result = IDSSettings(
                mode=mode,
                ids_rulesets=ids_rulesets,
                protected_networks=protected_networks,
            )
            self.cache.set(f"ids_net:{network_id}", result, 300)
            return result
        except Exception:
            return None

    async def submit_action_batch(self, org_id: str, actions: List[Dict],
                                   confirmed: bool = True, synchronous: bool = False) -> Optional[Dict]:
        dashboard = await self._get_dashboard()
        try:
            return await self._call(org_id,
                dashboard.organizations.createOrganizationActionBatch(
                    org_id, confirmed=confirmed, synchronous=synchronous, actions=actions))
        except Exception as e:
            logger.error(f"Action batch failed: {e}")
            return None

    def invalidate_network_cache(self, network_id: str) -> None:
        for prefix in [f"clients:{network_id}", f"fw_rules:{network_id}",
                       f"sec_events:{network_id}", f"traffic:{network_id}",
                       f"events:{network_id}", f"ssids:{network_id}",
                       f"ids_net:{network_id}"]:
            self.cache.invalidate_prefix(prefix)


_api_client = None
def get_api_client() -> MerakiAPIClient:
    global _api_client
    if _api_client is None:
        _api_client = MerakiAPIClient()
    return _api_client
