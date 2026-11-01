# Router storage role

The router_storage role detects the OpenWrt x86/64 SquashFS root
partition and writable overlay layout. It can optionally expand the root
partition and overlay filesystem when unused space remains on a supported
SCSI/SATA or VirtIO disk.

The role is deliberately separate from site.yml. Storage expansion
changes partition and filesystem geometry and causes OpenWrt to reboot
twice. It must never happen as a side effect of the normal router
configuration.

## Inspect storage

Run the dedicated playbook without enabling expansion:

    ansible-playbook -i inventory.ini playbooks/storage.yml --limit router1

Detection is read-only. The role reports one of these states:

| State | Meaning |
| --- | --- |
| required | Unused space remains after the root partition |
| partial | Partition expanded; overlay filesystem still needs expansion |
| not_required | The partition and overlay already use available capacity |
| unsupported | Platform, filesystem, or disk type is unsupported |
| unknown | The layout could not be identified safely |

The initial implementation supports OpenWrt 25.12.x x86/64 SquashFS
combined images with an ext4 loop-backed overlay, using /dev/sdX or
/dev/vdX disks. NVMe and other device layouts
are deliberately not modified. The official OpenWrt expansion procedure
documents an NVMe issue that can leave the system unbootable.

## Expand root storage

Expansion is disabled by default. An already expanded system is reported
as not_required and left unchanged, even when expansion is enabled.

    router_storage_expand_root: false

Enable it explicitly for a selected host or invocation:

    ansible-playbook -i inventory.ini playbooks/storage.yml \\
      --limit router1 -e router_storage_expand_root=true

When enabled, the role:

1. Requires an unambiguous supported SquashFS layout with unused space.
2. Installs the expansion prerequisites using the detected OpenWrt
   package manager.
3. Installs the reviewed, repository-versioned resize scripts under
   `/etc/uci-defaults/` and persists both paths in `/etc/sysupgrade.conf`.
4. Clears stale resize markers if the virtual disk has grown again.
5. Starts the appropriate partition/filesystem expansion stage.
6. Waits for SSH to return after the required reboots.
7. Re-detects the storage layout and requires the final
   not_required state.

Expansion does not depend on a runtime download from the OpenWrt Wiki.
Both resize scripts are retained across sysupgrade through
`/etc/sysupgrade.conf`.

Do not run expansion against a production router without a verified
backup and a maintenance window. The first implementation is intended
for disposable x86/64 test VMs. The official procedure and its limitations
are documented at
[OpenWrt: Expanding root partition and filesystem](https://openwrt.org/docs/guide-user/advanced/expand_root).

## Current limitations

- Detection and expansion are limited to x86/64 SquashFS combined images.
- Supported root disks are currently /dev/sdX and /dev/vdX.
- NVMe, MMC, device-mapper, encrypted, and ambiguous layouts are
  not supported.
- The reboot wait checks the target's SSH port from the Ansible control
  node. Environments where SSH is reachable only through a jump host
  may need a different wait strategy.
- The role has not yet been validated against a physical or virtual
  system that has completed the full two-stage expansion. Use a
  disposable clone of an unexpanded Proxmox template for that test.
