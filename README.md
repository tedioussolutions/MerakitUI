# Meraki TUI — Cisco Meraki Dashboard Monitoring Suite

A full-screen terminal application for monitoring and configuring Cisco Meraki environments using the Textual framework.

## Features

- **Dashboard** — Device status table with summary bar, filter, sort, detail modal
- **Clients** — Client monitoring with search, online-only toggle, usage sort
- **Security** — Firewall rules, security events, content filtering
- **Analytics** — Bandwidth sparklines, top apps, top clients, wireless stats
- **Alerts** — Incident log, webhooks, alert settings
- **Config** — SSID management, switch ports, bulk operations via Action Batches
- **Settings** — General settings, API config, saved views management

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Run with environment variable
export MERAKI_DASHBOARD_API_KEY=your_api_key
python -m meraki_tui

# Or pass API key directly
python -m meraki_tui --api-key YOUR_KEY

# With org and network pre-selected
python -m meraki_tui --org ORG_ID --network NETWORK_ID --theme dark
```

## Requirements

- Python 3.9+
- Cisco Meraki Dashboard API key
