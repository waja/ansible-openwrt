# Router configuration

## Configure the routers

Apply the standard configuration using the Docker command shown in the
Docker section above. To target one router, add `--limit router1` to that
`ansible-playbook` command.

The `site.yml` playbook configures explicitly selected network settings first,
then initializes OpenWrt, applies system and firewall settings, installs the
configured packages, and configures base services while removing obsolete
configuration files.

### Run a selected role

Each project-owned role in `playbooks/site.yml` has a tag matching its role
name. For example, to run the base-service role against one router:

```bash
ansible-playbook -i inventory.ini playbooks/site.yml \
  --limit router1 --tags router_base
```

Available role tags are `router_network`, `router_system`,
`router_firewall`, `router_packages`, and `router_base`. OpenWrt
initialization runs automatically. Selecting one role does not automatically
run other project roles that may be prerequisites. Review the selected tasks
before execution; `router_network` can interrupt connectivity.

### Configure firewall defaults

The `router_firewall` role manages only the default firewall policies for
input, forwarding, and output. Its defaults are `REJECT`, `REJECT`, and
`ACCEPT`, respectively. These defaults preserve the usual OpenWrt firewall
policy.

For an access point that should pass traffic without filtering at the
firewall-defaults level, override the values in its `host_vars` file, for
example `host_vars/accesspoint.yml`:

```yaml
---
router_firewall_input: ACCEPT
router_firewall_forward: ACCEPT
router_firewall_output: ACCEPT
```

**Caution:** `input: ACCEPT` allows traffic to services on the router, and
`forward: ACCEPT` removes the default forwarding restriction. Use these
settings only where appropriate for your network design.

The role can also manage source NAT (masquerading) for explicitly selected
zones. Set `router_firewall_masquerading` to a mapping of zone names to
booleans. `true` enables masquerading and `false` disables it. The default
is an empty mapping, so no zone settings are changed. Zones omitted from the
mapping remain untouched; unknown zone names cause the role to fail rather
than creating new zones. Only the `masq` option is managed.

For example, in `host_vars/router1.yml`:

```yaml
---
router_firewall_masquerading:
  wan: true
  lan: false
  guest: false
```

Masquerading changes are committed in one UCI transaction and trigger a
firewall reload. The role does not manage `masq6`, zone membership,
individual firewall rules, or SYN-flood protection.

### Configure system settings

The `router_system` role manages the hostname, timezone, NTP client, system
logging options, and Attended Sysupgrade (ASU) client settings. Its defaults
are defined in `roles/router_system/defaults/main.yml`.

The logging defaults are `router_system_log_proto: udp`,
`router_system_conloglevel: 8`, and `router_system_cronloglevel: 7`.
The remote syslog destination has no default: set `router_system_log_ip`
only for routers that should send logs to a central server. For example, in
`host_vars/router1.yml`:

```yaml
---
router_system_log_ip: 192.0.2.234
```

Replace the documentation-only address with your actual syslog server
address. If `router_system_log_ip` is undefined, the role leaves the
existing UCI option unchanged.

The role also configures these ASU client options:

- `router_system_asu_auto_search: 0`
- `router_system_asu_login_check_for_upgrades: 1`
- `router_system_asu_upgrade_packages: 1`

These settings only have an effect when the relevant ASU client components
are installed. The role configures UCI options only; it does not install the
package. Add `luci-app-attendedsysupgrade` to `router_packages_list` if it is
not already present on the router. See the
[OpenWrt ASU documentation](
https://openwrt.org/docs/guide-user/installation/attended.sysupgrade).

### Configure packages and managed services

The `router_packages` role installs the packages listed in
`router_packages_list` and derives additional packages from the services
managed by `router_base`. The service list is configured with
`router_base_services`; the mapping from service names to package names is
`router_packages_service_package_map`, whose defaults are defined in
`roles/router_packages/defaults/main.yml`.

Each mapping entry is a list of packages. A service can therefore require
multiple packages, and its service name does not have to match its package
name. Every service in `router_base_services` must have an entry in the
mapping; otherwise the package role fails with an assertion error. Duplicate
package names are installed only once.

Do not add packages to `router_packages_list` solely because they are
required by a managed service. For example, `snmpd` and `xinetd` are
installed automatically while they remain in the default `router_base_services`
list and have their default mappings. Add packages to `router_packages_list`
when you want them independently of the managed service list.

The standard `playbooks/site.yml` playbook passes `router_base_services`
to the package role. When using `router_packages` independently, set
`router_packages_managed_services` yourself; it defaults to an empty list
rather than assuming that every service in the mapping is managed.

You can customize package lists and managed services in inventory variables
without changing the playbook.

#### Same package list for all routers

Create `group_vars/openwrt.yml` next to your inventory file:

```yaml
---
router_packages_list:
  - busybox
  - openwrt-keyring
  - rsync
router_base_services:
  - snmpd
  - xinetd
```

All hosts in the `openwrt` group use these values unless overridden by
host-specific variables. The example explicitly lists the default managed
services to show where service management is configured; if you only want to
change the package list, you do not need to set `router_base_services`.

#### Different package lists per router

For the inventory host `router1`, create `host_vars/router1.yml` next to
the inventory file:

```yaml
---
router_packages_list:
  - busybox
  - openwrt-keyring
```

For `router2`, create `host_vars/router2.yml`:

```yaml
---
router_packages_list:
  - busybox
  - openwrt-keyring
  - rsync
  - uhttpd
```

Host-specific values override group variables. A host's
`router_packages_list` replaces the group list completely; Ansible does not
merge the two lists automatically. If you want common packages on every
router, keep them in the group list and repeat the full desired list in each
host-specific override.

#### Map a custom managed service to packages

If you add a service to `router_base_services`, add its package mapping too.
For example, if the `example-daemon` service is provided by the
`example-package` package, define both variables in inventory:

```yaml
---
router_base_services:
  - snmpd
  - example-daemon

router_packages_service_package_map:
  snmpd:
    - snmpd
  xinetd:
    - xinetd
  example-daemon:
    - example-package
```

The mapping variable replaces the default mapping when set in inventory;
include every mapping entry you still need, including the defaults for
services you continue to manage. To make one service install multiple
packages, list all of those package names under that service.

You can combine group and host variables with the same unchanged playbook:

```bash
ansible-playbook -i inventory.ini playbooks/site.yml
ansible-playbook -i inventory.ini playbooks/site.yml --limit router2
```

### Configure network settings

The `router_network` role can configure IPv4 addressing on explicitly
listed OpenWrt network interface sections. The default mode is `dhcp`, but
the default empty `router_network_interfaces` mapping makes no interface
changes. Only list interfaces that this role should manage.

#### Obtain interface address, route, and DNS through DHCP

For example, to configure the `wan` interface as a DHCP client:

```yaml
---
router_network_interface_mode: dhcp
router_network_interfaces:
  wan: {}
```

In DHCP mode, the role sets `proto=dhcp`, enables peer-provided DNS, and
removes static address, netmask, gateway, and DNS options for each listed
interface. The DHCP server must provide a default route and DNS information
for those to become available.

#### Configure a static interface

For static mode, each listed interface needs an IPv4 address and netmask.
Gateway and DNS are optional:

```yaml
---
router_network_interface_mode: static
router_network_interfaces:
  lan:
    ipaddr: 192.0.2.1
    netmask: 255.255.255.0
    gateway: 192.0.2.254
    dns:
      - 192.0.2.53
      - 192.0.2.54
```

Static mode disables peer-provided DNS and configures the supplied gateway
and DNS servers. Omit `gateway` to remove a configured gateway, and omit
`dns` to remove configured DNS servers. Interface changes trigger a network
reload and may interrupt connectivity; apply them carefully on real routers.

For controlled configuration-only runs, set
`router_network_apply_runtime_changes: false`. The role still commits UCI
settings, but it skips the network reload and dnsmasq restart handlers. This
is intended for tests or carefully planned maintenance, not normal router
configuration; the runtime settings remain unapplied until the relevant
services are reloaded.

The current implementation uses one addressing mode for all interfaces
listed in `router_network_interfaces`. Mixed DHCP/static interface modes
are intentionally not supported yet. IPv6 configuration is outside this
feature's scope.

#### Configure the IPv4 DHCP server

The separate `router_network_dhcp_interfaces` mapping controls whether the
DHCP server runs on each OpenWrt DHCP section. This is independent of whether
the router's own interface acts as a DHCP client. Set each managed DHCP
section to `enabled` or `disabled`; sections omitted from the mapping are
left unchanged.

For example, to disable IPv4 DHCP on LAN and enable it on the guest network,
add this to `group_vars/openwrt.yml`:

```yaml
---
router_network_dhcp_interfaces:
  lan: disabled
  guest: enabled
```

The role sets `dhcp.<section>.ignore=0` for `enabled` and `1` for
`disabled`. This controls IPv4 DHCP only; it does not configure DHCPv6 or
IPv6 Router Advertisements. Configure those separately if needed.

The role restarts dnsmasq when the DHCP server configuration changes. If a
previous dnsmasq restart failed, set `router_network_force_restart: true`
for a run to request another restart even when the DHCP settings are already
correct. The default is `false`.

#### Discover existing OpenWrt configuration

For a router that already has manual changes, use the read-only discovery
script `scripts/owrt-extra.sh` to compare the live system with a reconstructed
factory reference and collect likely Ansible candidates. It must be copied to
the router and run there as root on OpenWrt; it is not an Ansible playbook.

```sh
scp scripts/owrt-extra.sh root@router1:/tmp/owrt-extra.sh
ssh root@router1 'sh /tmp/owrt-extra.sh'
```

The report is written to `/tmp/owrt-diff/` in RAM. Treat it as sensitive:
UCI output can include Wi-Fi passwords and other secrets. The script does not
print password hashes, and host-key export is opt-in (`-H`); with `-H`,
private keys are copied in plaintext under `/tmp/owrt-diff/secrets/`.
Review and securely retrieve only what you need, then remove the report and
script from the router.

Options: `-k` keeps the temporary factory reference mounted for inspection,
`-f` rebuilds that reference, and `-H` exports host keys. Read the script's
help (`sh /tmp/owrt-extra.sh -h`) before using these options.

The report includes a UCI diff, overlay-file candidates, package and service
differences, and—when supported—`apk audit --system` output in
`/tmp/owrt-diff/apk-audit-system.txt`. The APK audit can detect modified
package-owned system files outside protected configuration paths, but it does
not report arbitrary untracked files; the overlay scan handles a different
set of candidates. This check requires an APK-based OpenWrt system (25.12+)
and is skipped with a warning when the command or option is unavailable.
CI checks shell syntax and command-line behavior using the OpenWrt 25.12 rootfs image. It does not run the full discovery workflow in that container: the rootfs image does not provide the same device-like overlay environment as a booted OpenWrt router, so a container startup check is not a reliable substitute. The mount/chroot reconstruction and detection of real overlay changes still need validation on a suitable OpenWrt VM or physical router.

This is an investigative report, not an automatic Ansible generator. Runtime
state such as manually installed nftables rules, `ip` changes, temporary
`sysctl` values, loaded modules, and running processes is not comprehensively
captured. Files in the overlay may also be caches or service state rather than
configuration. Review each candidate before managing it with Ansible. Data
outside the overlay, such as calibration data and bootloader storage, is not
suitable for normal Ansible configuration.

## Audit installed packages

The audit playbook requires a baseline package list on each target router.
The default path is:

```text
/etc/backup/installed_packages.txt
```

The baseline must already exist on the target host. The role does not create
or deploy this baseline. Ensure that it is generated or copied to each router
before running the audit.

Run the audit against all routers:

```bash
ansible-playbook -i inventory.ini playbooks/audit_packages.yml
```

Or run it against one router:

```bash
ansible-playbook -i inventory.ini playbooks/audit_packages.yml --limit router1
```

To use a different baseline path, override the role default:

```bash
ansible-playbook -i inventory.ini playbooks/audit_packages.yml \
  -e router_package_audit_baseline=/path/to/installed_packages.txt
```

The path is interpreted on the target router, not on the Ansible control
node. The audit installs `diffutils` if needed, compares sorted package
names, and displays additions or removals. It does not change the installed
package set to match the baseline.

## Customize other role variables

Role defaults are documented in the corresponding
`roles/<role_name>/defaults/main.yml` files. Override them through
`group_vars/openwrt.yml`, `host_vars/<inventory_hostname>.yml`, or
Ansible extra variables (`-e`) when appropriate. Host variables take
precedence over group variables; extra variables have higher precedence
than both.
