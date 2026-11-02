# Firewall role

The `router_firewall` role manages the firewall default policies,
explicitly declared firewall zones and filter rules, and an optional WAN
rule for additional Dropbear SSH listeners. Redirects and inter-zone
forwardings are not currently managed.

## Requirements and execution

The role uses `community.openwrt.uci` and expects OpenWrt initialization
to have run first. The standard `playbooks/site.yml` playbook handles
initialization and applies this role with the `router_firewall` tag.

```bash
ansible-playbook -i inventory.ini playbooks/site.yml \
  --limit router1 --tags router_firewall
```

Firewall changes over SSH can interrupt the management session. Ensure
that you have an independent recovery path before changing zones or
policies on a remote router. The role does not implement an automatic
timed rollback.

## Default policies

The role manages the input, forward, and output policies in the first
firewall defaults section. `router_firewall_zones` and `router_firewall_rules` default to empty
mappings (`{}`), so no additional zones or filter rules are managed unless
you declare them.

| Variable | Default | Accepted values |
| --- | --- | --- |
| `router_firewall_input` | `REJECT` | `ACCEPT`, `REJECT`, `DROP` |
| `router_firewall_forward` | `REJECT` | `ACCEPT`, `REJECT`, `DROP` |
| `router_firewall_output` | `ACCEPT` | `ACCEPT`, `REJECT`, `DROP` |

For an access point that should pass traffic without filtering at the
firewall-defaults level, set all three policies in its host variables:

```yaml
---
router_firewall_input: ACCEPT
router_firewall_forward: ACCEPT
router_firewall_output: ACCEPT
```

Use these settings only where appropriate for the network design.
`input: ACCEPT` allows traffic to services on the router, while
`forward: ACCEPT` removes the default forwarding restriction.

## Declarative firewall rules

Declare filter rules as a mapping keyed by the desired UCI section ID:

```yaml
router_firewall_rules:
  allow_ssh_from_admin:
    name: Allow SSH from admin network
    src: wan
    src_ip: 192.0.2.10
    dest_port: "22"
    proto:
      - tcp
    target: ACCEPT
```

The mapping key is the stable UCI section ID and may contain only letters,
digits, and underscores. The optional `name` is the human-readable rule label and defaults
to the mapping key for newly created named sections. Anonymous UCI rules
are adopted only when `name` is explicitly supplied; the mapping key is
not an implicit adoption identity. Adoption is refused if more than one
candidate exists. An existing named section with the requested ID takes
precedence.

Use `state: absent` to remove a rule. Use `enabled: false` to disable it
without removing its section. Omitted options remain unchanged and explicit
`null` removes an option. Empty lists are rejected; use `null` to remove
list-valued options.

Supported options include `src`, `dest`, `src_ip`, `src_ip6`,
`src_mac`, `src_port`, `dest_ip`, `dest_ip6`, `dest_port`,
`proto`, `family`, `target`, `icmp_type`, `limit`,
`limit_burst`, `enabled`, `log`, `log_limit`, `ipset`,
`mark`, `set_mark`, `set_xmark`, and `extra`. Protocols and ICMP
types accept non-empty YAML lists; other options use their documented
scalar form. Zone references must resolve to an existing zone or one
declared as present in the same role invocation.

New rules are appended in declaration order. Existing rules are not
automatically reordered. The role validates the complete rule input and
identities before applying UCI operations, and shares the existing single
firewall commit and reload lifecycle.

## Declarative zones

Declare zones as a mapping keyed by the desired UCI section ID:

```yaml
---
router_firewall_zones:
  guest:
    network:
      - guest
    input: REJECT
    output: ACCEPT
    forward: REJECT
    masq: false
    mtu_fix: true
```

The dictionary key is the stable UCI section ID and may contain only
letters, digits, and underscores. The optional `name` option defaults to
that key. Zone names must be at most 11 characters and start with a
letter or underscore.

### Currently supported zone options

| Option | YAML type | Behavior |
| --- | --- | --- |
| `name` | string | Zone name; defaults to the mapping key |
| `enabled` | boolean | Disable the zone without removing its section |
| `network` | non-empty list of strings | Networks assigned to the zone |
| `device` | non-empty list of strings | Device names or fw4 device patterns |
| `subnet` | non-empty list of strings | Classify traffic by IP network |
| `input` | string | Input policy: `ACCEPT`, `REJECT`, or `DROP` |
| `output` | string | Output policy: `ACCEPT`, `REJECT`, or `DROP` |
| `forward` | string | Forward policy: `ACCEPT`, `REJECT`, or `DROP` |
| `masq` | boolean | Enable IPv4 masquerading |
| `masq6` | boolean | Enable IPv6 masquerading |
| `masq_src` | non-empty list of strings | Source networks for masquerading |
| `masq_dest` | non-empty list of strings | Destination networks for NAT |
| `masq_allow_invalid` | boolean | Allow invalid conntrack states with NAT |
| `mtu_fix` | boolean | Enable MSS clamping |
| `family` | string | `ipv4`, `ipv6`, or `any` |
| `log` | integer | Values 0–3; bit 0 verdicts, bit 1 MSS-fix logging |
| `log_limit` | string | Rate limit, e.g. `10/minute` |
| `auto_helper` | boolean | Automatically assign conntrack helpers |
| `helper` | non-empty list of strings | Explicit conntrack helper names |
| `counter` | boolean | Include counters on zone verdict rules |
| `state` | string | `present` (default) or `absent` |

The option types follow the zone parser shipped with OpenWrt 25.12's
firewall4 package at this [pinned revision](
https://github.com/openwrt/firewall4/commit/b6e5157).

Only the options in this table are accepted. The role validates the
complete declared zone input before applying UCI changes. A present zone
updates only the options supplied in its definition; omitted options are
left unchanged. Set an option to `null` to remove it, including list-valued
options. Empty lists are rejected because UCI cannot represent a distinct
empty-list value. `state: absent` removes the complete zone.

A named section with the requested UCI section ID is updated in place; a
missing section is created. If the ID already belongs to a non-zone
section, the role fails before writing changes.

### Configuration examples

The examples below are inventory variables for the `router_firewall` role.
They are independent examples; combine them only when the resulting
network and firewall design is appropriate for your router.

#### 1. Assign a guest network to a restricted zone

Assume that a logical network interface named `guest` is already
configured by the network role. This declares its firewall zone:

```yaml
router_firewall_zones:
  guest:
    name: guest
    network:
      - guest
    input: REJECT
    output: ACCEPT
    forward: REJECT
    masq: false
```

The `network` list attaches the logical interface to the zone. The
policies have different directions:

- `input: REJECT` blocks guest devices from accessing services on the
  router, except for traffic allowed by separate firewall rules.
- `output: ACCEPT` allows traffic initiated by the router towards this
  zone.
- `forward: REJECT` prevents forwarding through this zone by default.

This does not, by itself, create DHCP, DNS, or guest-to-WAN forwarding
rules. Those must be configured separately. In particular, do not assume
that assigning an interface to a zone automatically grants Internet
access.

#### 2. Match a VPN tunnel device

When a VPN client creates a tunnel device dynamically, a device pattern
can be more suitable than binding the zone to a logical network interface:

```yaml
router_firewall_zones:
  vpn:
    device:
      - tun+
    family: ipv4
    input: REJECT
    output: ACCEPT
    forward: REJECT
    masq: false
```

The `tun+` pattern matches tunnel devices whose names start with
`tun`. Use the pattern supported by fw4; it is not an Ansible wildcard
or a declaration of the VPN itself. The VPN client, routing, and any
forwarding permissions still need their own configuration.

If TCP connections stall on a path with a smaller MTU (for example,
through some PPPoE or VPN links), `mtu_fix: true` enables TCP MSS clamping
for the zone. This adjusts the advertised TCP segment size to the path
MTU; it does not change the interface MTU. fw4 requires Linux kernel 4.10
or later for this option.

Use `family: ipv4` when this zone should apply only to IPv4 traffic.
Use `ipv6` for IPv6-only handling or `any` when both families should
be considered.

#### 3. Restrict masquerading on an existing WAN zone

Masquerading is commonly enabled on an egress zone. If the WAN zone
already exists, declare only the settings that this role should manage:

```yaml
router_firewall_zones:
  wan:
    masq: true
    masq6: false
    masq_src:
      - 192.168.50.0/24
```

Here, IPv4 masquerading is enabled, IPv6 masquerading is explicitly
disabled, and the source list limits masquerading to traffic originating from
that subnet. An optional `masq_dest` list can further constrain the remote
addresses to which masquerading applies. These options accept the same
network specifications as `subnet`: CIDR prefixes, individual addresses,
address ranges, and logical network names. Prefix a value with `!` to
exclude it. For example, `masq_dest: ["!203.0.113.0/24"]` excludes that
remote prefix. Adapt all values to the actual addresses in your network.
`masq6: true` separately enables IPv6 masquerading. IPv6 normally uses
routed global addresses without NAT, so enable it only when your IPv6
network design explicitly requires address translation; do not treat it
as a routine counterpart to IPv4 masquerading.

These options do not create routes or forwarding permissions, and they do
not replace the WAN interface configuration.

If the existing WAN zone has other options, they remain untouched because
they are not included in this declaration. Check the resulting fw4 rules
on the router before relying on a restrictive prefix combination.

#### 4. Match IP subnets without assigning a network interface

Use `subnet` when zone membership should be determined by IP address
ranges rather than by a logical network or device:

```yaml
router_firewall_zones:
  lab:
    subnet:
      - 192.168.60.0/24
    input: REJECT
    output: ACCEPT
    forward: REJECT
```

The subnet is used to classify traffic by IP address: inbound traffic
is matched against its source address, while outbound traffic is matched
against its destination address. fw4 accepts CIDR prefixes, individual
IP addresses, address ranges, and names of logical networks known to
netifd. For example, `192.168.60.0/24` matches a prefix, while `lab`
uses the addresses currently assigned to that logical network.

This does not create an interface, address, route, or network. Prefer
`network` for normal netifd-managed interfaces; use `device` for direct
device matching. Use `subnet` when address-based classification is
specifically intended.

#### 5. Enable zone logging with a rate limit

The `log` option is an integer bit field, not a simple boolean:

- Bit 0 (value `1`) enables logging for zone filter verdicts (accept,
  reject, or drop handling where applicable).
- Bit 1 (value `2`) enables logging for TCP MSS-fix rules.
- Use `3` to enable both types of logging.

For example, log filter verdicts and limit the rate of messages:

```yaml
router_firewall_zones:
  guest:
    log: 1
    log_limit: 10/minute
```

`log_limit` accepts a rate such as `10/minute`, `5/second`, or
`100/hour`. It limits emitted log messages; it does not limit network
traffic. Logging can produce substantial system log traffic, so enable it
deliberately and reduce or remove it after troubleshooting.

#### 6. Control masquerading of invalid connection states

When masquerading is enabled and the global `drop_invalid` firewall
default is disabled, fw4 adds per-zone rules to drop packets with an
invalid conntrack state. This prevents traffic with an invalid state
from bypassing the expected NAT path. Set `masq_allow_invalid: true` to
suppress those additional per-zone drop rules:

```yaml
router_firewall_zones:
  wan:
    masq: true
    masq_allow_invalid: true
```

This is an exception for specialized setups, not a general performance
or compatibility setting. Disabling the per-zone drop behavior can allow
traffic with invalid connection-tracking state through the masquerading
path. If global `drop_invalid` is enabled, fw4 already drops invalid
states globally and does not need these per-zone rules. Leave this option
unset or false unless you understand why the per-zone protection must be
changed.

#### 7. Configure connection-tracking helpers

Connection-tracking (conntrack) helpers inspect certain protocols and
can establish expectations for related connections. fw4 can assign
available helpers automatically, or a zone can request specific helpers:

```yaml
router_firewall_zones:
  legacy:
    network:
      - legacy
    auto_helper: false
    helper:
      - ftp
```

With `auto_helper: false`, automatic helper assignment is disabled for
this zone. The `helper` list explicitly requests the named helpers;
the helper must be available in the installed firewall/kernel packages.
The example requests the FTP helper only. Do not enable helpers
speculatively: protocol helpers add special connection-tracking behavior
and should be enabled only for protocols and devices that require them.

In firewall4, automatic helpers are normally enabled by default for
non-masquerading zones. Masquerading zones do not use automatic helper
assignment in the same way; explicit helpers can still request helper
handling. A global `auto_helper: false` setting in firewall defaults
also disables automatic helpers for zones.

#### 8. Disable per-zone packet counters

fw4 enables counters for zone verdict rules by default. Set
`counter: false` to omit those counters:

```yaml
router_firewall_zones:
  guest:
    counter: false
```

Counters are useful when inspecting packet/byte totals for traffic
accepted, rejected, or dropped by zone policy. Disable them only when
you deliberately do not need those statistics; this option does not
disable logging or change the zone's policies.

#### 9. Explicitly remove options without replacing the whole zone

A partial declaration changes only the options it contains. For example:

```yaml
router_firewall_zones:
  guest:
    input: DROP
    masq: null
    network: null
```

This changes the input policy and removes the existing `masq` and
`network` options. Other options on the zone remain unchanged. Use
`masq: false` instead of `masq: null` when the intention is to keep an
explicit disabled setting.

An empty list is not a removal instruction and is rejected:

```yaml
router_firewall_zones:
  guest:
    network: []
```

Use `network: null` to remove the list option.

#### 10. Disable a zone or remove it entirely

These operations are different:

```yaml
router_firewall_zones:
  guest:
    enabled: false
```

This keeps the UCI zone section but disables it in fw4. Other existing
zone options are retained.

```yaml
router_firewall_zones:
  guest:
    state: absent
```

This removes the entire zone section. The role refuses removal while
firewall rules, redirects, or forwardings still reference the zone.
Remove or update those references first; the role does not delete them
automatically.

### Adopt an existing anonymous zone

When no named section with the requested UCI section ID exists, the role
searches for zones with the desired name. Exactly one matching anonymous
zone is adopted by assigning the requested section ID. No match creates a
new named zone. An existing named section takes precedence over anonymous
matches. Multiple matches fail during validation rather than selecting
one arbitrarily.

A zone that already exists under a different named section ID is rejected;
use its existing ID instead of creating a duplicate.

### Remove a zone safely

Set `state: absent` to remove a zone:

```yaml
---
router_firewall_zones:
  guest:
    state: absent
```

The role resolves the target using the same named-section precedence and
unique anonymous-zone matching as updates. Before staging any writes, it
checks rule, redirect, and forwarding `src` and `dest` references.
Removal is rejected while any of those objects still references the zone.
Dependent objects are never cascade-deleted. Remove or update those
references first. Removing a zone that no longer exists is a no-op.

For removal, only `name` and `state` may be supplied. This permits
removing an anonymous zone by its actual name when that name differs from
the mapping key:

```yaml
---
router_firewall_zones:
  guest_zone:
    name: guest
    state: absent
```

## Additional Dropbear WAN access

The role can create a dedicated WAN firewall rule for the additional
Dropbear ports configured by `router_system`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `router_firewall_dropbear_extra_ports` | `[]` | TCP ports |
| `router_firewall_dropbear_wan_zone` | `""` | Source zone |

Configure both roles with the same port list. For example:

```yaml
---
router_system_dropbear_extra_ports:
  - 2222
router_firewall_dropbear_extra_ports:
  - 2222
router_firewall_dropbear_wan_zone: wan
```

The rule permits TCP access to those additional ports from the selected
zone. It does not restrict source IP addresses. An empty WAN zone or empty
port list removes the role-owned rule. The existing firewall policy for
SSH port 22 is not changed by this feature.

Expose SSH to the Internet only when necessary. Prefer key-based
authentication and restrict source addresses at another suitable layer
when your network design permits.

## Runtime reload and change handling

| Variable | Default | Purpose |
| --- | --- | --- |
| `router_firewall_apply_runtime_changes` | `true` | Reload fw4 after changes |

Default policies, declared zones and rules, and the optional Dropbear WAN
rule are staged together and committed once. The firewall is reloaded
once only when the UCI configuration changes. Set
`router_firewall_apply_runtime_changes: false` for configuration-only
runs where the runtime reload must be deferred. The UCI configuration is
still committed.

If applying the UCI operations fails, the role attempts to revert
uncommitted firewall changes and reports the preceding UCI error.
