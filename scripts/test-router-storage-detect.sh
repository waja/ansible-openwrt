#!/bin/sh
# Fixture-based regression tests for router-storage-detect.sh.

set -eu

DETECT_SCRIPT=${1:?Usage: test-router-storage-detect.sh DETECT_SCRIPT}
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT HUP INT TERM

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

new_fixture() {
    FIXTURE="$TMP_ROOT/$1"
    SYS_ROOT="$FIXTURE/sys"
    ETC_ROOT="$FIXTURE/etc"
    RELEASE_FILE="$FIXTURE/openwrt_release"
    PROC_MOUNTINFO="$FIXTURE/mountinfo"
    DF_COMMAND="$FIXTURE/bin/df"

    mkdir -p \
        "$SYS_ROOT/dev/block" \
        "$SYS_ROOT/class/block" \
        "$SYS_ROOT/devices/platform/mock/block/sda/sda1" \
        "$SYS_ROOT/devices/platform/mock/block/sda/sda2" \
        "$SYS_ROOT/devices/virtual/block/loop0" \
        "$ETC_ROOT" "$FIXTURE/bin"

    cat > "$RELEASE_FILE" <<'EOF'
DISTRIB_TARGET='x86/64'
DISTRIB_RELEASE='25.12.5'
EOF

    cat > "$PROC_MOUNTINFO" <<'EOF'
1 0 8:2 / /rom ro - squashfs /dev/root ro
2 0 7:0 / /overlay rw - ext4 /dev/loop0 rw
3 0 0:1 / / rw - overlay overlay rw
EOF

    ln -s "$SYS_ROOT/devices/platform/mock/block/sda" \
        "$SYS_ROOT/class/block/sda"
    printf '%s\n' 2097152 > "$SYS_ROOT/class/block/sda/size"
    printf '%s\n' 1 > "$SYS_ROOT/devices/platform/mock/block/sda/sda1/partition"
    printf '%s\n' 2048 > "$SYS_ROOT/devices/platform/mock/block/sda/sda1/start"
    printf '%s\n' 32768 > "$SYS_ROOT/devices/platform/mock/block/sda/sda1/size"
    printf '%s\n' 2 > "$SYS_ROOT/devices/platform/mock/block/sda/sda2/partition"
    printf '%s\n' 33280 > "$SYS_ROOT/devices/platform/mock/block/sda/sda2/start"
    printf '%s\n' 212992 > "$SYS_ROOT/devices/platform/mock/block/sda/sda2/size"
    printf '%s\n' 2000000 > "$SYS_ROOT/devices/virtual/block/loop0/size"

    ln -s "$SYS_ROOT/devices/platform/mock/block/sda/sda1" \
        "$SYS_ROOT/class/block/sda1"
    ln -s "$SYS_ROOT/devices/platform/mock/block/sda/sda2" \
        "$SYS_ROOT/class/block/sda2"
    ln -s "$SYS_ROOT/devices/virtual/block/loop0" \
        "$SYS_ROOT/class/block/loop0"
    ln -s "$SYS_ROOT/devices/platform/mock/block/sda/sda2" \
        "$SYS_ROOT/dev/block/8:2"

    cat > "$DF_COMMAND" <<'EOF'
#!/bin/sh
printf 'Filesystem 1024-blocks Used Available Capacity Mounted on\n'
printf '/dev/loop0 %s 1 1 1%% /overlay\n' "${DF_TOTAL_KB:-950000}"
EOF
    chmod +x "$DF_COMMAND"
}

run_case() {
    name=$1
    expected=$2
    df_total=$3
    result="$(
        PROC_MOUNTINFO="$PROC_MOUNTINFO" \
        SYS_ROOT="$SYS_ROOT" \
        RELEASE_FILE="$RELEASE_FILE" \
        ETC_ROOT="$ETC_ROOT" \
        DF_COMMAND="$DF_COMMAND" \
        DF_TOTAL_KB="$df_total" \
        sh "$DETECT_SCRIPT"
    )" || fail "$name: detector exited unsuccessfully"

    if ! printf '%s\n' "$result" | grep -Fq "\"state\":\"$expected\""; then
        echo "$name: expected $expected, got: $result" >&2
        exit 1
    fi
    echo "PASS: $name -> $expected"
}

new_fixture required
run_case "unused trailing disk space" required 950000

new_fixture partial
printf '%s\n' 2063872 > "$SYS_ROOT/devices/platform/mock/block/sda/sda2/size"
: > "$ETC_ROOT/rootpt-resize"
run_case "partition resized but filesystem pending" partial 500000

new_fixture complete
printf '%s\n' 2063872 > "$SYS_ROOT/devices/platform/mock/block/sda/sda2/size"
: > "$ETC_ROOT/rootpt-resize"
: > "$ETC_ROOT/rootfs-resize"
run_case "partition and filesystem expanded" not_required 950000

new_fixture wrong_root_partition
printf '%s\n' 3 > "$SYS_ROOT/devices/platform/mock/block/sda/sda2/partition"
run_case "unexpected root partition number is rejected" unsupported 950000

new_fixture later_partition
printf '%s\n' 2063872 > "$SYS_ROOT/devices/platform/mock/block/sda/sda2/size"
mkdir -p "$SYS_ROOT/devices/platform/mock/block/sda/sda3"
printf '%s\n' 3 > "$SYS_ROOT/devices/platform/mock/block/sda/sda3/partition"
printf '%s\n' 220000 > "$SYS_ROOT/devices/platform/mock/block/sda/sda3/start"
printf '%s\n' 1000 > "$SYS_ROOT/devices/platform/mock/block/sda/sda3/size"
ln -s "$SYS_ROOT/devices/platform/mock/block/sda/sda3" \
    "$SYS_ROOT/class/block/sda3"
run_case "later partition is rejected" unsupported 950000

new_fixture inconsistent_markers
printf '%s\n' 2063872 > "$SYS_ROOT/devices/platform/mock/block/sda/sda2/size"
: > "$ETC_ROOT/rootpt-resize"
: > "$ETC_ROOT/rootfs-resize"
run_case "completed marker with undersized overlay is ambiguous" unknown 500000

new_fixture incomplete_block_data
rm "$SYS_ROOT/devices/virtual/block/loop0/size"
run_case "missing loop-device size is unknown" unknown 950000

echo "All router storage detection tests passed."
