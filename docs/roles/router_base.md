# Base services role

The `router_base` role enables and starts the configured core services
and removes obsolete configuration files. Package installation is owned
by `router_packages`; this role does not install packages.

## Run the role

```bash
ansible-playbook -i inventory.ini playbooks/site.yml \
  --limit router1 --tags router_base
```

## Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `router_base_services` | `[snmpd, xinetd]` | Services to enable and keep started |
| `router_base_obsolete_files` | `[/etc/config/snmpd-opkg]` | Obsolete configuration files to remove |

For example, to manage a different service set on one router:

```yaml
---
router_base_services:
  - snmpd
  - xinetd
  - example-daemon

router_base_obsolete_files:
  - /etc/config/snmpd-opkg
  - /etc/config/old-service
```

Only list services that exist on the target router. Ensure their
corresponding packages are installed. In the standard `site.yml`
playbook, `router_packages_managed_services` is populated from
`router_base_services`; the package role uses
`router_packages_service_package_map` to determine which packages to
install. See the [packages guide](router_packages.md).

## Service restart coordination

The package and base roles share a restart lock and temporary marker
files under `/tmp`. If package installation changed the installed
package set, the base role enables and starts the configured services,
then restarts services that have not yet been marked as restarted.
It clears the pending marker and completion markers after processing.

When no package restart is pending, the role still ensures each configured
service is enabled and started, but it does not force a restart solely
because the role ran. This keeps repeated runs idempotent while ensuring
newly installed or updated service packages are activated.
