# README.md
# Ansible OpenWrt Router Configuration

This repository provides Ansible playbooks and roles to configure OpenWrt
routers and compare their installed packages against a saved baseline.

## License

This project is licensed under the GNU General Public License v3.0 or, at
your option, any later version (`GPL-3.0-or-later`). See [LICENSE](LICENSE)
for the full license text.

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

### Run selected roles

The standard playbook supports role-level tags matching the role names:
`router_network`, `router_system`, `router_firewall`, `router_packages`,
and `router_base`. For example, to run only the base-service role on one
router:

```bash
ansible-playbook -i inventory.ini playbooks/site.yml \
  --limit router1 --tags router_base
```

Use `--list-tasks --tags router_base` to inspect the selected tasks first.
Selecting a role does not automatically run other project roles that it may
depend on. The OpenWrt initialization role still runs automatically. The
`router_network` role can interrupt connectivity when runtime changes apply.

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

See the [router configuration guide](docs/configuration.md) for the complete instructions on applying the playbooks and configuring firewall defaults, system settings, packages and managed services, inventory variables, and network settings.

## Repository layout

- `playbooks/site.yml` — standard router configuration
- `playbooks/audit_packages.yml` — installed-package audit
- `roles/router_system/` — hostname, timezone, NTP, logging, and ASU settings
- `roles/router_firewall/` — configurable firewall default policies
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
python -m pip install --require-hashes \
  -r requirements/ci/lint.txt
```

Then run the checks used by the project:

```bash
yamllint .
ansible-lint --exclude collections/ansible_collections/community/openwrt/
ansible-playbook -i inventory.ini --syntax-check playbooks/site.yml
ansible-playbook -i inventory.ini --syntax-check playbooks/audit_packages.yml
```

The lint dependencies are pinned in the generated
`requirements/ci/lint.txt` lockfile. Direct dependency
changes belong in the corresponding `.in` file; regenerate all lockfiles
with `bash scripts/update-ci-lockfiles.sh` using Python 3.14 and
`pip-tools==7.6.2`. CI installs the generated lockfiles with
`--require-hashes`. The syntax checks use the inventory so Ansible can
resolve the `openwrt` host pattern. These checks do not replace running
the Molecule scenario.
