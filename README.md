# README.md
# Ansible OpenWrt Router Configuration

This repository provides Ansible playbooks and roles to configure OpenWrt
routers and compare their installed packages against a saved baseline.

The playbooks use the inventory group `openwrt`. You normally do not need
to copy or edit the playbooks for your own routers: define your hosts in an
inventory and customize variables there.

## What the playbooks do

- `playbooks/site.yml` runs the standard configuration:
  `community.openwrt.init`, `router_packages`, `router_base`, and
  `router_network`.
- `playbooks/audit_packages.yml` compares the installed packages on each
  router against a saved package-list baseline. It reports differences but
  does not install or remove packages to reconcile them.

Both playbooks target the `openwrt` inventory group.

## Requirements

- SSH access to each OpenWrt router, typically with a configured SSH key.
- The Ansible dependencies listed in `requirements.yml`.
- Either Ansible and Python on the control node, or Docker to run Ansible
  in a container.

### Run Ansible directly on the control node

Install the pinned dependencies into the standard user Ansible paths:

```bash
ansible-galaxy role install -r requirements.yml \
  --roles-path ~/.ansible/roles
ansible-galaxy collection install -r requirements.yml \
  --collections-path ~/.ansible/collections
```

### Run Ansible in Docker with `willhallonline/ansible`

The [willhallonline/ansible image](https://github.com/willhallonline/ansible)
provides Ansible and Python in a container, so they do not need to be
installed on the control node. The examples run Ansible from this repository
directory and keep the inventory and playbooks on the host.

The examples use `latest`, matching the tested setup. For reproducible
runs, choose a specific tag from the
[available image tags](https://hub.docker.com/r/willhallonline/ansible/tags)
and use it consistently in place of `latest`.

Mount the repository at `/ansible`, your SSH directory at
`/home/ansible/.ssh`, and your Ansible dependency directory at
`/home/ansible/.ansible`. The SSH directory is mounted read-only; do not
copy private keys into the image or commit them to the repository.

First, verify that the image can run Ansible:

```bash
docker run --rm willhallonline/ansible:latest ansible --version
```

The `ansible.utils.ipaddr` filter also requires the Python package
`netaddr` on the Ansible control node. The image container is disposable,
so install it into the persistent `~/.ansible/python` directory once and
add that directory to `PYTHONPATH` whenever Ansible runs:

```bash
docker run --rm -it \
  -v "$HOME/.ansible:/home/ansible/.ansible" \
  willhallonline/ansible:latest \
  python -m pip install --target /home/ansible/.ansible/python netaddr==1.3.0
```

Install the pinned role and collection dependencies from `requirements.yml`.
The `~/.ansible` mount keeps them available for later runs:

```bash
docker run --rm -it \
  -v "$PWD:/ansible" \
  -v "$HOME/.ssh:/home/ansible/.ssh:ro" \
  -v "$HOME/.ansible:/home/ansible/.ansible" \
  --env PYTHONPATH=/home/ansible/.ansible/python \
  --workdir /ansible \
  willhallonline/ansible:latest \
  /bin/sh -c 'ansible-galaxy role install -r requirements.yml \
    --roles-path /home/ansible/.ansible/roles &&
    ansible-galaxy collection install -r requirements.yml \
    --collections-path /home/ansible/.ansible/collections'
```

Once the dependencies are installed, use the same Docker invocation for all
validation and execution steps. The examples below assume that `inventory.ini`
is in the repository directory mounted at `/ansible`.

Check the playbook syntax first. This does not connect to the router:

```bash
docker run --rm -it \
  -v "$PWD:/ansible" \
  -v "$HOME/.ssh:/home/ansible/.ssh:ro" \
  -v "$HOME/.ansible:/home/ansible/.ansible" \
  --env PYTHONPATH=/home/ansible/.ansible/python \
  --workdir /ansible \
  willhallonline/ansible:latest \
  ansible-playbook -i inventory.ini playbooks/site.yml --syntax-check
```

Then test SSH access and execute a command on OpenWrt without requiring
Python on the router:

```bash
docker run --rm -it \
  -v "$PWD:/ansible" \
  -v "$HOME/.ssh:/home/ansible/.ssh:ro" \
  -v "$HOME/.ansible:/home/ansible/.ansible" \
  --env PYTHONPATH=/home/ansible/.ansible/python \
  --workdir /ansible \
  willhallonline/ansible:latest \
  ansible -i inventory.ini openwrt -m ansible.builtin.raw \
    -a 'ubus call system board' -e ansible_connection=ssh
```

Finally, apply the configuration only after reviewing the intended inventory
and network variables. The `router_network` role can change connectivity:

```bash
docker run --rm -it \
  -v "$PWD:/ansible" \
  -v "$HOME/.ssh:/home/ansible/.ssh:ro" \
  -v "$HOME/.ansible:/home/ansible/.ansible" \
  --env PYTHONPATH=/home/ansible/.ansible/python \
  --workdir /ansible \
  willhallonline/ansible:latest \
  ansible-playbook -i inventory.ini playbooks/site.yml \
    -e ansible_connection=ssh
```

To target one router, add `--limit router1` to the relevant Ansible command.
The examples assume SSH host keys are already present in
`~/.ssh/known_hosts`. If your SSH configuration contains options that are
specific to macOS, such as `UseKeychain`, the Linux SSH client in the
container may not support them. Adjust the SSH configuration used by the
container as needed.

These examples assume SSH host keys are already present in
`~/.ssh/known_hosts`. If your SSH configuration contains options that are
specific to macOS, such as `UseKeychain`, the Linux SSH client in the
container may not support them. Adjust the SSH configuration used by the
container as needed.

To run the package audit instead, replace the playbook path with
`playbooks/audit_packages.yml`. To target one router, add
`--limit router1` to the `ansible-playbook` command.

The container needs network access to the routers and valid SSH
authentication. The image does not make Python available on the OpenWrt
targets; the project's tasks must remain compatible with Python-free
OpenWrt systems.

## Define your routers

Create an inventory file, for example `inventory.ini`:

```ini
[openwrt]
router1 ansible_host=192.0.2.1
router2 ansible_host=192.0.2.2

[openwrt:vars]
ansible_user=root
```

Replace the documentation IP addresses with the real management addresses
of your routers. Configure SSH authentication as appropriate for your
environment. The names `router1` and `router2` are inventory hostnames;
they are also used when defining host-specific variables.

The Docker-based syntax check and `ubus` connectivity test are documented
in the Docker section above. The `ubus` test uses Ansible's raw module, so
it does not require Python on the OpenWrt target. It also checks that
`ubus` is available, so a failure may indicate an issue beyond SSH itself.

Ansible's normal ping module requires Python on the target and is therefore
not a suitable connectivity test for Python-free OpenWrt images.

## Configure the routers

Apply the standard configuration using the Docker command shown in the
Docker section above. To target one router, add `--limit router1` to that
`ansible-playbook` command.

The `site.yml` playbook configures explicitly selected network settings first,
then initializes OpenWrt, applies system settings, installs the configured
packages, and configures base services and removes obsolete configuration files.

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

### Configure packages per router

The `router_packages` role uses `router_packages_list` to define the
requested packages. The role also adds its required service packages from
`router_packages_required_services`. The defaults are defined in
`roles/router_packages/defaults/main.yml`.

You can set package lists in inventory variables without changing the
playbook.

#### Same package list for all routers

Create `group_vars/openwrt.yml` next to your inventory file:

```yaml
---
router_packages_list:
  - busybox
  - openwrt-keyring
  - snmpd
  - xinetd
```

All hosts in the `openwrt` group use this list unless overridden by a
host-specific variable.

#### Different package lists per router

For the inventory host `router1`, create `host_vars/router1.yml` next to
the inventory file:

```yaml
---
router_packages_list:
  - busybox
  - openwrt-keyring
  - snmpd
  - xinetd
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

### Audit installed packages

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

## Repository layout

- `playbooks/site.yml` — standard router configuration
- `playbooks/audit_packages.yml` — installed-package audit
- `roles/router_system/` — hostname, timezone, NTP, logging, and ASU settings
- `roles/router_packages/` — package installation and restart handling
- `roles/router_base/` — base service configuration
- `roles/router_network/` — IPv4 interface addressing and DHCP server control
- `roles/router_package_audit/` — package baseline comparison
- `requirements.yml` — pinned Ansible role and collection dependencies
- `extensions/molecule/default/` — Molecule test scenario
- `extensions/molecule/network-static/` — static network configuration tests
- `extensions/molecule/network-dhcp/` — DHCP configuration tests
- `.github/workflows/molecule.yml` — lint and Molecule CI workflow

## Development checks

Install the lint tools used by the project, then run the checks. On a control
node with Python and pip available, install them with:

```bash
python -m pip install yamllint ansible-lint
```

Then run the checks used by the project:

```bash
yamllint .
ansible-lint --exclude collections/ansible_collections/community/openwrt/
ansible-playbook -i inventory.ini --syntax-check playbooks/site.yml
ansible-playbook -i inventory.ini --syntax-check playbooks/audit_packages.yml
```

The syntax checks use the inventory so Ansible can resolve the `openwrt`
host pattern. These checks do not replace running the Molecule scenario.
