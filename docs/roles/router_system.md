# System role

The `router_system` role configures the router hostname, timezone, NTP
client, system logging options, Attended Sysupgrade (ASU) client settings,
and optional additional Dropbear SSH listeners.

## Run the role

The standard playbook initializes OpenWrt before running this role:

```bash
ansible-playbook -i inventory.ini playbooks/site.yml \
  --limit router1 --tags router_system
```

## Hostname, timezone, and NTP

| Variable | Default | Purpose |
| --- | --- | --- |
| `router_system_hostname` | `openwrt` | System hostname |
| `router_system_timezone` | `UTC` | System timezone offset/string |
| `router_system_timezone_name` | `Etc/UTC` | Timezone name |
| `router_system_ntp_enabled` | `true` | Enable the NTP client |
| `router_system_ntp_servers` | Four `*.openwrt.pool.ntp.org` servers | NTP server list |

The legacy input `router_hostname_value` is used as the default hostname
when `router_system_hostname` is not explicitly set.

For example:

```yaml
---
router_system_hostname: router1
router_system_timezone: CET-1CEST,M3.5.0,M10.5.0/3
router_system_timezone_name: Europe/Berlin
router_system_ntp_enabled: true
router_system_ntp_servers:
  - 0.de.pool.ntp.org
  - 1.de.pool.ntp.org
```

## System logging

| Variable | Default | Purpose |
| --- | --- | --- |
| `router_system_log_proto` | `udp` | Remote syslog transport protocol |
| `router_system_log_ip` | Undefined | Remote syslog server address |
| `router_system_conloglevel` | `8` | Console log level |
| `router_system_cronloglevel` | `7` | Cron log level |

The remote syslog destination has no default. Set it only for routers
that should send logs to a central server:

```yaml
---
router_system_log_ip: 192.0.2.234
```

Replace the documentation-only address with your actual syslog server
address. If `router_system_log_ip` is undefined, the role leaves the
existing UCI option unchanged.

## Attended Sysupgrade client

The role configures these UCI options:

| Variable | Default |
| --- | --- |
| `router_system_asu_auto_search` | `0` |
| `router_system_asu_login_check_for_upgrades` | `1` |
| `router_system_asu_upgrade_packages` | `1` |

These settings only have an effect when the relevant ASU client
components are installed. The role configures UCI options only; it does
not install the package. Add `luci-app-attendedsysupgrade` to
`router_packages_list` if it is not already present on the router.
See the [OpenWrt ASU documentation](
https://openwrt.org/docs/guide-user/installation/attended.sysupgrade).

## Additional Dropbear SSH ports

By default, the role leaves the existing Dropbear configuration and
port 22 untouched. Set `router_system_dropbear_extra_ports` to configure
role-owned listeners on additional TCP ports:

```yaml
---
router_system_dropbear_extra_ports:
  - 2222
  - 2223
```

Each additional port uses a separate Dropbear UCI section because OpenWrt
supports one `Port` option per section. The listeners use the router's
existing system accounts and SSH authorized keys; no separate credentials
are created.

Ports must be unique, between 1 and 65535, and must not include the
default SSH port 22. The role removes only its own additional listener
sections when a port is removed from the list. Setting the list to empty
removes all role-owned additional listeners.

The role restarts Dropbear when its managed listener configuration
changes. WAN access is configured separately by `router_firewall`;
see the [firewall guide](router_firewall.md#additional-dropbear-wan-access).
Additional ports remain closed on WAN by default.

## Applying changes

System settings are written through UCI. Changes to hostname, timezone,
NTP, and logging notify the system configuration handler, which reloads
system configuration and restarts logging and sysntpd. Dropbear is
restarted when its listener configuration changes.
