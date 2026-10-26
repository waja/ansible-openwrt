# README.md
# Ansible OpenWrt Router Configuration

This repository provides Ansible playbooks and roles to configure OpenWrt
routers and compare their installed packages against a saved baseline.

The playbooks use the inventory group `openwrt`. You normally do not need
to copy or edit the playbooks for your own routers: define your hosts in an
inventory and customize variables there.

## What the playbooks do

- `playbooks/site.yml` runs the standard configuration:
  `community.openwrt.init`, `router_packages`, and `router_base`.
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
  --collections-path ~/.ansible/collections --force
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
    --collections-path /home/ansible/.ansible/collections --force'
```

Once the dependencies are installed, run the playbook:

```bash
docker run --rm -it \
  -v "$PWD:/ansible" \
  -v "$HOME/.ssh:/home/ansible/.ssh:ro" \
  -v "$HOME/.ansible:/home/ansible/.ansible" \
  --env PYTHONPATH=/home/ansible/.ansible/python \
  --workdir /ansible \
  willhallonline/ansible:latest \
  ansible-playbook -i inventory.ini playbooks/site.yml
```

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

The `site.yml` playbook runs the initialization role first, then installs
the configured packages, and finally configures base services and removes
obsolete configuration files.

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
