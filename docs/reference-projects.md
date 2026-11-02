# Reference projects using Ansible with OpenWrt

This page records external projects that can provide practical examples when
designing or troubleshooting this repository. They are starting points for
investigation, not authoritative documentation or requirements for our design.

Check the relevant project when working on a related feature. Verify any
proposed approach against the official `community.openwrt` documentation,
our supported OpenWrt versions, current module behavior, and this repository's
tests before adopting it. Do not copy code or hardware-specific workarounds
without understanding their assumptions.

## Projects

### [lulkien/LinuxConfig][linuxconfig]

- **Ansible path:** `router/openwrt/ansible/`

- **Focus:** Xiaomi CR660x access-point configuration, VLANs and wireless.
- **Useful entry points:** `README.md`, `bootstrap.yml`,
  `setup-wireless.yml`, and `backup.yml`.
- **Ideas to examine:** separate bootstrap and follow-up configuration,
  explicit ordering for disruptive changes, and a dedicated configuration
  backup playbook.
- **Caution:** the documented bootstrap changes firewall and network behavior
  and reboots the device. Treat it as a device-specific example, not a
  generally safe sequence.

### [thiagoalmeidasa/homelab][homelab]

- **Ansible path:** `ansible/roles/openwrt_router/`

- **Focus:** reusable router role for packages, DHCP reservations and DNS.
- **Useful entry point:** `tasks/main.yml`, which imports smaller task files
  and conditionally applies optional configuration.
- **Ideas to examine:** how a role separates feature areas and handles
  optional variable-driven configuration.

### [bairhys/Ansible-Openwrt][bairhys]

- **Focus:** broader router provisioning, including Wi-Fi, WireGuard,
  Tailscale, dynamic DNS and monitoring.
- **Useful entry point:** `README.md`, which documents supported features,
  dependencies and operator setup.
- **Ideas to examine:** feature coverage, prerequisites, inventory examples,
  and documentation of steps that still require manual platform approval.

### [Lumpiasty/klaster][klaster]

- **Ansible path:** `ansible/roles/openwrt/` on branch `fresh-start`

- **Focus:** a modular OpenWrt role covering system settings, packages,
  network, WWAN, BGP, firewall and wireless.
- **Useful entry point:** `tasks/main.yml`, which imports feature-specific
  task files and documents an explicit package dependency.
- **Ideas to examine:** task decomposition and how dependencies determine
  execution order.

### [3ti-Energy/Rut-config][rut-config]

- **Focus:** Ansible-managed configuration for its target router environment.
- **Useful entry point:** `site.yaml`.
- **Ideas to examine:** `community.openwrt.setup` fact gathering, reviewing
  staged UCI changes with `community.openwrt.uci`, and asking for explicit
  approval before committing changes.
- **Caution:** the repository includes vendor/environment-specific API and
  configuration details. Verify that any technique applies to our target
  devices and supported collection version.

### [Kblack0610/home-config][home-config]

- **Ansible path:** `ansible/roles/openwrt-iot-vlan/`

- **Focus:** IoT network isolation with network, DHCP, wireless and firewall
  configuration.
- **Useful entry point:** the role's `README.md`, which describes its
  phased rollout, verification steps, rollback paths and division of
  responsibility between configuration tools.
- **Ideas to examine:** staged rollout of risky changes, explicit recovery
  planning, and avoiding multiple tools managing the same UCI objects.
- **Caution:** its bridge/VLAN design and stated hardware limitations are
  specific to the author's device and OpenWrt environment.

### [DigitecGalaxus/ansible-openwrt-framework][digitec-openwrt]

- **Focus:** an Ansible framework for managing OpenWrt gateways as a fleet,
  using Tailscale clients and a Headscale control plane for its mesh.
- **Useful entry points:** [network template][digitec-network],
  [firewall template][digitec-firewall],
  [Tailscale settings template][digitec-tailscale], and the
  [configuration tasks][digitec-config-tasks].
- **Ideas to examine:** the unmanaged `tailscale0` interface, a dedicated
  firewall zone, explicit inter-zone forwarding, and declarative route
  advertisement derived from network definitions.
- **Caution:** its templates render and import complete UCI package files,
  rather than managing isolated sections. Its firewall grants broad access
  within the Tailscale zone, forwards Tailscale traffic to WAN, and adds a
  project-specific SNAT rule. Its route calculation assumes particular
  network data. A `uci-defaults` script also patches the package init script
  with a public-IP ping delay. These are framework-specific choices, not
  safe defaults or drop-in patterns for this repository.

### [GuNanOvO/openwrt-tailscale][gunanovo-tailscale]

- **Focus:** builds smaller Tailscale IPK/APK packages and provides install,
  update, and package-feed workflows for OpenWrt devices.
- **Useful entry points:** [available packages by architecture][gunanovo-packages],
  [APK feed setup][gunanovo-apk], [installer modes and behavior][gunanovo-installer],
  and [post-install configuration][gunanovo-postinstall].
- **Ideas to examine:** architecture-specific packaging, persistent versus
  temporary/binary installation, storage and memory constraints, and how
  package installation integrates with the OpenWrt init service.
- **Caution:** this is a third-party package and installer project, not an
  Ansible configuration role. Its OpenWrt 25.12 APK feed requires adding a
  third-party signing key and repository. Do not make that feed a dependency
  when the official OpenWrt package meets our requirements. Its own project
  notes state that most devices/architectures are untested, so a listed
  package is not evidence of tested hardware compatibility.

### [fl0w1nd/openwrt-tailscale][flowind-tailscale]

- **Focus:** a script-based Tailscale manager aimed at devices constrained by
  flash storage or official package availability.
- **Useful entry points:** [subnet-routing guide][flowind-subnet],
  [storage modes][flowind-storage], and the
  [project README][flowind-readme].
- **Ideas to examine:** separating the unmanaged interface from optional
  firewall integration, persistent binaries on external storage, RAM mode,
  and the distinction between kernel-TUN and userspace operation.
- **Caution:** its subnet-routing helper creates OpenWrt UCI objects and its
  example firewall policy uses permissive zone policies. Its compressed
  binaries, installer, cron updater, and optional LuCI integration are a
  separate distribution/management model, not a pattern to import into this
  Ansible role. In userspace mode there is no `tailscale0` interface to
  configure.

## How to use these references

- Use them to discover options, edge cases, implementation patterns and
  potential test cases for a concrete task.
- Prefer official collection documentation for module contracts and supported
  parameters; use external repositories as examples of real-world usage.
- Verify idempotence, check mode, error handling, security implications and
  behavior on the OpenWrt releases tested by this repository.
- Record a design decision in the relevant project documentation or issue
  when a reference leads to an adopted approach. A link alone is not evidence
  that an approach is correct or supported.
- Revisit links when needed; external repositories, branches and file paths
  can change.

## Runtime state discovery assessment

The following references were reviewed specifically for issue
[#53](https://github.com/waja/ansible-openwrt/issues/53). None provides a
drop-in runtime snapshot collector; each informs a different boundary of
the design:

- **[LinuxConfig][linuxconfig] — persistent backup, not runtime state.**
  Its `sysupgrade --create-backup` workflow is a useful pattern for a
  separate configuration export: create an archive, retrieve it with
  Ansible, and clean up the temporary file. It does not capture the
  currently active kernel or network state and is therefore outside #53.
- **[3ti-Energy/Rut-config][rut-config] — configuration and runtime are
  distinct views.** Its use of `community.openwrt.setup` and review of
  staged UCI changes before an explicit commit reinforces that collected
  facts, pending configuration changes, and the active kernel state must
  not be conflated. The collector remains evidence-only and does not
  stage or commit UCI changes.
- **[Kblack0610/home-config][home-config] — validation and recovery.**
  Its phased rollout, verification and rollback guidance is a useful
  model for the later real-system validation procedure. It does not
  justify changing live state during collection.
- **[bairhys/Ansible-Openwrt][bairhys] — monitoring, not discovery.**
  Its exporter and monitoring integrations may inform future monitoring
  roles, but continuous metrics collection is not the goal of this
  point-in-time migration aid.
- **[thiagoalmeidasa/homelab][homelab] and [Lumpiasty/klaster][klaster]**
  demonstrate modular configuration task organization. That is useful
  for Ansible roles but does not change the collector's runtime data
  sources or behavior.
- The Tailscale-focused references and
  [DigitecGalaxus framework][digitec-openwrt] address VPN/UCI
  configuration rather than general runtime-state discovery; no
  implementation pattern was adopted from them for #53.

### Resulting design decisions

- Keep runtime snapshots separate from UCI, overlay files, package
  inventories and persistent configuration backups.
- Capture complementary views rather than treating one source as
  authoritative: fw4-generated rules versus the effective nftables
  ruleset; netifd's logical interface status versus kernel state from
  `ip`.
- Keep collection optional and read-only. Missing utilities are reported,
  never installed automatically.
- Treat every snapshot as sensitive, point-in-time evidence. Do not infer
  origin, intent, persistence or safe desired state from it, and never
  replay it into Ansible configuration automatically.
- Defer broad process and unrestricted sysctl inventories; reconsider a
  narrowly scoped sysctl allowlist only when a concrete migration use
  case exists.
- Use the validation and rollback discipline exemplified by home-config
  when testing on a booted OpenWrt system. The collector itself must not
  perform rollback or mutate router state.

These decisions preserve the scope of #53. They do not require another
runtime data source or a broader system inventory. The collector was
subsequently validated on a booted OpenWrt 25.12.5 x86/64 VM: all seven
snapshots succeeded, restrictive permissions and overwrite protection were
verified, and the full discovery run cleaned up its temporary mounts and lock.
See [PR #149](https://github.com/waja/ansible-openwrt/pull/149) for the
validation record.

## Official documentation

- [OpenWrt Tailscale guide][openwrt-tailscale]
- [Tailscale subnet routers][tailscale-subnet]
- [community.openwrt collection][openwrt-docs]
- [community.openwrt.setup module][setup-docs]
- [community.openwrt.uci module][uci-docs]

[linuxconfig]: https://github.com/lulkien/LinuxConfig/tree/master/router/openwrt/ansible
[homelab]: https://github.com/thiagoalmeidasa/homelab/tree/main/ansible/roles/openwrt_router
[bairhys]: https://github.com/bairhys/Ansible-Openwrt/tree/main
[klaster]: https://github.com/Lumpiasty/klaster/tree/fresh-start/ansible/roles/openwrt
[rut-config]: https://github.com/3ti-Energy/Rut-config/tree/main
[home-config]: https://github.com/Kblack0610/home-config/tree/master/ansible/roles/openwrt-iot-vlan

[digitec-openwrt]: https://github.com/DigitecGalaxus/ansible-openwrt-framework
[gunanovo-tailscale]: https://github.com/GuNanOvO/openwrt-tailscale
[flowind-tailscale]: https://github.com/fl0w1nd/openwrt-tailscale
[digitec-network]: https://github.com/DigitecGalaxus/ansible-openwrt-framework/blob/master/roles/openwrt/config/templates/network_config.j2
[digitec-firewall]: https://github.com/DigitecGalaxus/ansible-openwrt-framework/blob/master/roles/openwrt/config/templates/firewall_config.j2
[digitec-tailscale]: https://github.com/DigitecGalaxus/ansible-openwrt-framework/blob/master/roles/openwrt/config/templates/tailscale_config.j2
[digitec-config-tasks]: https://github.com/DigitecGalaxus/ansible-openwrt-framework/blob/master/roles/openwrt/config/tasks/main.yaml
[gunanovo-packages]: https://github.com/GuNanOvO/openwrt-tailscale/blob/main/docs/en/packages.md
[gunanovo-apk]: https://github.com/GuNanOvO/openwrt-tailscale/blob/main/docs/en/guide/apk-setup.md
[gunanovo-installer]: https://github.com/GuNanOvO/openwrt-tailscale/blob/main/docs/en/guide/install-script.md
[gunanovo-postinstall]: https://github.com/GuNanOvO/openwrt-tailscale/blob/main/docs/en/guide/post-install.md
[flowind-subnet]: https://github.com/fl0w1nd/openwrt-tailscale/blob/main/docs/en/guide/subnet-routing.md
[flowind-storage]: https://github.com/fl0w1nd/openwrt-tailscale/blob/main/docs/en/guide/storage-modes.md
[flowind-readme]: https://github.com/fl0w1nd/openwrt-tailscale/blob/main/README.md
[openwrt-tailscale]: https://openwrt.org/docs/guide-user/services/vpn/tailscale/start
[tailscale-subnet]: https://tailscale.com/kb/1019/subnets
[openwrt-docs]: https://docs.ansible.com/ansible/latest/collections/community/openwrt/index.html
[setup-docs]: https://docs.ansible.com/ansible/latest/collections/community/openwrt/setup_module.html
[uci-docs]: https://docs.ansible.com/ansible/latest/collections/community/openwrt/uci_module.html
