# Network role

The `router_network` role configures IPv4 addressing on explicitly
listed OpenWrt network interface sections. It can also enable or disable
the IPv4 DHCP server for each listed interface. Unlisted interfaces are
left untouched.

**Caution:** Interface changes can interrupt connectivity. Make sure you
have a recovery path before applying changes to a remote router.

## Run the role

The standard playbook runs this role in a separate play before OpenWrt
initialization and the other configuration roles:

```bash
ansible-playbook -i inventory.ini playbooks/site.yml \
  --limit router1 --tags router_network
```

## Interface addressing

| Variable | Default | Purpose |
| --- | --- | --- |
| `router_network_interface_mode` | `dhcp` | Addressing mode for every listed interface: `dhcp` or `static` |
| `router_network_interfaces` | `{}` | Mapping of existing interface section names to settings |

The default empty mapping makes no interface changes. Only list interfaces
that this role should manage. One addressing mode applies to every
interface in the mapping; mixed DHCP/static interface modes are not
supported. IPv6 configuration is outside this role's scope.

### Obtain address, route, and DNS through DHCP

For example, configure the `wan` interface as a DHCP client:

```yaml
---
router_network_interface_mode: dhcp
router_network_interfaces:
  wan: {}
```

In DHCP mode, the role sets `proto=dhcp`, enables peer-provided DNS,
and removes static address, netmask, gateway, and DNS options for each
listed interface. The DHCP server must provide a default route and DNS
information for those to become available.

### Configure a static interface

Each listed interface needs an IPv4 address and netmask. Gateway and DNS
are optional:

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

Static mode disables peer-provided DNS and configures the supplied
gateway and DNS servers. Omit `gateway` to remove a configured gateway,
and omit `dns` to remove configured DNS servers. Addresses are validated
as IPv4 values, and the netmask must be contiguous.

Interface changes are committed through one UCI transaction and notify
the network reload handler.

## Configure the IPv4 DHCP server

DHCP server status is an optional `dhcp` subkey of each interface in
`router_network_interfaces`. This is independent of whether the router's
own interface acts as a DHCP client.

For example, enable IPv4 DHCP on LAN and disable it on the guest network:

```yaml
---
router_network_interface_mode: static
router_network_interfaces:
  lan:
    ipaddr: 192.0.2.1
    netmask: 255.255.255.0
    dhcp:
      enabled: true
  guest:
    ipaddr: 192.0.20.1
    netmask: 255.255.255.0
    dhcp:
      enabled: false
```

The role sets `dhcp.<interface>.ignore=0` when `enabled: true` and
`ignore=1` when `enabled: false`. Omit the `dhcp` subkey to leave
that interface's DHCP section and all its settings untouched. Interfaces
omitted from `router_network_interfaces` are also left untouched.

This controls IPv4 DHCP only; it does not configure DHCPv6 or IPv6 Router
Advertisements. Configure those separately if needed.

## Runtime changes and dnsmasq

| Variable | Default | Purpose |
| --- | --- | --- |
| `router_network_apply_runtime_changes` | `true` | Run network reload and dnsmasq restart handlers |
| `router_network_force_dnsmasq_restart` | `false` | Request a dnsmasq restart even without a DHCP configuration change |

DHCP changes restart dnsmasq only when the UCI configuration changes.
Set `router_network_force_dnsmasq_restart: true` to force a restart,
for example to retry a previously failed restart.

For controlled configuration-only runs, set
`router_network_apply_runtime_changes: false`. The role still commits
UCI settings, but skips the network reload and dnsmasq restart handlers.
This is intended for tests or carefully planned maintenance, not normal
router configuration; runtime settings remain unapplied until the
relevant services are reloaded.

## Example: complete interface and DHCP configuration

```yaml
---
router_network_interface_mode: static
router_network_interfaces:
  lan:
    ipaddr: 192.0.2.1
    netmask: 255.255.255.0
    dhcp:
      enabled: true
  wan:
    ipaddr: 192.0.2.2
    netmask: 255.255.255.252
    gateway: 192.0.2.1
    dns:
      - 192.0.2.53
```

The example is illustrative only; choose addresses, routes, and DHCP
settings that match the actual network topology.
