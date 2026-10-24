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

### Run Ansible in Docker with `serversideup/ansible`

The [serversideup/ansible image](https://github.com/serversideup/docker-ansible)
provides Ansible and Python in a container, so they do not need to be
installed on the control node. The examples run Ansible from this repository
directory and keep the inventory and playbooks on the host.

Choose a specific image tag from the
[available tags](https://hub.docker.com/r/serversideup/ansible/tags).
Pin the tag rather than using `latest`, so deployments use a predictable
Ansible and Python environment. Replace `<pinned-tag>` in the examples
with the tag you selected.

The image uses `/ansible` as its working directory and `/ssh` for SSH
configuration. Mount the repository at `/ansible` and your SSH directory
at `/ssh`. The SSH directory is mounted read-only below; do not copy
private keys into the image or commit them to the repository.

First, verify that the selected image can run Ansible:

```bash
docker run --rm serversideup/ansible:<pinned-tag> ansible --version
```

The container also needs the role and collection dependencies from
`requirements.yml`. For a simple first run, install them and execute the
playbook in the same container invocation:

```bash
docker run --rm -it \
  -v "$PWD:/ansible" \
  -v "$HOME/.ssh:/ssh:ro" \
  -e PUID="$(id -u)" \
  -e PGID="$(id -g)" \
  serversideup/ansible:<pinned-tag> \
  sh -lc 'ansible-galaxy role install -r requirements.yml \
    --roles-path /tmp/ansible-roles &&
    ansible-galaxy collection install -r requirements.yml \
    --collections-path /tmp/ansible-collections &&
    ANSIBLE_ROLES_PATH=/tmp/ansible-roles \
    ANSIBLE_COLLECTIONS_PATH=/tmp/ansible-collections \
    ansible-playbook -i inventory.ini playbooks/site.yml'
```

This downloads the pinned dependencies on each fresh run. For frequent use,
build a small image on top of `serversideup/ansible` that installs the
repository's `requirements.yml` at build time. The shorter invocation then
works with the same volume mounts:

```bash
docker run --rm -it \
  -v "$PWD:/ansible" \
  -v "$HOME/.ssh:/ssh:ro" \
  -e PUID="$(id -u)" \
  -e PGID="$(id -g)" \
  ansible-openwrt:<pinned-tag> \
  ansible-playbook -i inventory.ini playbooks/site.yml
```

Keep the base image tag and dependency versions pinned so the control-node
environment is reproducible. The examples assume SSH host keys are already
present in `~/.ssh/known_hosts`; if your SSH configuration needs to update
that file, provide a writable known-hosts file as described in the upstream
image documentation.

To run the package audit instead, replace the playbook path with
`playbooks/audit_packages.yml`. To target one router, add
`--limit router1` to the `ansible-playbook` command.

The container still needs network access to the routers and valid SSH
authentication. The image does not make Python available on the OpenWrt
targets; the project's tasks must remain compatible with Python-free
OpenWrt systems. See the upstream
[image documentation](https://github.com/serversideup/docker-ansible)
for SSH-agent forwarding and other configuration options.

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

Check SSH connectivity without requiring Python on the router:

```bash
ansible -i inventory.ini openwrt \
  -m ansible.builtin.raw -a 'ubus call system board'
```

This runs `ubus call system board` over SSH using Ansible's raw module.
It verifies that Ansible can connect and execute a command on OpenWrt
without requiring Python on the target. It also checks that `ubus` is
available, so a failure may indicate an issue beyond SSH connectivity.

On targets that have a usable Python environment, you can additionally
use Ansible's normal ping module:

```bash
ansible -i inventory.ini openwrt -m ansible.builtin.ping
```

The ping module requires Python on the target and will fail on Python-free
OpenWrt images even when SSH connectivity works.

## Configure the routers

Apply the standard configuration to all routers in the inventory group:

```bash
ansible-playbook -i inventory.ini playbooks/site.yml
```

Target just one router with `--limit`:

```bash
ansible-playbook -i inventory.ini playbooks/site.yml --limit router1
```

The `site.yml` playbook runs initialization first, installs the configured
packages, configures base services and removes obsolete configuration files,
then applies the network configuration through `router_network`.

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

The `router_network` role is the home for network configuration. Its first
feature explicitly configures IPv4 DHCP status per OpenWrt DHCP section.
The standard `site.yml` playbook includes this role. Set each managed
section to `enabled` or `disabled`; sections omitted from the mapping are
left unchanged. The default empty mapping therefore preserves existing
DHCP settings.

For example, to disable IPv4 DHCP on LAN and enable it on the guest network
for every router, add this to `group_vars/openwrt.yml`:

```yaml
---
router_network_dhcp_interfaces:
  lan: disabled
  guest: enabled
```

You can instead define the variable in `host_vars/<inventory_hostname>.yml`
to configure DHCP only on specific routers. Keys are existing OpenWrt DHCP
configuration section names, such as `lan` or `guest`. Each value must be
`enabled` or `disabled`; invalid values and unknown section names fail
validation rather than silently changing other interfaces.

The role sets `dhcp.<interface>.ignore=0` for `enabled` and `1` for
`disabled`. This controls IPv4 DHCP only; it does not configure DHCPv6 or
IPv6 Router Advertisements. Configure those separately if needed.

The network role serializes DHCP reconciliation and shares a service-restart
lock with the package and base roles. Lock acquisition waits up to the
configured timeout (1860 seconds by default). Locks are not reclaimed based
on age, because an old lock may still belong to an active run. If a run is
interrupted and leaves a lock behind, confirm that no Ansible run is active
before manually removing the corresponding lock directory under
`/root/.ansible-locks` or the compatibility lock
`/tmp/router-packages-restart-lock`.

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
- `roles/router_packages/` — package installation and restart handling
- `roles/router_base/` — base service configuration
- `roles/router_network/` — network configuration, initially IPv4 DHCP control
- `roles/router_package_audit/` — package baseline comparison
- `requirements.yml` — pinned Ansible role and collection dependencies
- `extensions/molecule/default/` — Molecule test scenario
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
