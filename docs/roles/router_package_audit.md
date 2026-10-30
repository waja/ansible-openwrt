# Package audit role

The `router_package_audit` role compares the currently installed package
names with a saved baseline. It reports additions or removals; it does
not change the installed package set to match the baseline.

## Requirements

A baseline package list must already exist on each target router. The
default path is:

```text
/etc/backup/installed_packages.txt
```

The role does not create or deploy this baseline. Ensure that it is
generated or copied to each router before running the audit.

## Run the audit

Run the audit against all routers:

```bash
ansible-playbook -i inventory.ini playbooks/audit_packages.yml
```

Or run it against one router:

```bash
ansible-playbook -i inventory.ini playbooks/audit_packages.yml \
  --limit router1
```

## Configure the baseline path

The role variable `router_package_audit_baseline` defaults to
`/etc/backup/installed_packages.txt`. It is interpreted on the target
router, not on the Ansible control node.

Override it for a single run:

```bash
ansible-playbook -i inventory.ini playbooks/audit_packages.yml \
  -e router_package_audit_baseline=/path/to/installed_packages.txt
```

Or define it in inventory:

```yaml
---
router_package_audit_baseline: /etc/backup/router1-packages.txt
```

## What the audit does

The role first checks that the baseline exists and installs
`diffutils` if required. It obtains installed package names using
`opkg list_installed` or `apk info`, depending on the package manager
detected by `community.openwrt.init`. It sorts the baseline and current
package names before comparing them, then displays the differences.

Temporary audit files are created under a unique directory in `/tmp`
and removed at the end of the run, including when the comparison fails.
