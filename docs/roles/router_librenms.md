# LibreNMS integration role

The `router_librenms` role deploys the OpenWrt scripts used by LibreNMS
for OS detection and wireless sensors. It is opt-in and does not install
packages or change the SNMP community.

## Enable the role

Set the following variables in `host_vars/router1.yml` or a group vars file:

```yaml
---
router_snmpd_enabled: true
router_snmpd_community: "replace-with-a-long-random-community"
router_librenms_enabled: true
router_librenms_wireless_interfaces:
  - interface: phy0-ap0
    name: wl-2.4G
  - interface: phy1-ap0
    name: wl-5.0G
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `router_librenms_enabled` | `false` | Enable the role in `site.yml` |
| `router_librenms_source_ref` | `master` | LibreNMS agent branch, tag, or commit to download |
| `router_librenms_wireless_interfaces` | `[]` | Map wireless interface names to LibreNMS display labels |

Each interface mapping contains exactly two values:

- `interface`: the actual OpenWrt wireless interface name passed to
  `iw` and `iwinfo`
- `name`: the label written to `wlInterfaces.txt` and shown by
  LibreNMS

There are no assumed interface names. Both values must be unique across
the list. Interface names may contain letters, digits, underscores, dots,
colons, and hyphens. Labels may contain letters, digits, underscores,
dots, and hyphens.

The wireless interface list may be empty. The role still configures OS
detection and the aggregate wireless client count, but does not create
per-interface wireless sensors.

## Prerequisites

The role expects the SNMP daemon to be installed and managed by
`router_packages` and `router_base`. Configure a non-default SNMP
community with `router_snmpd_enabled` and
`router_snmpd_community`; restrict UDP/161 to trusted monitoring hosts
using the firewall. SNMPv2c does not encrypt community strings.

The wireless scripts use the OpenWrt `iw` and `iwinfo` utilities.
Install the corresponding packages through `router_packages_list`
when they are not already provided by the device's wireless stack:

```yaml
router_packages_list:
  - busybox
  - openwrt-keyring
  - muninlite
  - rsync
  - uhttpd
  - uhttpd-mod-ubus
  - rpcd
  - iw
  - iwinfo
```

## Managed files and SNMP configuration

The role downloads the LibreNMS scripts from the official
[librenms-agent repository](https://github.com/librenms/librenms-agent)
to the Ansible controller during each run, then deploys them under
`/etc/librenms`. `wlInterfaces.txt` is rendered locally from the configured
interface mappings and is not downloaded. The router itself does not need
Internet access; the Ansible controller must be able to reach GitHub over
HTTPS.

`router_librenms_source_ref` selects the upstream branch, tag, or commit
(default: `master`). The role resolves this ref to a commit SHA once per run and downloads every
script from that immutable commit. The default therefore picks up the current
upstream scripts on each role run without mixing files if the branch moves
during the download. For reproducible deployments, set this variable to an
immutable commit SHA. Downloaded files are compared with the installed
copies, so an unchanged upstream version does not trigger a file change or
SNMP restart.

SNMP extend entries are managed through UCI. The executable path is stored
in `prog` and command-line arguments are stored separately in `args`.

The role deploys a small `hardware` helper for LibreNMS hardware detection.
It prefers the Device Tree model, then DMI product information. Sophos SG
appliances are reported using their DMI vendor, product, and encoded model
revision (for example, `Sophos SG 125w Rev. 3` from `Sophos`, `SG`, and
`125Wr3`). On QEMU/KVM systems it reports the virtual machine vendor and
product when available; when no hardware metadata is exposed, it falls back
to the OpenWrt architecture. This avoids assuming that every OpenWrt target
has a Device Tree or DMI interface.

The role owns only sections prefixed with
`ansible_router_librenms_`; other SNMP settings and extend sections are
left untouched. Obsolete sections with this prefix are removed when the
wireless interface mapping changes.

The role configures the following LibreNMS extend names:

- `distro` and `hardware` for OS and hardware detection (`hardware` uses
  Device Tree, DMI, and a generic fallback for virtualized/minimal systems)
- `interfaces` and `clients-wlan` for interface mapping and aggregate
  associated-client count
- Per-interface `clients`, `frequency`, `noise-floor`, `rate`
  (TX/RX min/average/max), and `snr` (min/average/max) sensors

The role adds `/etc/librenms` to `/etc/sysupgrade.conf` so the scripts
survive sysupgrade. SNMP is restarted only when deployed files or managed
extend configuration changes.

## LibreNMS server

Enable the SNMP MIBs needed for the wireless sensors and ensure that the
device can be discovered and polled using the router's configured SNMP
community. The official
[LibreNMS OpenWrt device notes](https://docs.librenms.org/Support/Device-Notes/Openwrt/)
describe the expected sensors and a manual `snmpwalk` check. The
`distro` extend is also used for OpenWrt OS detection.

Run the role together with its package, base-service, and SNMP prerequisites
through the standard playbook. The SNMP variables shown above must be set:

```bash
ansible-playbook -i inventory.ini playbooks/site.yml \\
  --limit router1 \\
  --tags router_packages,router_base,router_snmpd,router_librenms
```
