# Router configuration

This guide explains how to apply the playbooks, select individual roles,
organize inventory variables, and discover existing router configuration.
Detailed role options and examples live in the corresponding role guides.

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
`router_firewall`, `router_packages`, `router_base`,
`router_snmpd`, and `router_librenms`. The SNMP and LibreNMS roles are
skipped unless `router_snmpd_enabled: true` and
`router_librenms_enabled: true` are set. OpenWrt initialization runs
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

## Discover existing OpenWrt configuration

For a router that already has manual changes, use the read-only discovery
script `scripts/owrt-extra.sh` to compare the live system with a
reconstructed factory reference and collect likely Ansible candidates.
Copy it to the router and run it there as root on OpenWrt; it is not an
Ansible playbook.

```sh
scp scripts/owrt-extra.sh root@router1:/tmp/owrt-extra.sh
ssh root@router1 'sh /tmp/owrt-extra.sh'
```

The report is written to `/tmp/owrt-diff/` in RAM. Treat it as sensitive:
UCI output can include Wi-Fi passwords and other secrets. The script does
not print password hashes, and host-key export is opt-in (`-H`); with
`-H`, private keys are copied in plaintext under
`/tmp/owrt-diff/secrets/`. Review and securely retrieve only what you
need, then remove the report and script from the router.

Options: `-k` keeps the temporary factory reference mounted for
inspection, `-f` rebuilds that reference, and `-H` exports host keys.
Read the script's help (`sh /tmp/owrt-extra.sh -h`) before using these
options.

The report includes a UCI diff, overlay-file candidates, package and
service differences, and—when supported—`apk audit --system` output in
`/tmp/owrt-diff/apk-audit-system.txt`. The APK audit can detect modified
package-owned system files outside protected configuration paths, but it
does not report arbitrary untracked files; the overlay scan handles a
different set of candidates. This check requires an APK-based OpenWrt
system (25.12+) and is skipped with a warning when the command or option
is unavailable.

CI checks shell syntax and command-line behavior using the OpenWrt 25.12
rootfs image. It does not run the full discovery workflow in that
container: the rootfs image does not provide the same device-like overlay
environment as a booted OpenWrt router. The mount/chroot reconstruction
and detection of real overlay changes still need validation on a suitable
OpenWrt VM or physical router.

This is an investigative report, not an automatic Ansible generator.
Runtime state such as manually installed nftables rules, `ip` changes,
temporary `sysctl` values, loaded modules, and running processes is not
comprehensively captured. Files in the overlay may also be caches or
service state rather than configuration. Review each candidate before
managing it with Ansible. Data outside the overlay, such as calibration
data and bootloader storage, is not suitable for normal Ansible
configuration.
