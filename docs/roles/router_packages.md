# Packages role

The `router_packages` role installs explicitly requested packages and
the packages required by services managed by `router_base`. It selects
the OpenWrt package manager dynamically after
`community.openwrt.init` has detected the target release.

## Run the role

```bash
ansible-playbook -i inventory.ini playbooks/site.yml \
  --limit router1 --tags router_packages
```

The standard `site.yml` playbook passes `router_base_services` to
`router_packages_managed_services`. When running this role independently,
set `router_packages_managed_services` yourself if you also want
packages for services managed elsewhere.

## Package variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `router_packages_list` | `busybox`, `openwrt-keyring`, `muninlite`, `rsync`, `uhttpd`, `uhttpd-mod-ubus`, `rpcd` | Packages to install directly |
| `router_packages_managed_services` | `[]` | Services whose packages should also be installed |
| `router_packages_service_package_map` | `snmpd: [snmpd]`, `xinetd: [xinetd]` | Mapping from service names to one or more package names |

Do not add packages to `router_packages_list` solely because they are
required by a managed service. For example, `snmpd` and `xinetd` are
installed automatically while they remain in the default
`router_base_services` list and have their default mappings. Add packages
to `router_packages_list` when you want them independently of the
managed service list.

Each mapping entry is a list of packages. A service can therefore require
multiple packages, and its service name does not have to match its package
name. Every service in `router_packages_managed_services` must have an
entry in the mapping; otherwise the role fails with an assertion error.
Duplicate package names are installed only once.

## Examples

### Set a common package list

Create `group_vars/openwrt.yml` next to the inventory file:

```yaml
---
router_packages_list:
  - busybox
  - openwrt-keyring
  - rsync
```

All hosts in the `openwrt` group use these values unless overridden by
host-specific variables.

### Override packages for one router

Create `host_vars/router2.yml`:

```yaml
---
router_packages_list:
  - busybox
  - openwrt-keyring
  - rsync
  - uhttpd
```

A host-specific `router_packages_list` replaces the group list
completely. Ansible does not merge the two lists automatically. Repeat
the full desired list when overriding a group-level list.

### Map a custom managed service to packages

If you add a service to `router_base_services`, add its package mapping
too. For example, if `example-daemon` is provided by
`example-package`:

```yaml
---
router_base_services:
  - snmpd
  - example-daemon

router_packages_service_package_map:
  snmpd:
    - snmpd
  xinetd:
    - xinetd
  example-daemon:
    - example-package
```

The mapping variable replaces the default mapping when set in inventory.
Include every mapping entry you still need, including defaults for
services you continue to manage. To make one service install multiple
packages, list all package names under that service.

## Package and service restart coordination

The package and base roles coordinate service restarts through a shared
temporary marker and restart lock. When package installation changes the
installed package set, `router_packages` marks service restarts as
pending. `router_base` then enables and starts the configured services
and restarts each affected service once. This avoids restarting services
before package installation has completed.
