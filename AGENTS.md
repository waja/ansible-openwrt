# AGENTS.md

## Project context

Ansible project `waja.ansible_openwrt` for configuring OpenWrt routers.
Tested with Molecule in Docker containers against OpenWrt 24.10 (opkg) and
25.12 (apk). CI runs on GitHub Actions.

Pull requests target `development`, not `master`. A dedicated workflow
warns on PRs that target `master` and adds the `needs-rebase` label.

## Directory structure (binding)

- `playbooks/site.yml` – standard configuration for all OpenWrt routers
- `playbooks/audit_packages.yml` – optional installed-package comparison
- `extensions/molecule/default/` – Molecule scenario
  (`molecule.yml`, `prepare.yml`, `converge.yml`)
- `roles/router_packages/` – dynamically installs the default package list
- `roles/router_base/` – enables core services and removes obsolete config
- `roles/router_package_audit/` – optional comparison with a saved baseline
- `roles/<role_name>/` – roles with `tasks/main.yml` and
  `defaults/main.yml`
- `./collections/` – installed dependencies, **never edit**, must be
  git-ignored
- `requirements.yml` – authoritative, version-pinned source for
  Ansible role and collection dependencies used locally and in CI.
- `.github/workflows/molecule.yml` – main CI pipeline
- `.github/workflows/pr-base-check.yml` – warns on PRs targeting `master`

The repository is **not** a full Ansible collection. There is no
`galaxy.yml`, `meta/`, or `plugins/` directory, and none must be
created unless explicitly requested. The CI `check-structure` job detects
these paths and, if present, enables additional collection-level tests.
Their absence is the normal state, not a defect.

## Documentation maintenance

Keep `README.md` in sync with the actual repository behavior and usage.
Whenever a change affects playbooks, roles, variables/defaults, inventory
configuration, dependencies, supported OpenWrt versions, or user-facing
commands, review the README and update it when needed. Add or revise
examples when the supported way to use the project changes. Do not document
behavior that has not been implemented or verified. If a change genuinely
needs no README update, no documentation-only edit is required.

Keep the relevant operational details in `AGENTS.md` synchronized too,
especially when changing development instructions, repository conventions,
or CI workflows.

## Code style

### Line length
- Maximum 80 characters per physical line, by convention for all
  file types.
- `yamllint` enforces this for YAML files, including block scalars
  (`run: |`, `script: |`). It does not check Markdown or shell files.
- Do not suppress the rule with `# yamllint disable-line` unless the
  line cannot be wrapped (e.g. a long URL).

### YAML
- 2-space indentation, no tabs
- Start every YAML file with a comment containing its repository-relative
  path, followed by `---`
- File ends with a newline
- Boolean values as `true`/`false`, not `yes`/`no`
- Wrap long strings with `>-` (folded) at YAML level only. Never use
  YAML scalars inside embedded JavaScript or shell.

### Ansible
- Always use FQCN:
  - `ansible.builtin.include_role`, `ansible.builtin.raw`,
    `ansible.builtin.command` for generic tasks
  - `community.openwrt.uci` for UCI operations
- Give tasks descriptive names (`name:`), in English
- In `converge.yml`: pass test values directly to `include_role` via
  `vars:` so they are visible and scoped
- Do not use `command`/`shell` when a module exists.
- `ansible.builtin.raw` is allowed in `prepare.yml` because no Python
  environment is available on the target yet.
- A narrow additional exception is allowed when one remote operation must
  be followed immediately by a related state marker and no Ansible module
  can perform both actions together. In `router_base`, the service restart
  and its completion-marker write are run in one remote shell command.
  This reduces the risk that Ansible loses the task acknowledgement after
  the restart but before a separate marker task runs, which could cause an
  unnecessary restart on the next run. Do not use `raw` as a general
  replacement for available modules.

### Role variables
- Must be prefixed with the role name:
  `router_hostname_value`, `router_packages_list`
- Define defaults in `roles/<name>/defaults/main.yml` so the role runs
  without explicitly set variables
- Do not use `vars:` in `tasks/main.yml` for values that should be
  overridable

### Package installation (OpenWrt-specific)

**Never** hardcode `community.openwrt.apk` or `community.openwrt.opkg`.
Always select dynamically via the fact set by
`community.openwrt.init`:

    - name: Install requested and required packages dynamically
      action: "community.openwrt.{{ openwrt_package_manager }}"
      args:
        name: >-
          {{ (router_packages_list + router_packages_required_services)
             | unique | join(',') }}
        state: present
        update_cache: true
      register: router_packages_install_result

- The `action:` form is required. The module name cannot be used as a
  task key when built from a variable.
- Check the input format of the selected module (`opkg` and `apk` differ
  in some options) before copying an example.
- Keep the installation result registered as
  `router_packages_install_result`; restart-marker handling depends on
  its `changed` value.
- `router_packages` owns package installation; service configuration
  belongs in `router_base`.
- `router_package_audit` is optional because it requires the saved
  baseline file `/etc/backup/installed_packages.txt`.

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
- Currently only `openwrt-25.12` is defined in `platforms:` and enabled
  in the CI matrix. OpenWrt 24.10 is temporarily disabled because its
  opkg networking fails in CI. The workflow passes
  `--platform-name "${{ matrix.platform }}"` so each enabled matrix job
  tests its selected image.

## Adding a new role (checklist)

1. Create `roles/<role_name>/tasks/main.yml`.
2. Create `roles/<role_name>/defaults/main.yml` with prefixed variables.
3. Include the role in `extensions/molecule/default/converge.yml`
   **after** `community.openwrt.init`, passing test values via `vars:`.
4. Use FQCN modules only.
5. Make the entire converge run idempotent: a second converge must
   report no changes. Fix any task that reports `changed`
   unexpectedly. Use `changed_when: false` for read-only tasks and
   make module calls truly idempotent.
6. Install collections first (`ansible-galaxy collection install
   community.openwrt community.docker`), then run `yamllint .`,
   `ansible-lint` and `ansible-playbook --syntax-check` locally.

## Adding a new OpenWrt version (checklist)

1. Add the platform to `platforms:` in
   `extensions/molecule/default/molecule.yml` with the matching
   `openwrt/rootfs:x86_64-openwrt-<version>` image.
2. Add the same platform name to the matrix in
   `.github/workflows/molecule.yml`.
3. Pass the platform to Molecule with
   `--platform-name "${{ matrix.platform }}"` in the CI matrix job.
4. Verify that `community.openwrt.init` supports the version and sets
   `openwrt_package_manager` correctly.
5. If the version uses a different package manager, no role change is
   needed – the dynamic pattern handles it.

## Important commands

### Fast local checks

Run these after installing collections (see below).

    yamllint .
    ansible-lint --exclude collections/ansible_collections/community/openwrt/
    ansible-playbook extensions/molecule/default/converge.yml --syntax-check

### Full test run (CI task, requires Docker)

    # run the test, keep containers on failure
    molecule test --destroy=never
    # inspect a failed container
    molecule login --host openwrt-25.12
    # clean up afterwards
    molecule destroy

Molecule is a CI responsibility. Local runs require Docker and the
Molecule toolchain; if those are unavailable, rely on the fast checks
above and let CI run Molecule.

### Install Ansible dependencies

The repository-level `requirements.yml` is the source of truth for
pinned Ansible role and collection dependencies, including the
`community.docker` connection plugin required by Molecule. Install roles
and collections separately because they use different destination paths:

    ansible-galaxy role install -r requirements.yml \
      --roles-path ~/.ansible/roles
    ansible-galaxy collection install -r requirements.yml \
      --collections-path ~/.ansible/collections --force

Ansible's default search paths include these user-specific directories.
The Renovate configuration extends `config:recommended`, which enables
the Ansible Galaxy manager to propose updates for role and collection
entries in `requirements.yml`.

## CI pipeline (`.github/workflows/molecule.yml`)

The workflow file is the source of truth. Keep this section synchronized
with it.

- Python version: `3.14`
- Triggers: `workflow_dispatch`, `pull_request`, and pushes to
  `development` and `master`.
  **Note:** `$default-branch` is only a template macro for starter
  workflows, not a runtime expression in `branches` filters. Use the
  actual branch name.

### Jobs

- `lint`
  - Runs `yamllint .`.
  - Installs pinned roles and collections from `requirements.yml` into
    `~/.ansible/roles` and `~/.ansible/collections`, respectively.
  - Runs `ansible-lint`, excluding the installed `community.openwrt`
    collection.
- `check-structure`
  - Checks whether `galaxy.yml` and `tests/unit/plugins/` exist.
  - Exposes the result as the `has_collection` job output.
  - Does not imply that collection scaffolding should be added.
- `sanity` and `units`
  - Depend on `lint` and `check-structure`.
  - Run only when `has_collection == 'true'`.
  - Use `ansible-test` with `${{ env.ANSIBLE_PYTHON_VERSION }}`.
- `molecule`
  - Depends on `lint`, `sanity`, `units`.
  - Installs pinned roles and collections from `requirements.yml` into
    `~/.ansible/roles` and `~/.ansible/collections`, respectively.
  - Uses `if: ${{ !cancelled() && !failure() }}` so it still runs when
    `sanity`/`units` are skipped.
  - Matrix currently enables only `openwrt-25.12`, with
    `fail-fast: false`. OpenWrt 24.10 is temporarily disabled because
    its opkg networking fails in CI.
  - Passes `--platform-name "${{ matrix.platform }}"` to ensure each
    enabled matrix job tests its selected Molecule platform.
  - Selects scenarios via `MOLECULE_GLOB`.
  - Runs `molecule test --destroy=never` to preserve failed containers.
  - Prints container diagnostics on failure.
  - Destroys containers in an unconditional cleanup step.

When changing the workflow, update this section to reflect actual job
dependencies, conditions, matrix, and commands.

## Troubleshooting

- `No such container`, `mkdir` failing in `/tmp`, or
  `create: Successful` without a container: check for `--limit` first.
- `ip: RTNETLINK answers: Operation not permitted` in container logs
  is harmless (unprivileged container).
- ansible-lint warning `Unable to load module
  community.openwrt.{{ … }}` is expected for the dynamic package
  manager pattern. Do not hardcode the module to silence it.
- `argument --python: expected one argument`: the variable used in
  the workflow does not exist. Use `${{ env.ANSIBLE_PYTHON_VERSION }}`.
- `couldn't resolve module/action 'community.openwrt.uci'`: collections
  are not installed. Run `ansible-galaxy collection install
  community.openwrt`.

## Don'ts

- Do not modify anything under `./collections/`
- Do not use `yes`/`no` in YAML
- Do not hardcode package manager modules
- Do not use role variables without the role prefix
- Do not use `sleep infinity` in `molecule.yml` (BusyBox does not
  support it)
- Do not use `become: true` in Molecule tests – the container runs as
  root
- Never pass `--limit` (or `-- --limit …`) to `molecule test/create`.
  Molecule forwards it to the driver playbooks, which run on localhost.
  No host matches, the container is silently never created, and
  `create` still reports "Successful".
- Do not invent collection metadata paths (`galaxy.yml`, `meta/`,
  `plugins/`) – this project does not have them
- Do not suppress `yamllint` errors with `# noqa` (`# noqa` is
  ansible-lint syntax); use `# yamllint disable-line` only when a line
  cannot be wrapped

## Security and secrets

- Never commit real router addresses, credentials, or private keys.
- Use placeholders in examples (`192.0.2.1`, `example.invalid`).
- CI runs without secrets; do not add steps that require them.

## When in doubt

- `roles/router_hostname` is the minimal role example: a single task
  using `community.openwrt.uci`, with an overridable default in
  `defaults/main.yml`
- `converge.yml` shows how test values are passed via `vars:` to
  `include_role`
- Before pushing, run the fast local checks above (after installing
  collections)
- See "Adding a new role" for the idempotence requirement
- If workflow and this document disagree, the workflow wins – update
  this file
