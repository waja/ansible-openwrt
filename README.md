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
  `router_network`, and the opt-in `router_snmpd` role.
- `playbooks/audit_packages.yml` compares the installed packages on each
  router against a saved package-list baseline. It reports differences but
  does not install or remove packages to reconcile them.

Both playbooks target the `openwrt` inventory group.

For role-specific settings and examples, start with the
[router configuration overview](docs/configuration.md) and follow its links
to the individual [system](docs/roles/router_system.md),
[firewall](docs/roles/router_firewall.md),
[network](docs/roles/router_network.md),
[packages](docs/roles/router_packages.md),
[base services](docs/roles/router_base.md),
[SNMP](docs/roles/router_snmpd.md),
[LibreNMS](docs/roles/router_librenms.md), and
[package audit](docs/roles/router_package_audit.md) guides.

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

See the [router configuration overview](docs/configuration.md) for playbook usage, inventory organization, and links to the detailed role guides.

## Repository layout

- `playbooks/site.yml` — standard router configuration
- `playbooks/audit_packages.yml` — installed-package audit
- `roles/router_system/` — hostname, timezone, NTP, logging, ASU settings,
  and optional additional Dropbear listeners
- `roles/router_firewall/` — firewall default policies, typed declarative
  zones with safe adoption/removal and explicit option removal, and optional
  WAN access for additional Dropbear ports
- `roles/router_packages/` — package installation and restart handling
- `roles/router_base/` — base service configuration
- `roles/router_network/` — IPv4 interface addressing and per-interface DHCP server settings
- `roles/router_snmpd/` — optional SNMP community configuration
- `roles/router_librenms/` — optional LibreNMS wireless sensor integration
- `roles/router_package_audit/` — package baseline comparison
- `requirements.yml` — pinned Ansible role and collection dependencies
- `extensions/molecule/default/` — Molecule test scenario
- `extensions/molecule/network-static/` — static network configuration tests
- `extensions/molecule/network-dhcp/` — DHCP configuration tests
- `.github/workflows/molecule.yml` — lint and Molecule CI workflow

## Script and documentation checks

The CI workflow checks shell scripts with ShellCheck, and
Markdown files with `markdownlint-cli2` and `codespell`. To run these
checks locally, install the same tools and run:

```bash
shellcheck --shell=sh scripts/*.sh
markdownlint-cli2 "**/*.md"
git ls-files -z -- scripts/ '*.md' ':(exclude)collections/**' | xargs -0 -r codespell --check-filenames
```

These checks detect shell issues, formatting problems, Markdown conventions,
and likely spelling errors. They do not provide a full grammar check.

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

The syntax checks use the inventory so Ansible can resolve the `openwrt`
host pattern. These checks do not replace running the Molecule scenario.

The lint dependencies are pinned in the generated lockfile. Edit the
corresponding `.in` file for direct dependency changes, then regenerate all
lockfiles with `bash scripts/update-ci-lockfiles.sh` using Python 3.14 and
`pip-tools==7.6.2`. CI validates that the committed lockfiles are current.
