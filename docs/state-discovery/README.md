# OpenWrt state discovery

For a router that already has manual changes, use the read-only discovery
script `scripts/owrt-extra.sh` to compare the live system with a
reconstructed factory reference and collect likely Ansible candidates.
Copy it to the router and run it there as root on OpenWrt; it is not an
Ansible playbook.

```sh
scp scripts/owrt-extra.sh root@router1:/tmp/owrt-extra.sh
ssh root@router1 'sh /tmp/owrt-extra.sh'
```

The report is written to `/tmp/owrt-diff/` in RAM. Treat it as sensitive:
UCI output can include Wi-Fi passwords and other secrets. The script does
not print password hashes, and host-key export is opt-in (`-H`); with
`-H`, private keys are copied in plaintext under
`/tmp/owrt-diff/secrets/`. Review and securely retrieve only what
you need, then remove the report and script from the router.

Options: `-k` keeps the temporary factory reference mounted for
inspection, `-f` rebuilds that reference, and `-H` exports host keys.
Read the script's help (`sh /tmp/owrt-extra.sh -h`) before using these
options.

The report includes a UCI diff, overlay-file candidates, package and
service differences, and—when supported—`apk audit --system` output in
`/tmp/owrt-diff/apk-audit-system.txt`. The APK audit can detect modified
package-owned system files outside protected configuration paths, but it
does not report arbitrary untracked files; the overlay scan handles a
different set of candidates. This check requires an APK-based OpenWrt
system (25.12+) and is skipped with a warning when the command or option
is unavailable.

CI checks shell syntax and command-line behavior using the OpenWrt 25.12
rootfs image. It does not run the full discovery workflow in that
container: the rootfs image does not provide the same device-like overlay
environment as a booted OpenWrt router. The mount/chroot reconstruction
and detection of real overlay changes still need validation on a suitable
OpenWrt VM or physical router.

This is an investigative report, not an automatic Ansible generator.
Runtime state such as manually installed nftables rules, `ip` changes,
temporary `sysctl` values, loaded modules, and running processes is not
comprehensively captured. Files in the overlay may also be caches or
service state rather than configuration. Review each candidate before
managing it with Ansible. Data outside the overlay, such as calibration
data and bootloader storage, is not suitable for normal Ansible
configuration.
