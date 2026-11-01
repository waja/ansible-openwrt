# AGENTS.md

## Project context

Ansible project `waja.ansible_openwrt` for configuring OpenWrt routers.
Molecule tests run in Docker against the OpenWrt releases listed in
`.github/openwrt-versions.json`. CI runs on GitHub Actions.

Pull requests target `development`, not `master`. A dedicated workflow
warns on PRs that target `master` and adds the `needs-rebase` label.

## Directory structure (binding)

- `playbooks/site.yml` – standard configuration for all OpenWrt routers
- `playbooks/audit_packages.yml` – optional installed-package comparison
- `playbooks/storage.yml` – optional root storage inspection and expansion
- `docs/configuration.md` – router configuration overview, playbook usage,
  inventory organization, and links to role-specific guides
- `docs/roles/<role_name>.md` – detailed configuration guide for each
  role with documented user-facing options, including `router_librenms`
- `docs/state-discovery/` – discovery workflow, bundle format and schema,
  evidence handling, and Ansible assessment design
- `scripts/owrt-extra.sh` – read-only OpenWrt state discovery for Ansible
  migration
- `extensions/molecule/default/` – Molecule scenario for hostname,
  firewall zones, packages, and base services
- `extensions/molecule/network-static/` – isolated configuration-only
  tests for static IPv4 settings
- `extensions/molecule/network-dhcp/` – isolated configuration-only
  tests for DHCP client settings and IPv4 DHCP server status
- `roles/router_system/` – manages hostname, timezone, NTP, logging, ASU
  settings, and optional additional Dropbear listeners
- `roles/router_firewall/` – manages firewall default policies, declarative
  zones (including safe adoption and reference-safe removal), and opt-in WAN
  access for additional Dropbear ports
- `roles/router_packages/` – dynamically installs the default package list
- `roles/router_base/` – enables core services and removes obsolete config
- `roles/router_network/` – manages explicitly configured IPv4 interface
  addressing and DHCP server settings
- `roles/router_snmpd/` – optionally replaces the default SNMP community
  while retaining the package's read-only access mappings
- `roles/router_librenms/` – deploys pinned LibreNMS scripts and manages
  role-owned SNMP extend entries and sysupgrade persistence
- `roles/router_package_audit/` – optional comparison with a saved baseline
- `roles/router_storage/` – read-only root storage detection and opt-in expansion
- `roles/<role_name>/` – roles with `tasks/main.yml` and
  `defaults/main.yml`
- `./collections/` – installed dependencies, **never edit**, must be
  git-ignored
- `requirements.yml` – authoritative, version-pinned source for
  Ansible role and collection dependencies used locally and in CI.
- `.python-version` – shared Python version for CI workflows
- `.github/openwrt-versions.json` – shared OpenWrt release-version matrix
  for CI images
- `.github/actions/openwrt-image/action.yml` – shared image selection
  and pull step
- `requirements/ci/*.in` and `requirements/ci/*.txt` – direct Python
  dependency inputs and generated hash-locked CI toolchains
- `requirements/ci/pip-tools.in` – pinned lockfile generator version
- `scripts/update-ci-lockfiles.sh` – lockfile generation and validation
- `.github/workflows/update-ci-lockfiles.yml` – lockfile freshness validation
- `.github/workflows/refresh-ci-lockfiles.yml` – weekly lockfile refresh PR
- `.github/workflows/molecule.yml` – main Ansible/Molecule CI pipeline
- `.github/workflows/forward-compatibility.yml` – scheduled Ansible and
  ansible-lint pre-release tests
- `.github/workflows/script-tests.yml` – state-discovery script smoke tests
- `.github/workflows/pr-base-check.yml` – warns on PRs targeting `master`

The repository is **not** a full Ansible collection. There is no
`galaxy.yml`, `meta/`, or `plugins/` directory, and none must be
created unless explicitly requested. The CI `check-structure` job detects
these paths and, if present, enables additional collection-level tests.
Their absence is the normal state, not a defect.

## Documentation maintenance

Keep `README.md` in sync with the actual repository behavior and usage.
Keep `docs/configuration.md` as the concise entry point for applying the
playbooks, organizing inventory, and navigating role documentation. Put
detailed role-specific options, behavior, and examples in
`docs/roles/<role_name>.md` for roles that have meaningful user-facing
configuration. Do not create empty role guides merely to mirror every role
in the repository. The README should remain the project entry point and link
to the configuration overview and relevant role guides rather than
repeating their content. Whenever a change affects playbooks, roles,
variables/defaults, inventory configuration, dependencies, supported OpenWrt
versions, or user-facing commands, review the README, configuration overview,
and affected role guides. Add or revise examples when the supported way to
use the project changes. Do not document behavior that has not been
implemented or verified. If a change genuinely needs no documentation
update, no documentation-only edit is required.

Keep the relevant operational details in `AGENTS.md` synchronized too,
especially when changing development instructions, repository conventions,
or CI workflows.

### CI scope and path filters

- Prefer simple, conservative test selection over saving CI minutes. An
  additional test run is cheaper than maintaining fragile path-detection logic
  or accidentally skipping a required test.
- The Molecule workflow skips its matrix only when every changed file is
  Markdown. All other changes run Molecule; if the base commit or diff is
  unavailable, Molecule runs.
- Keep script-specific smoke tests in their dedicated workflow. Script
  changes also run Molecule; avoid adding exceptions just to save that run.
- Keep scheduled smoke tests and manual `workflow_dispatch` available.
- Do not add workflow-level path filters that can leave required checks
  pending.

Use `docs/reference-projects.md` as a curated set of external
Ansible/OpenWrt examples when researching relevant design questions,
implementation patterns, or test cases. Treat those repositories as
unverified examples, not project requirements: check official module
documentation and verify compatibility, safety, and behavior before adopting
an approach. Record lasting decisions in the relevant project documentation
or issue rather than relying on an external link alone.

## Issue and PR workflow

- Group related issues under a clearly scoped parent issue when the work
  consists of multiple coordinated implementation steps.
- Describe the purpose of each child issue and document the intended
  implementation order when dependencies exist.
- Keep independent work explicitly out of the dependency chain.
- Implement one child issue at a time unless there is a clear technical reason
  to combine changes. Keep each PR focused on its corresponding work item.
- Use GitHub's native sub-issue relationships when available; otherwise keep
  the parent issue's linked work-item list accurate.
- Create every new pull request targeting `development` as a **Draft**.
  Keep it in draft while implementation and self-review are in progress.
  Mark it ready for review only after the full diff has been reviewed, all
  checks required for that PR by the applicable workflows and repository
  policy have reached successful conclusions, and the PR is ready for
  reviewer feedback. For a specific PR, applicable checks are all checks
  required by repository policy or triggered by the GitHub Actions workflows
  for that PR, including jobs selected by path filters, conditions, and test
  matrices. Workflows or jobs that are not triggered because their documented
  conditions are not met are not required. Do not assume every workflow or
  test suite must run for every PR. If further implementation changes are
  needed, convert the PR back to draft until they are complete.
- Do not commit or push changes directly to `development` or `master`.
  All changes to either integration branch, including emergency fixes and
  automated maintenance changes, must be proposed and merged through a
  pull request. This applies to all contributors, including repository
  maintainers.
- These are the repository's required contribution rules. GitHub branch
  protection and ruleset settings are a separate enforcement mechanism;
  verify those settings independently and keep this document aligned
  with the repository's actual merge policy. Do not claim that a rule is
  technically enforced by GitHub unless that enforcement has been verified.

## Development workflow

Keep the PR branch history focused on reviewed, coherent changes. Do not
use commits on the PR branch as a scratchpad for intermediate experiments.

1. Prepare related edits in a local working tree or a separate scratch branch.
2. Review the complete diff before committing, including surrounding logic,
   defaults, tests, and documentation affected by the change.
3. Run the applicable local checks before committing when the required
   tooling is available. At minimum, run the fast local checks listed below
   for Ansible changes.
4. Commit only a coherent, reviewed unit of work. Use a message that explains
   the change's intent; avoid commits that merely reverse or repair a
   just-created, unreviewed commit.
5. Before pushing, inspect the final diff and commit list against the PR base.
   Do not push known-broken or exploratory intermediate states just to save
   progress.
6. Report which checks actually ran and their results. Clearly distinguish
   static inspection from executed tests. If a check cannot run locally, say
   why and rely on CI where appropriate; do not imply it passed.

If a mistake has already been pushed, fix and verify the complete change before
adding more commits. Consolidate noisy commits only when they are your own and
rewriting the branch is safe; never rewrite unrelated commits or shared work.
Prefer a clean follow-up commit over history rewriting when the branch has
other contributors or its history is already in use.

## Change scope and technical decisions

### Reference project research

For every new implementation PR, review `docs/reference-projects.md`
during the planning phase. The goal is to discover useful approaches,
missing requirements, operational risks, edge cases, and test cases before
the implementation direction is settled.

- Identify which listed projects are relevant to the problem or feature.
  Inspect their implementation when it can provide useful detail; do not
  browse unrelated projects merely to satisfy this rule.
- Apply this especially to new roles and features, extensions of existing
  behavior, new user-facing options, and architectural or design decisions.
- Look for relevant examples when dealing with OpenWrt-specific behavior,
  UCI ownership and transactions, release or hardware differences, package
  managers, idempotence, service reloads, disruptive changes, and recovery.
- Also consult the references when evaluating security-sensitive behavior,
  migrations or upgrades, monitoring and integrations, cross-role
  interactions, or test and CI design.
- For unclear bugs, use relevant projects to identify alternative approaches
  and possible causes, but verify findings against the actual failure and
  supported environment.
- Trivial corrections and documentation-only formatting changes normally
  do not need reference research. If no listed project is relevant, proceed
  without forcing a comparison.
- Treat external repositories as unverified examples, never as specifications
  or project requirements. Verify any adopted idea against official module
  documentation, supported OpenWrt versions, this repository's conventions,
  and tests.
- Record relevant findings and lasting design decisions in the issue or
  project documentation; do not rely on an external link alone.

Prefer the smallest focused change that solves the problem reliably and fits
the repository's existing conventions, runtime environment, and security
model. Avoid unrelated refactoring and unnecessary changes to permissions,
dependencies, infrastructure, or test setup.

Before introducing a significant deviation from the existing approach, first
check whether a simpler solution can work. If multiple viable options remain,
summarize their trade-offs and discuss them with the developer before
implementing the deviation. This is especially important for broader
refactors, additional privileges, new dependencies, or changes to the normal
runtime or CI environment.

A minimal diff is a preference, not an absolute goal: do not sacrifice
correctness, security, reliability, test coverage, or maintainability merely
to reduce the number of changed lines. Explain when a larger change is
necessary and why.

### Avoid duplicated moving values

When a value is expected to change, keep one authoritative source and derive
related configuration from it wherever practical. This is especially useful
for release versions, image tags, container names, paths, and CI matrix values.

- Do not repeat the same changeable value across workflow matrices, scenario
  files, scripts, diagnostics, and documentation when it can be derived.
- Prefer explicit variables or matrix values for a setting that drives several
  related values; keep generated names and paths consistent with that source.
- Before changing a version, image, or other moving target, search the
  repository for related references and update the affected consumers.
- Keep intentional pins and fixed test fixtures explicit. Centralization is
  not a reason to make stable values configurable or to add unnecessary
  abstraction for a value used only once.
- Treat mutable tags such as `latest` as deliberate moving targets. Where
  reproducibility matters, prefer an explicit version or digest and document
  why a moving tag is needed.

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
- Group related UCI writes by configuration package in one
  `community.openwrt.uci` task using `operations` and
  `autocommit: true`. This commits the package once after all operations
  succeed, rather than leaving staged changes or committing each option
  separately. The collection dependency must support `operations`.
- Keep service reloads/restarts in handlers notified by the successful UCI
  task; do not use a generic commit handler because handler execution order
  does not guarantee a commit before every service handler.
- If a configuration option is optional and cannot cleanly be included in
  the grouped operations, use a separate conditional UCI task with
  `autocommit: true`.
- Molecule tests for UCI-managed settings must verify both effective values
  and persistence in the configuration file, and ensure no staged UCI
  changes remain for the affected package.
- `ansible.builtin.raw` is allowed in `prepare.yml` because no Python
  environment is available on the target yet.
- Shared service-lock tasks live in
  `includes/router_service_restart_lock/` and are used by `router_system`,
  `router_base`, and `router_packages`. The system role holds the lock
  across its UCI transactions and flushes its runtime-apply handler before
  releasing it, preventing overlapping runs from mixing system-package
  changes. The lock coordinates operations on Python-free OpenWrt targets;
  do not copy this locking design into new features without a separate
  design review.
- Set `router_service_restart_lock_timeout` to override the shared lock
  timeout (default 1860 seconds). Legacy role-specific timeout variables
  remain accepted as fallbacks.
- A narrow additional exception is allowed when one remote operation must
  be followed immediately by a related state marker and no Ansible module
  can perform both actions together. In `router_base`, the service restart
  and its completion-marker write are run in one remote shell command.
  This reduces the risk that Ansible loses the task acknowledgement after
  the restart but before a separate marker task runs, which could cause an
  unnecessary restart on the next run. Do not use `raw` as a general
  replacement for available modules.

### Input validation

- Validate values when they have a defined set or range of allowed inputs and
  an invalid value could cause a confusing failure or unintended change.
- Prefer checks that fail early with a clear, actionable error message.
- Do not add validation merely for completeness. First check whether the
  responsible module or target system already validates the value reliably
  and reports invalid input clearly.
- Avoid duplicating checks that the module or target system already performs,
  unless an additional check materially improves safety or the error message.
- Pay particular attention to values where a typo could silently select a
  different behavior, especially for security-sensitive or disruptive changes.
- Keep validation proportional to the risk and complexity of the input.

### Role variables

- Must be prefixed with the role name:
  `router_system_hostname`, `router_packages_list`; `router_hostname_value`
  remains supported as a legacy hostname input
- Define defaults in `roles/<name>/defaults/main.yml` so the role runs
  without explicitly set variables
- Keep service-to-package relationships in
  `router_packages_service_package_map`; do not maintain a second required
  service-package list
- Do not use `vars:` in `tasks/main.yml` for values that should be
  overridable

### Package installation (OpenWrt-specific)

**Never** hardcode `community.openwrt.apk` or `community.openwrt.opkg`.
Always select dynamically via the fact set by
`community.openwrt.init`:

    - name: Install requested and required packages dynamically
      action: "community.openwrt.{{ openwrt_package_manager }}"
      args:
        name: "{{ router_packages_install_list | join(',') }}"
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
- `router_packages` owns package installation; base service configuration
  belongs in `router_base`. The package role derives service packages from
  `router_packages_managed_services` through `router_packages_service_package_map`;
  every managed service must have a mapping to one or more packages.
- `router_network` owns explicitly listed IPv4 interface addressing
  (`dhcp` or `static`) and optional per-interface DHCP server status via
  `router_network_interfaces.<interface>.dhcp.enabled`. Omitted `dhcp`
  settings and unlisted interfaces are left untouched.
  Mixed interface modes, DHCPv6, and IPv6 Router Advertisements are out
  of scope.
- `router_package_audit` is optional because it requires the saved
  baseline file `/etc/backup/installed_packages.txt`.

## Molecule / OpenWrt containers (current state)

- All scenarios use `driver: docker`, `command: /sbin/init`, and
  `pre_build_image: true`
- `tmpfs: /tmp:exec,mode=1777` – required so Ansible can write there
- The `default` scenario tests hostname, packages, and base services.
  The `network-static` and `network-dhcp` scenarios test UCI values and
  verify that `eth0`, the default route, and resolver configuration
  remain unchanged.
- The network scenarios intentionally do not add `NET_ADMIN` or reload
  networking/restart dnsmasq. They test configuration only;
  runtime DHCP and route behavior are out of scope.
- The network role's `router_network_apply_runtime_changes` variable
  defaults to `true`. Tests set it to `false` so handlers do not apply
  the committed configuration to the running container.
- Image tag: `openwrt/rootfs:x86_64-openwrt-${OPENWRT_VERSION}`
- Inventory variables for all hosts:
  - `ansible_connection: docker`
  - `ansible_remote_tmp: /tmp`
  - `openwrt_remote_tmp: /tmp`
- `prepare.yml` waits via `ansible.builtin.raw` for
  `/var/run/ubus/ubus.sock` and `ubus list`
- `community.openwrt.init` must run before all other roles in
  `converge.yml`
- Each scenario defines one platform using Molecule environment
  interpolation: `OPENWRT_VERSION` selects the image tag and
  `MOLECULE_SCENARIO_NAME` selects the instance name.
- `.github/openwrt-versions.json` is the single source of truth for the
  OpenWrt release-version matrix used by Molecule, forward-compatibility, and
  script smoke-test workflows. Each workflow expands the list into its own
  GitHub Actions matrix.
- Keep the file valid JSON. For example, to test two releases, set
  `"versions": ["24.10", "25.12"]`. Do not add comments to the JSON file.
- `.github/actions/openwrt-image/action.yml` centralizes release/snapshot tag
  selection, image pulling, and image ID/digest reporting. Forward-compatibility
  and script smoke tests explicitly select regular release images.
- To add or remove a tested release, edit the `versions` array in
  `.github/openwrt-versions.json`; do not duplicate version lists in workflows
  or Molecule scenario files.

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

## Adding a new OpenWrt version

1. Add or remove the release in the `versions` array in
   `.github/openwrt-versions.json`.
2. Verify that `community.openwrt.init` supports the version and sets
   `openwrt_package_manager` correctly.
3. Check the CI results for every Molecule scenario. The scenario files
   interpolate the image tag and container name from environment variables;
   do not add duplicate per-version platform entries.

## Important commands

### Fast local checks

Run these after installing collections (see below).

    yamllint .
    ansible-lint --exclude collections/ansible_collections/community/openwrt/
    ansible-playbook extensions/molecule/default/converge.yml --syntax-check

### Full test run (CI task, requires Docker)

    # run the test, keep containers on failure
    export OPENWRT_VERSION="$(jq -r '.versions[0]' \
      .github/openwrt-versions.json)"
    export OPENWRT_IMAGE="openwrt/rootfs:x86_64-openwrt-${OPENWRT_VERSION}"
    molecule test --destroy=never
    # inspect a failed container (scenario name shown by molecule list)
    molecule login --host "openwrt-${OPENWRT_VERSION}-default"
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
      --collections-path ~/.ansible/collections

Without `--force`, `ansible-galaxy collection install` checks the
configured collection paths and skips a requested collection when an
installed version satisfies the pinned requirement. It installs a missing
or unsatisfied version into the first configured path. This matters for
Docker images that already include a pinned collection: forcing installation
can download and overwrite that collection unnecessarily. Do not use
`--force` for routine dependency installation; reserve it for an
intentional reinstall or overwrite. The pin in `requirements.yml` expresses
the version this project requires; it does not mean that every environment
must download that version again when it is already available and satisfies
the requirement. Verify the actual version and search paths with
`ansible-galaxy collection list` when behavior is unclear.
The Renovate configuration extends `config:recommended`, which enables
the Ansible Galaxy manager to propose updates for role and collection
entries in `requirements.yml`.

## CI pipeline (`.github/workflows/molecule.yml`)

The workflow file is the source of truth. Keep this section synchronized
with it.

- Python version: read from `.python-version` by `actions/setup-python`.
- Python dependencies are split into lint, Ansible sanity/unit tests,
  and Molecule toolchains. `requirements/ci/ansible-core.in` defines the
  shared Ansible Core version; each group lock includes that input.
- `requirements/ci/pip-tools.in` is the single source for the lockfile
  generator version. Both lock workflows install from it, and the update
  script validates the installed version against it.
- Generate or refresh locks with `bash scripts/update-ci-lockfiles.sh`.
  CI regenerates them and fails if committed lockfiles are stale.
  A separate weekly workflow opens or updates a PR only when locks change.
- Triggers: `workflow_dispatch`, weekly schedules (Sunday at 06:17 and
  07:17 UTC), pull requests, and pushes to `development` and `master`.
  The workflow starts for all push and pull-request events so required checks
  are not left pending by workflow-level path filters. The change-detection
  job skips the Molecule matrix only when every changed file is Markdown.
  Every other change runs Molecule. If the base commit is unavailable or Git
  cannot produce the diff, Molecule runs. Scheduled and manual runs always
  run the Molecule matrix.

### Jobs

- `lint`
  - Installs the hash-locked lint toolchain from
    `requirements/ci/lint.txt` with `--require-hashes` and checks it
    with `python -m pip check`.
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
  - Install the hash-locked Ansible test toolchain from
    `requirements/ci/ansible-test.txt`.
  - Run only when `has_collection == 'true'`.
  - Use `ansible-test` with `${{ steps.python.outputs.python-version }}`.
- `molecule`
  - Depends on `changes`, `check-structure`, `lint`, `sanity`, and
    `units`. It runs only after structure and lint prerequisites pass.
  - Installs pinned roles and collections from `requirements.yml` into
    `~/.ansible/roles` and `~/.ansible/collections`, respectively.
  - Runs for scheduled/manual events and whenever any changed file is not
    Markdown. It skips the matrix only for Markdown-only changes. If the
    base commit is unavailable or Git cannot produce the diff, it runs.
  - Installs the hash-locked Molecule toolchain from
    `requirements/ci/molecule.txt` with `--require-hashes`.
  - Sets `MOLECULE_GLOB` to discover scenarios under
    `extensions/molecule/`.
  - Matrix lists scenarios `default`, `network-static`, and `network-dhcp`,
    with `fail-fast: false`. Each scenario runs in a separate job.
  - Expands `versions` from `.github/openwrt-versions.json` into the
    OpenWrt-version matrix, combined with the scenario matrix.
  - Uses `.github/actions/openwrt-image` to select, pull, and identify the
    regular or snapshot image for each matrix entry.
  - Sets `OPENWRT_SNAPSHOT` by comparing `github.event.schedule` with the
    snapshot cron (`17 7 * * 0`). The existing `17 6 * * 0` schedule keeps
    testing the regular release image.
  - The shared image action exports `OPENWRT_VERSION` and `OPENWRT_IMAGE`
    for all subsequent Molecule commands, including cleanup, and logs the
    pulled image ID and repository digests.
  - Runs `molecule test -s "${{ matrix.scenario }}" --destroy=never`
    to preserve a failed scenario's container for diagnostics.
  - Logs the tested container's image ID and prints detailed diagnostics
    on failure: Docker configuration, network interfaces/routes/DNS,
    OpenWrt release and opkg version, network/firewall init links,
    firewall rules, recent system log, filesystem space, and container
    logs. Container names derive from `OPENWRT_VERSION` and scenario.
  - The `17 6 * * 0` schedule tests the regular moving OpenWrt release image;
    the separate `17 7 * * 0` schedule tests the moving snapshot tag.
    Pull requests, pushes, and manual runs use the regular image.
  - Destroys only the scenario assigned to that job in an unconditional
    cleanup step.
- `molecule-status`
  - Exposes the stable `Molecule` check. Configure branch protection to
    require this aggregate check, not the individual matrix jobs.
  - Succeeds for intentional matrix skips and fails when a prerequisite or
    any executed matrix job fails.

When changing the workflow, update this section to reflect actual job
dependencies, conditions, matrix, and commands.

### Forward compatibility pre-release tests

Workflow: `.github/workflows/forward-compatibility.yml`.

- Runs on its weekly Sunday schedule (08:17 UTC), manual dispatch, and
  pull requests that change the workflow, shared OpenWrt version matrix, or
  pre-release discovery script. It does not run on pushes.
- Does not use or modify the hash-locked CI requirement inputs or lockfiles.
  It discovers published, non-yanked PEP 440 pre-release/development versions
  from the PyPI JSON API and reports an explicit notice when none exist.
- The Ansible Core lane installs the selected pre-release with the current
  Molecule Docker toolchain and runs all three existing scenarios:
  `default`, `network-static`, and `network-dhcp`.
- The Ansible Core lane expands the same OpenWrt-version matrix and uses the
  shared image action with `snapshot: 'false'`; it never selects the snapshot
  image.
- A separate lane tests the newest published ansible-lint pre-release.
  pip resolves its Ansible Core dependency constraints and `pip check`
  validates the resulting environment. A dependency conflict fails the lane.
- If a tool has no published pre-release, its test is explicitly skipped;
  a latest-stable installation is never reported as a forward-compatibility
  test. Each executed lane reports the installed tool versions.
- Keep this workflow independent of the weekly snapshot schedule in
  `.github/workflows/molecule.yml`, which continues to use the pinned
  stable Ansible baseline.

### State discovery script tests (`.github/workflows/script-tests.yml`)

- The workflow starts for all pull requests and pushes to
  `development`/`master`. A local full-history Git diff gates the test job
  to changes under `scripts/**`, the shared OpenWrt version matrix, the
  image action, or this workflow file. It also supports manual dispatch.
- Runs shell syntax and command-line smoke tests for
  `scripts/owrt-extra.sh` in every configured regular release image, using
  the shared OpenWrt-version matrix and image action.
- The local diff avoids GitHub's changed-file API limit; if the base commit
  is unavailable, tests run by default.
- Does not depend on the Molecule matrix, so script-only changes avoid
  Ansible/Molecule integration tests.

### Script and documentation lint (`.github/workflows/lint-scripts-docs.yml`)

- Starts for pull requests, pushes to `development`/`master`, and manual
  dispatch. Local full-history Git diffing gates the relevant jobs; workflow
  and lint-configuration changes run the applicable checks. If the base
  commit is unavailable or diffing fails, all checks run.
- Shell changes under `scripts/**` are checked with ShellCheck in POSIX
  shell mode. Changes to `.shellcheckrc` also trigger ShellCheck. The existing
  OpenWrt release smoke tests remain separate in
  `.github/workflows/script-tests.yml`.
- Markdown files are checked with `markdownlint-cli2` and `codespell`.
  Markdown line length is not enforced because long URLs, tables, and code
  examples are common in this repository. HTML in Markdown and documents
  without a first-line H1 are permitted.
- Spelling checks catch likely misspellings; they are not a grammar or
  language-quality assessment. Keep documentation in English and review
  wording as part of normal code review.

### Docker Ansible CI (`.github/workflows/docker-ansible.yml`)

- Triggers on pull requests, pushes to `development`/`master`,
  manual dispatch, and a weekly Sunday smoke test at 04:17 UTC. Scheduled
  runs execute only when this workflow is on the repository's default
  branch. No path filter is used, so the workflow always reports a status
  on pull requests.
- Pulls `willhallonline/ansible:latest` explicitly before testing, so the
  smoke test checks the current mutable tag rather than a cached local
  image. Logs and the GitHub Actions step summary record the image ID and
  repository digest(s) used for the run.
- Uses `willhallonline/ansible:latest` to verify that the image's
  preinstalled collections are reused when their versions satisfy
  `requirements.yml`. This is a separate image check; the README's usage
  examples use the same image.
- Lists `community.docker` before installation, installs pinned roles
  and collections from `requirements.yml` using Ansible's default paths,
  then lists the collection again. Collection installation uses verbose
  output so CI logs show whether an installed version was reused or a
  collection was installed.
- Uses the same mounted Ansible home in a separate container to verify
  that dependencies remain available across container runs.
- Syntax-checks the site, package-audit, and storage playbooks with a
  temporary local inventory; it does not connect to routers and requires
  no secrets.
- This workflow checks the Will Hall Online image's dependency behavior
  and playbook syntax. It does not replace the lint and Molecule checks in
  `.github/workflows/molecule.yml`.

## Troubleshooting

- `No such container`, `mkdir` failing in `/tmp`, or
  `create: Successful` without a container: check for `--limit` first.
- `ip: RTNETLINK answers: Operation not permitted` can occur in an
  unprivileged container. In the network scenarios, do not dismiss it
  automatically: check whether it explains a failed network reload.
- ansible-lint warning `Unable to load module
  community.openwrt.{{ … }}` is expected for the dynamic package
  manager pattern. Do not hardcode the module to silence it.
- `argument --python: expected one argument`: the variable used in
  the workflow does not exist. Use `${{ steps.python.outputs.python-version }}`.
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

- `roles/router_system` manages OpenWrt system settings with
  `community.openwrt.uci` and overridable role defaults, including ASU client
  options and optional additional Dropbear listeners. Additional ports
  default to empty and use the router's existing system accounts and SSH
  authorized keys. `router_firewall` opens those ports on WAN only when
  `router_firewall_dropbear_wan_zone` is set; it defaults to empty. The ASU
  package must be installed separately; the remote syslog address
  (`router_system_log_ip`) intentionally has no default.
- `roles/router_network` demonstrates explicit UCI configuration through
  `router_network_interfaces`, including optional nested DHCP settings
- `converge.yml` shows how test values are passed via `vars:` to
  `include_role`
- Before pushing, run the fast local checks above (after installing
  collections)
- See "Adding a new role" for the idempotence requirement
- If workflow and this document disagree, the workflow wins – update
  this file
