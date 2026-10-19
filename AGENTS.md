# AGENTS.md

## Project context

Ansible project `waja.ansible_openwrt` for configuring OpenWrt routers.
Tested with Molecule in Docker containers against OpenWrt 24.10 (opkg) and
25.12 (apk). CI runs on GitHub Actions: lint → Molecule matrix.

## Directory structure (binding)

- `extensions/molecule/default/` – Molecule scenario
  (`molecule.yml`, `prepare.yml`, `converge.yml`)
- `roles/<role_name>/` – roles with `tasks/main.yml` (and `defaults/`
  if variables should be overridable)
- `./collections/` – installed dependencies, **never edit**
- `.github/workflows/molecule.yml` – CI pipeline
- `.github/workflows/pr-base-check.yml` – warns on PRs targeting `master`

Note: this repository is not a full Ansible collection. There is no
`galaxy.yml`, `meta/`, or `plugins/` directory. Do not create or
reference them unless explicitly asked.

## Code style

### YAML
- 2-space indentation, no tabs
- Maximum line length 80 characters (`.yamllint`)
- File ends with a newline
- Boolean values as `true`/`false`, not `yes`/`no`
- Wrap long strings with `>-` (folded), e.g. for `MOLECULE_GLOB`
- The 80-character limit also applies to embedded code in block scalars
  (e.g. JavaScript in `actions/github-script`), even though `yamllint`
  does not check it. Keep those lines short or wrap them manually.

### Ansible
- Always use FQCN:
  - `ansible.builtin.include_role`, `ansible.builtin.raw`,
    `ansible.builtin.command` for generic tasks
  - `community.openwrt.uci` for UCI operations
- Give tasks descriptive names (`name:`), in English
- In `converge.yml`: pass test values directly to `include_role` via
  `vars:` so they are visible and scoped
- Do not use `command`/`shell` when a module exists;
  `ansible.builtin.raw` is allowed in `prepare.yml` because no Python
  environment is available on the target yet

### Role variables
- Must be prefixed with the role name:
  `router_hostname_value`, `router_packages_list`
- Define defaults in `roles/<name>/defaults/main.yml` so the role runs
  without explicitly set variables
- Do not use `vars:` in `tasks/main.yml` for values that should be
  overridable

### Package installation (OpenWrt-specific)
- **Never** hardcode `community.openwrt.apk` or `community.openwrt.opkg`.
- Always select dynamically via the fact set by `community.openwrt.init`:
  ```yaml
  - name: Install packages dynamically
    action: "community.openwrt.{{ openwrt_package_manager }}"
    args:
      name: "{{ router_packages_list | join(',') }}"
      state: present
      update_cache: true
  ```

## Molecule / OpenWrt containers (current state)

- `driver: docker` with `command: /sbin/init` and
  `pre_build_image: true`
- `tmpfs: /tmp:exec,mode=1777` – required so Ansible can write there
- Image tag: `openwrt/rootfs:x86_64-openwrt-<version>`
- Inventory variables for all hosts:
  - `ansible_connection: docker`
  - `ansible_remote_tmp: /tmp`
  - `openwrt_remote_tmp: /tmp`
- `prepare.yml` waits via `ansible.builtin.raw` for
  `/var/run/ubus/ubus.sock` and `ubus list`
- `community.openwrt.init` must run before all other roles in
  `converge.yml`

## Important commands

```bash
# Syntax check of the Molecule playbook
ansible-playbook extensions/molecule/default/converge.yml --syntax-check

# Linting
yamllint .
ansible-lint --exclude collections/ansible_collections/community/openwrt/

# Molecule locally (container stays up after a failure)
molecule test --destroy=never
molecule login --host openwrt-25.12
molecule destroy

# Install collections (standard path)
ansible-galaxy collection install community.openwrt community.docker
```

## CI pipeline (`.github/workflows/molecule.yml`)

- **Triggers**: `workflow_dispatch`, `pull_request`, `push` to
  `$default-branch`, `development`, `master`
- **Job `lint`**:
  - `yamllint .`
  - `ansible-lint --exclude collections/ansible_collections/community/openwrt/`
  - `ANSIBLE_COLLECTIONS_PATH` contains the workspace `collections/`,
    `~/.ansible/collections` and `/usr/share/ansible/collections`
- **Job `molecule`** (`needs: lint`):
  - Matrix `openwrt-25.12`, `openwrt-24.10`, `fail-fast: false`
  - `MOLECULE_GLOB` at workflow level
  - `molecule test --destroy=never` (no `--limit` needed because
    `MOLECULE_GLOB` selects the scenario)
  - On failure: `docker ps -a`, `docker inspect`, `docker logs`
  - `molecule destroy` with `if: always()`
- Python version: `3.14` (in `setup-python` and centrally if needed)

## Don'ts

- Do not modify anything under `./collections/`
- Do not use `yes`/`no` in YAML
- Do not hardcode package manager modules
- Do not use role variables without the role prefix
- Do not use `sleep infinity` in `molecule.yml` (BusyBox does not support it)
- Do not exceed 80 characters per line (except with `# yamllint disable-line`)
- Do not use `become: true` in Molecule tests – the container runs as root
- Do not add `--limit` to the pipeline as long as `MOLECULE_GLOB` selects
  the scenario and the matrix runs one platform per job
- Do not exceed 80 characters per line (except with `# yamllint disable-line`)
- Do not write long lines inside `script: |` blocks in GitHub workflows –
  `yamllint` does not catch them, but they violate the same style rule

## When in doubt

- `roles/router_hostname` is the minimal role example
- `converge.yml` shows how test values are passed via `vars:` to
  `include_role`
- Before pushing, run locally: `yamllint .`, `ansible-lint` and
  `molecule test --destroy=never`
- Do not suppress `yamllint` errors with `# noqa` – fix the root cause