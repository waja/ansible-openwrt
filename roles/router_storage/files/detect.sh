#!/bin/sh
# Detect the supported OpenWrt x86/64 SquashFS root storage layout.
# Environment overrides are used only by the fixture-based regression tests.

set -eu

PROC_MOUNTINFO=${PROC_MOUNTINFO:-/proc/self/mountinfo}
SYS_ROOT=${SYS_ROOT:-/sys}
RELEASE_FILE=${RELEASE_FILE:-/etc/openwrt_release}
ETC_ROOT=${ETC_ROOT:-/etc}
OVERLAY_MOUNTPOINT=${OVERLAY_MOUNTPOINT:-/overlay}
DF_COMMAND=${DF_COMMAND:-df}

mount_info() {
    awk -v mountpoint="$1" '
        $5 == mountpoint {
            for (i = 7; i <= NF; i++) {
                if ($i == "-") {
                    print $(i + 1) "|" $(i + 2) "|" $3
                    exit
                }
            }
        }
    ' "$PROC_MOUNTINFO"
}

target="$(. "$RELEASE_FILE"; printf '%s' "$DISTRIB_TARGET")"
release="$(. "$RELEASE_FILE"; printf '%s' "$DISTRIB_RELEASE")"
rom_info="$(mount_info /rom)"
root_info="$(mount_info /)"
overlay_info="$(mount_info /overlay)"

IFS='|' read -r rom_fstype rom_source rom_device <<EOF
$rom_info
EOF
IFS='|' read -r root_fstype root_source root_device <<EOF
$root_info
EOF
IFS='|' read -r overlay_fstype overlay_source overlay_device <<EOF
$overlay_info
EOF

root_partition=""
root_disk=""
partition_number=0
disk_sectors=0
partition_start=0
partition_sectors=0
later_partition=0
overlay_loop=""
loop_sectors=0
overlay_total_kb=0

if [ -n "$rom_device" ] && [ -e "$SYS_ROOT/dev/block/$rom_device" ]; then
    root_sysfs="$(readlink -f "$SYS_ROOT/dev/block/$rom_device")"
    root_partition="$(basename "$root_sysfs")"
    root_disk="$(basename "$(dirname "$root_sysfs")")"
    partition_number="$(cat \
        "$SYS_ROOT/class/block/$root_partition/partition" 2>/dev/null || echo 0)"
    disk_sectors="$(cat \
        "$SYS_ROOT/class/block/$root_disk/size" 2>/dev/null || echo 0)"
    partition_start="$(cat \
        "$SYS_ROOT/class/block/$root_partition/start" 2>/dev/null || echo 0)"
    partition_sectors="$(cat \
        "$SYS_ROOT/class/block/$root_partition/size" 2>/dev/null || echo 0)"
    for candidate in "$SYS_ROOT"/class/block/"$root_disk"[0-9]*; do
        [ -f "$candidate/partition" ] || continue
        candidate_name="$(basename "$candidate")"
        [ "$candidate_name" = "$root_partition" ] && continue
        candidate_start="$(cat "$candidate/start" 2>/dev/null || echo 0)"
        if [ "$candidate_start" -gt "$partition_start" ] 2>/dev/null; then
            later_partition=1
        fi
    done
fi

case "$overlay_source" in
    /dev/loop[0-9]*)
        overlay_loop="$(basename "$overlay_source")"
        loop_sectors="$(cat \
            "$SYS_ROOT/class/block/$overlay_loop/size" 2>/dev/null || echo 0)"
        overlay_total_kb="$("$DF_COMMAND" -Pk "$OVERLAY_MOUNTPOINT" 2>/dev/null | \
            awk 'NR == 2 {print $2}')"
        [ -n "$overlay_total_kb" ] || overlay_total_kb=0
        ;;
esac

rootpt_marker=0
rootfs_marker=0
[ ! -e "$ETC_ROOT/rootpt-resize" ] || rootpt_marker=1
[ ! -e "$ETC_ROOT/rootfs-resize" ] || rootfs_marker=1

state=unknown
layout_key="$target:$release:$rom_fstype:"
layout_key="$layout_key$root_fstype:$overlay_fstype:$rom_source"
case "$layout_key" in
    x86/64:25.12*:squashfs:overlay:ext4:/dev/root)
        case "$root_disk" in
            sd[a-z]|vd[a-z])
                if [ "$later_partition" -eq 1 ] ||
                    [ "$partition_number" -ne 2 ] 2>/dev/null; then
                    state=unsupported
                elif [ "$partition_number" -eq 2 ] 2>/dev/null &&
                    [ "$disk_sectors" -gt 0 ] 2>/dev/null &&
                    [ "$partition_sectors" -gt 0 ] 2>/dev/null &&
                    [ "$loop_sectors" -gt 0 ] 2>/dev/null &&
                    [ "$overlay_total_kb" -gt 0 ] 2>/dev/null; then
                    partition_end=$((partition_start + partition_sectors))
                    if [ "$partition_end" -lt "$((disk_sectors - 2048))" ]; then
                        state=required
                    elif [ "$rootpt_marker" -eq 1 ] &&
                        [ "$rootfs_marker" -eq 0 ]; then
                        state=partial
                    elif [ "$rootfs_marker" -eq 1 ] &&
                        [ "$rootpt_marker" -eq 0 ]; then
                        state=unknown
                    else
                        loop_total_kb=$((loop_sectors / 2))
                        if [ "$overlay_total_kb" -ge \
                            "$((loop_total_kb * 90 / 100))" ]; then
                            state=not_required
                        elif [ "$rootpt_marker" -eq 1 ] &&
                            [ "$rootfs_marker" -eq 1 ]; then
                            state=unknown
                        fi
                    fi
                fi
                ;;
            *)
                state=unsupported
                ;;
        esac
        ;;
    *)
        state=unsupported
        ;;
esac

printf '{"state":"%s","target":"%s","release":"%s",' \
    "$state" "$target" "$release"
printf '"rom_fstype":"%s",' "$rom_fstype"
printf '"rom_source":"%s","rom_device":"%s",' \
    "$rom_source" "$rom_device"
printf '"root_fstype":"%s","root_source":"%s",' \
    "$root_fstype" "$root_source"
printf '"overlay_fstype":"%s","overlay_source":"%s",' \
    "$overlay_fstype" "$overlay_source"
printf '"root_partition":"%s","root_disk":"%s",' \
    "$root_partition" "$root_disk"
printf '"partition_number":%s,"later_partition":%s,' \
    "$partition_number" "$later_partition"
printf '"disk_sectors":%s,' "$disk_sectors"
printf '"partition_start":%s,"partition_sectors":%s,' \
    "$partition_start" "$partition_sectors"
printf '"overlay_loop":"%s","loop_sectors":%s,' \
    "$overlay_loop" "$loop_sectors"
printf '"overlay_total_kb":%s,"rootpt_marker":%s,' \
    "$overlay_total_kb" "$rootpt_marker"
printf '"rootfs_marker":%s}\n' "$rootfs_marker"
