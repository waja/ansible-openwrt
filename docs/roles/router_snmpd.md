# SNMP daemon role

The `router_snmpd` role optionally replaces the package-provided SNMP
community in the IPv4 and IPv6 community-to-security mappings. It retains
the existing read-only security name, group, view, and access mappings.
It does not add a second community or change unrelated SNMP settings.

## Enable the role

The role is opt-in. Enable it explicitly and provide a non-empty
community string in inventory, for example in `host_vars/router1.yml`:

```yaml
---
router_snmpd_enabled: true
router_snmpd_community: "replace-with-a-long-random-community"
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `router_snmpd_enabled` | `false` | Enable the role in `site.yml` |
| `router_snmpd_community` | `""` | Explicit community string to replace the default |

When enabled, the community must be a non-empty string without leading
or trailing whitespace and must not be `public`. There is no fallback
community value. The task is marked `no_log` to avoid exposing the
community in Ansible output.

Run the role after setting both variables:

```bash
ansible-playbook -i inventory.ini playbooks/site.yml \
  --limit router1 --tags router_snmpd
```

## Security considerations

SNMPv2c community strings are transmitted without encryption. Use a
unique, unguessable value and restrict access to UDP/161 at the network
firewall to trusted monitoring hosts. This role does not manage firewall
rules or SNMPv3 users.

Package installation and service enablement remain owned by
`router_packages` and `router_base`. The SNMP role only updates UCI
configuration and restarts `snmpd` when its community mapping changes.
