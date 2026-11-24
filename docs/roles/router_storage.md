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

## Root expansion limitations

- Detection and expansion are limited to x86/64 SquashFS combined images.
- Supported root disks are currently /dev/sdX and /dev/vdX.
- NVMe, MMC, device-mapper, encrypted, and ambiguous layouts are
  not supported.
- The reboot wait checks the target's SSH port from the Ansible control
  node. Environments where SSH is reachable only through a jump host
  may need a different wait strategy.
- Full expansion has been validated on a disposable OpenWrt 25.12.5
  x86/64 VM clone. The original Proxmox template was not modified.

## Optional external storage mounts

The same role can optionally manage external filesystems, independently of
root expansion. Mounts are disabled by default:

    router_storage_mounts: []

Configure each filesystem by its stable UUID. The target defaults to
`/opt` and the filesystem to `ext4`. Mount options are optional; when
omitted, no additional filesystem options are passed. Use a canonical UUID
for ext4 or the `1234-ABCD` volume identifier for VFAT. Hardware-specific
kernel modules belong in the per-mount `packages` list; they are not
installed automatically for every router.

    router_storage_mounts:
      - name: opt
        uuid: "00000000-0000-0000-0000-000000000000"
        target: /opt
        filesystem: ext4
        packages:
          - kmod-fs-ext4
          - kmod-mmc
          - kmod-sdhci-mt7620

The role installs `block-mount` and the explicitly requested packages,
checks that exactly one block device has the configured UUID and expected
filesystem, and manages a named mount section in `/etc/config/fstab`.
It enables the fstab init service for subsequent boots. At runtime it mounts
only the configured device directly; it does not run the global
`block mount` or `block umount` commands, which could affect unrelated
mounts.

Existing fstab sections are preserved. A conflicting UUID or target,
a non-mount section using the managed name, an already-mounted device at
another target, a conflicting mount at the target, or non-empty target
directory causes a clear failure. A target directory is created if absent.
No partitioning, formatting, filesystem repair, or device auto-selection
is performed.

For the MikroTik hEX S, the example kernel modules are hardware-specific
and must be verified against the exact device and OpenWrt image. Filesystem
creation and partitioning are intentionally manual prerequisites. Validate
the configuration on the target device before relying on it for services
that need persistent storage.
