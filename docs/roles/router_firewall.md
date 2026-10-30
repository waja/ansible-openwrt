# Firewall role

The `router_firewall` role manages the firewall default policies,
explicitly declared firewall zones, and an optional WAN rule for additional
Dropbear SSH listeners. It does not currently manage arbitrary firewall
rules, redirects, forwardings, or SYN-flood protection.

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
firewall defaults section. `router_firewall_zones` defaults to an empty
mapping (`{}`), so no additional zones are managed unless you declare them.

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
| `network` | non-empty list of strings | Networks assigned to the zone |
| `input` | string | Input policy: `ACCEPT`, `REJECT`, or `DROP` |
| `output` | string | Output policy: `ACCEPT`, `REJECT`, or `DROP` |
| `forward` | string | Forward policy: `ACCEPT`, `REJECT`, or `DROP` |
| `masq` | boolean | Enable or disable masquerading |
| `mtu_fix` | boolean | Enable or disable MTU fixing |
| `state` | string | `present` (default) or `absent` |

Only the options in this table are accepted. The role validates the
complete declared zone input before applying UCI changes. A present zone
updates only the options supplied in its definition; omitted options are
not explicitly removed. Explicit `null` removal semantics and additional
zone options are not implemented yet.

A named section with the requested UCI section ID is updated in place; a
missing section is created. If the ID already belongs to a non-zone
section, the role fails before writing changes.

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
| `router_firewall_dropbear_extra_ports` | `[]` | TCP ports configured by `router_system_dropbear_extra_ports` |
| `router_firewall_dropbear_wan_zone` | `""` | Firewall source zone to allow; empty disables the rule |

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
| `router_firewall_apply_runtime_changes` | `true` | Reload fw4 after a configuration change |

Default policies, declared zones, and the optional Dropbear WAN rule are
staged together and committed once. The firewall is reloaded once only
when the UCI configuration changes. Set
`router_firewall_apply_runtime_changes: false` for configuration-only
runs where the runtime reload must be deferred. The UCI configuration is
still committed.

If applying the UCI operations fails, the role attempts to revert
uncommitted firewall changes and reports the preceding UCI error.
