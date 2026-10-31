# Router configuration

This guide explains how to apply the playbooks, select individual roles,
and organize inventory variables. Detailed role options and examples live
in the corresponding role guides. For guidance on inspecting an existing
router before managing it with Ansible, see the
[OpenWrt state discovery guide](state-discovery/README.md).

## Apply the standard configuration

The `playbooks/site.yml` playbook applies the configured network settings
first, initializes OpenWrt, and then runs the system, firewall, package,
base-service, and optional SNMP roles.

Run the playbook against all routers in the `openwrt` inventory group:

```bash
ansible-playbook -i inventory.ini playbooks/site.yml
```

To target one router, add `--limit router1`:

```bash
ansible-playbook -i inventory.ini playbooks/site.yml --limit router1
```

Review the intended inventory changes before applying them. In particular,
`router_network` can interrupt connectivity when it changes interface
addressing.

## Run a selected role

Each project-owned role in `playbooks/site.yml` has a tag matching its
role name. For example:

```bash
ansible-playbook -i inventory.ini playbooks/site.yml \
  --limit router1 --tags router_firewall
```

Available tags are `router_network`, `router_system`,
`router_firewall`, `router_packages`, `router_base`, and
`router_snmpd`. The SNMP role is skipped unless
`router_snmpd_enabled: true` is set. OpenWrt initialization runs
automatically. Selecting one role does not automatically run other project
roles that may be prerequisites; review the selected tasks before execution.

## Role configuration guides

| Role | Purpose | Guide |
| --- | --- | --- |
| `router_network` | Explicit IPv4 interface addressing and per-interface DHCP server status | [Network](roles/router_network.md) |
| `router_system` | Hostname, timezone, NTP, logging, ASU client, and additional Dropbear listeners | [System](roles/router_system.md) |
| `router_firewall` | Default policies, declarative zones, and optional Dropbear WAN access | [Firewall](roles/router_firewall.md) |
| `router_packages` | Requested packages and packages required by managed services | [Packages](roles/router_packages.md) |
| `router_base` | Core service enablement and obsolete configuration cleanup | [Base services](roles/router_base.md) |
| `router_snmpd` | Optional SNMP community replacement | [SNMP daemon](roles/router_snmpd.md) |
| `router_package_audit` | Compare installed packages with a saved baseline | [Package audit](roles/router_package_audit.md) |

## Organize inventory variables

Use `group_vars/openwrt.yml` for settings shared by all routers and
`host_vars/<inventory_hostname>.yml` for router-specific overrides.
For example:

```text
inventory.ini
group_vars/
  openwrt.yml
host_vars/
  router1.yml
  router2.yml
```

Ansible host variables override group variables. Extra variables passed
with `-e` have higher precedence than both. A host-specific list replaces
the group list; Ansible does not merge lists automatically.

Each role guide documents the variables owned by that role and shows
complete inventory examples. Role defaults are also available in
`roles/<role_name>/defaults/main.yml`.
