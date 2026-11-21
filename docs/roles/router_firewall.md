# Firewall role

The `router_firewall` role manages the firewall default policies,
explicitly declared firewall zones, filter rules, DNAT/SNAT redirects, inter-zone forwardings, and an optional WAN rule for
additional Dropbear SSH listeners.

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

## Global firewall defaults

The role manages only explicitly supplied global options in the first
`config defaults` section. The public interface is an intentional
whitelist of options consumed by firewall4 on OpenWrt 25.12. Arbitrary UCI
pass-through is not supported.

| Variable | YAML type | Accepted values / behavior |
| --- | --- | --- |
| `router_firewall_default_input` | string | `ACCEPT`, `REJECT`, or `DROP` |
| `router_firewall_default_forward` | string | `ACCEPT`, `REJECT`, or `DROP` |
| `router_firewall_default_output` | string | `ACCEPT`, `REJECT`, or `DROP` |
| `router_firewall_default_synflood_protect` | boolean | Enable or disable fw4 SYN flood protection |
| `router_firewall_default_synflood_rate` | string | Positive rate, e.g. `25/second`, `25/minute`, `25/hour`, or `25/day` |
| `router_firewall_default_synflood_burst` | integer | Non-negative packet burst |
| `router_firewall_default_drop_invalid` | boolean | Drop packets with invalid conntrack state in the generated input, forward, and output chains |
| `router_firewall_default_flow_offloading` | boolean | Enable software flow offloading where fw4 can resolve zone devices |
| `router_firewall_default_flow_offloading_hw` | boolean | Request hardware flow offloading for a supported device/driver |

All variables are optional and deliberately have no role defaults. This is
important: an omitted variable does not write anything to UCI and preserves
the router's existing value. An explicitly supplied `null` removes the
corresponding UCI option. A boolean `false` writes `0`; it is not a removal
instruction.

The former policy variables `router_firewall_input`,
`router_firewall_forward`, and `router_firewall_output` are no longer
accepted. The role fails with a migration hint if one is explicitly set.
Rename them to `router_firewall_default_input`,
`router_firewall_default_forward`, and `router_firewall_default_output`.

Example:

```yaml
router_firewall_default_input: REJECT
router_firewall_default_forward: REJECT
router_firewall_default_output: ACCEPT

router_firewall_default_synflood_protect: true
router_firewall_default_synflood_rate: 25/second
router_firewall_default_synflood_burst: 50
router_firewall_default_drop_invalid: true

router_firewall_default_flow_offloading: true
router_firewall_default_flow_offloading_hw: false
```

### OpenWrt 25.12 fw4 fallback values

The following are fw4 parser fallbacks when the corresponding option is
absent from UCI. They are not role defaults: the role still leaves an
omitted variable untouched. The shipped firewall configuration may contain
explicit values that take precedence over these parser fallbacks.

| UCI option | fw4 fallback when absent | Actual fw4 behavior |
| --- | --- | --- |
| `input`, `forward`, `output` | `DROP` | Used as the policy of the corresponding filter chain |
| `synflood_protect` | No independent fallback; fw4 falls back to legacy `syn_flood` when unset | Enables the SYN flood chain when a rate is available; the shipped firewall config sets `syn_flood=1` |
| `synflood_rate` | `25/second` | Rate used by the SYN flood chain |
| `synflood_burst` | `50` | Optional burst limit in packets; zero omits the burst clause |
| `drop_invalid` | Unset (treated as false by the ruleset template) | Adds invalid conntrack-state drops when true |
| `flow_offloading` | `0` | Builds a software flowtable only when eligible zone devices can be resolved |
| `flow_offloading_hw` | `0` | Adds the nftables `flags offload` request when software flow offloading is enabled |

fw4's 25.12 parser also accepts `tcp_syncookies` (boolean, parser
fallback `1`), `tcp_ecn` (integer, no explicit fallback), and
`tcp_window_scaling` (boolean, parser fallback `1`). Those values are
stored by the parser but are not consumed by the generated firewall
ruleset. `tcp_westwood` is not present in the parser. The parser marks
`disable_ipv6` unsupported. This role deliberately exposes none of them.

### Security and performance considerations

SYN flood protection adds a rate-limited SYN chain when
`router_firewall_default_synflood_protect` is enabled and a rate is
available. The default fw4 parser rate is `25/second` and its default burst
is `50` packets when those options are not present in UCI. Set a rate and
burst deliberately for the router's traffic profile; overly restrictive
limits can affect legitimate connection bursts.

`drop_invalid` adds explicit drops for packets classified by conntrack as
invalid in the generated input, forward, and output chains. This is a
security hardening choice and can affect unusual network setups that
intentionally pass traffic in an invalid conntrack state.

Software flow offloading can reduce CPU load and improve forwarding
throughput, but it changes the packet path. fw4 places a flowtable ingress
hook and adds eligible TCP/UDP forwarding flows to it. Packets using that
fast path do not traverse every ordinary forward-chain rule on every
packet, which can affect the visibility and effectiveness of additional
per-packet filtering, accounting, logging, traffic shaping, or inspection.
Validate the impact on the router and enabled firewall features before
turning it on.

Hardware flow offloading is an additional request on top of software flow
offloading. It requires a compatible kernel, nftables implementation,
network driver, and hardware datapath. fw4 checks whether the nftables
hardware-offload flowtable can be installed; on the tested code path it can
fall back to software offloading when hardware offload is unavailable.
A UCI value of `1` is therefore not proof that hardware acceleration is
active. Inspect the generated ruleset and actual platform/datapath state.
The role does not try to infer hardware capability or enable unsupported
features automatically.

Issue [#164](https://github.com/waja/ansible-openwrt/issues/164) records
runtime validation of the CVE-2026-98432 mitigation with active software
flow offloading on OpenWrt 25.12.5 / kernel 6.12.94 / QEMU x86_64. That
test exercised an established flow with `[OFFLOAD]` state. Hardware flow
offloading was not validated: QEMU virtual NICs do not establish hardware
datapath support, and the productive Turris inspection was read-only.
Do not generalize those results to other kernels, drivers, or hardware
offload implementations.

The role intentionally does not expose `tcp_syncookies`, `tcp_ecn`,
`tcp_window_scaling`, or `tcp_westwood`: the 25.12 fw4 parser contains
some of these names, but they are not consumed by fw4's generated firewall
ruleset; `tcp_westwood` is absent from that parser. `disable_ipv6` is marked unsupported by the 25.12 firewall4 parser. These settings are not silently passed through,
and arbitrary `router_firewall_default_*` names are rejected.

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
digits, and underscores. The optional `name` is the human-readable rule
label and defaults to the mapping key for newly created named sections.
Anonymous UCI rules are adopted only when `name` is explicitly supplied;
the mapping key is not an implicit adoption identity. Adoption is refused if
more than one candidate exists. An existing named section with the requested
ID takes precedence.

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

## Declarative firewall redirects (DNAT and SNAT)

Declare redirects as a mapping keyed by the desired UCI section ID:

```yaml
router_firewall_redirects:
  https_to_server:
    name: HTTPS to internal server
    src: wan
    src_dport: "443"
    dest: lan
    dest_ip: 192.0.2.20
    dest_port: "443"
    proto:
      - tcp
    target: DNAT
```

A redirect is a NAT mapping, not a filter rule. Use `target: DNAT` for
destination NAT, including ordinary port forwarding. Use `target: SNAT`
for source NAT. The mapping key is the stable UCI section ID and may contain
only letters, digits, and underscores. The optional `name` is a descriptive
label and defaults to the mapping key.

The role prefers an existing named UCI section with the requested ID. If
none exists, it adopts an anonymous redirect only when exactly one
redirect has the explicitly supplied `name`. Multiple matches are rejected.
An existing section of another UCI type is a conflict and is rejected.

Use `state: absent` to remove a redirect and `enabled: false` to retain
but disable its section. Omitted options remain unchanged; explicit
`null` removes an option. Empty lists are rejected; use `null` to remove
list-valued options.

Supported options are `src`, `src_ip`, `src_mac`, `src_port`, `src_dip`,
`src_dport`, `dest`, `dest_ip`, `dest_port`, `proto`, `family`, `target`,
`mark`, `reflection`, `reflection_src`, `reflection_zone`, `limit`,
`limit_burst`, `start_date`, `start_time`, `stop_date`, `stop_time`,
`weekdays`, `utc_time`, and `helper`. `proto`, `src_mac`, and
`reflection_zone` accept non-empty lists where supported. `weekdays` is a
whitespace-separated string, for example `mon wed`. Zone references must
resolve to existing zones or zones declared as present in the same role
invocation.

The role intentionally does not expose `ipset`, `monthdays`, or legacy
`extra` redirect options because they are unsupported by the target fw4
implementation.

DNAT normally specifies the destination host in `dest_ip`; optional
`src_dport` and `dest_port` define the external and translated ports.
SNAT uses optional `src_ip` to match the original source and required
`src_dip` to rewrite it, with `dest` identifying the egress zone.
New redirects default to DNAT when `target` is omitted and require
`src` (a specific source zone, not `*`). Explicit SNAT redirects require
`dest` (a specific destination zone, not `*`) and `src_dip` (the
translated source address); `src_ip` is an optional source match. SNAT
does not support `src_mac`, `helper`, or reflection options. For DNAT,
`src_dip` matches the incoming destination address, `src_dport` matches
the incoming destination port, and `dest_ip`/`dest_port` specify the
translated destination. For SNAT, `dest` is the egress zone,
`dest_ip`/`dest_port` are destination matches, and `src_dport` specifies
a translated source port. Reflection options apply only to DNAT.

Existing redirects support partial updates: omitted options, including
`src` and `target`, remain unchanged. For an existing redirect with
`state: present` (the default), omitting `target` is allowed only when the
update does not add `src_mac`, `helper`, or reflection options (`reflection`,
`reflection_src`, or `reflection_zone`), and does not remove `src`, `dest`, or
`src_dip` with `null`. These changes require an explicit `target` so the role
can validate DNAT/SNAT compatibility.

When an enabled `state: present` operation explicitly declares `target`, it
must also declare that target's required zone/address fields in the same
mapping: DNAT requires a specific, non-wildcard `src`; SNAT requires a
specific, non-wildcard `dest` and `src_dip`. Stored values do not satisfy
these requirements for an explicitly targeted update. The exception is a
new redirect: when `target` is omitted, it defaults to DNAT and requires
`src`. The role does not infer routing, policy, or address assignments.

All redirect operations are staged with zones and rules, then committed
once and followed by at most one firewall reload. As with other firewall
changes, applying them over SSH can interrupt the management session.

## Declarative inter-zone forwardings

Manage `config forwarding` entries with a list. A forwarding's stable
identity is its source zone, destination zone, and effective address family.
The effective family defaults to `any`; separate `ipv4` and `ipv6`
forwardings between the same zones are independent entries.

```yaml
router_firewall_forwardings:
  - src: lan
    dest: wan
    family: any
    name: LAN to WAN

  - src: guest
    dest: wan
    family: ipv4
    enabled: false

  - src: old_lan
    dest: wan
    family: any
    state: absent
```

Both `src` and `dest` are required zone names. They must refer to
existing zones or zones declared `present` in `router_firewall_zones`
in the same role invocation. A zone declared `absent` cannot be referenced.
The role never creates a zone implicitly.

The optional `name` is descriptive and is not used for identity. Existing
named and anonymous UCI forwardings are matched by the identity tuple. More
than one matching section is rejected with the full tuple in the error
message. Matched sections are assigned a stable role-owned UCI section ID
derived from that tuple, so later updates and removals do not depend on
anonymous section indexes.

Use `enabled: false` to disable a forwarding without removing it;
`state: absent` removes only the exact identity tuple. Omitted optional
values remain unchanged. Explicit `null` removes an option; for example,
`family: null` removes an explicit family option while retaining the
effective `any` identity. Forwardings not listed remain untouched.

All forwarding operations are validated before writes and are staged with
the other firewall objects. They share the single UCI commit and conditional
firewall reload; no forwarding-specific commit or reload is performed.

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
checks rule and forwarding `src` and `dest` references, as well as redirect
`src`, `dest`, and `reflection_zone` references.
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

Default policies, declared zones, rules, redirects and inter-zone
forwardings, and the optional Dropbear WAN rule are staged together and committed once. The firewall is
reloaded once only when the UCI configuration changes. Set
`router_firewall_apply_runtime_changes: false` for configuration-only
runs where the runtime reload must be deferred. The UCI configuration is
still committed.

If applying the UCI operations fails, the role attempts to revert
uncommitted firewall changes and reports the preceding UCI error.
