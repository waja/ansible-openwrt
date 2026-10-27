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

## Official documentation

- [community.openwrt collection][openwrt-docs]
- [community.openwrt.setup module][setup-docs]
- [community.openwrt.uci module][uci-docs]

[linuxconfig]: https://github.com/lulkien/LinuxConfig/tree/master/router/openwrt/ansible
[homelab]: https://github.com/thiagoalmeidasa/homelab/tree/main/ansible/roles/openwrt_router
[bairhys]: https://github.com/bairhys/Ansible-Openwrt/tree/main
[klaster]: https://github.com/Lumpiasty/klaster/tree/fresh-start/ansible/roles/openwrt
[rut-config]: https://github.com/3ti-Energy/Rut-config/tree/main
[home-config]: https://github.com/Kblack0610/home-config/tree/master/ansible/roles/openwrt-iot-vlan

[openwrt-docs]: https://docs.ansible.com/ansible/latest/collections/community/openwrt/index.html
[setup-docs]: https://docs.ansible.com/ansible/latest/collections/community/openwrt/setup_module.html
[uci-docs]: https://docs.ansible.com/ansible/latest/collections/community/openwrt/uci_module.html
