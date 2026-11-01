#!/bin/sh
# Failure-path tests for owrt-extra.sh. Run only in a disposable OpenWrt
# rootfs container: the tests create fixtures under /etc, /rom and /overlay.
set -eu

SCRIPT=/tmp/owrt-extra-test.sh
cp /opt/owrt-test/owrt-extra.sh "$SCRIPT"
chmod 700 "$SCRIPT"

fail() {
    echo "FAIL: $*" >&2
    exit 1
}
reset_case() {
    rm -rf /tmp/owrt-diff /tmp/owrt-extra.lock /tmp/ref
}
assert_no_run_state() {
    [ ! -e /tmp/owrt-extra.lock ] || fail "lock left behind"
    [ ! -e /tmp/ref ] || fail "reference tree left behind"
}

mkdir -p /overlay/upper /rom/etc/apk /tmp/sysinfo /etc/apk

# A missing required command must fail before creating the report.
reset_case
path_bin=/tmp/owrt-path-without-apk
mkdir -p "$path_bin"
for cmd in awk basename cat chmod chroot cmp comm cp diff dirname find grep id ln mkdir mktemp mount readlink rm sed sort sync tr uci umount sysupgrade apk wc; do
    [ "$cmd" = apk ] && continue
    resolved=$(command -v "$cmd" 2>/dev/null || true)
    if [ -n "$resolved" ]; then
        ln -s "$resolved" "$path_bin/$cmd"
    else
        printf '#!/bin/sh\nexit 0\n' > "$path_bin/$cmd"
        chmod 700 "$path_bin/$cmd"
    fi
done
if PATH="$path_bin" /bin/sh "$SCRIPT" > /tmp/missing-command.log 2>&1; then
    fail "missing command was accepted"
fi
grep -Fq "Required command not found: apk" /tmp/missing-command.log ||
    fail "missing-command diagnostic not found"
grep -Fq "required commands are missing" /tmp/missing-command.log ||
    fail "missing-command summary not found"
[ ! -e /tmp/owrt-diff ] || fail "report created before command preflight"
assert_no_run_state
# Reuse the isolated utility path for later metadata and command-failure cases.
PATH="$path_bin:$PATH"
export PATH

# Missing board metadata must also fail before report creation.
if [ -e /etc/board.json ]; then
    mv /etc/board.json /tmp/board.json.saved
    had_board=1
else
    had_board=0
fi
if /bin/sh "$SCRIPT" > /tmp/missing-board.log 2>&1; then
    fail "missing board.json was accepted"
fi
grep -Fq "/etc/board.json is missing" /tmp/missing-board.log ||
    { cat /tmp/missing-board.log >&2; fail "missing board.json diagnostic not found"; }
[ ! -e /tmp/owrt-diff ] || fail "report created before board preflight"
assert_no_run_state
if [ "$had_board" = 1 ]; then mv /tmp/board.json.saved /etc/board.json; fi

# Supply minimal board metadata for the remaining tests.
printf '{}\n' > /etc/board.json
if [ -e /tmp/sysinfo/board_name ]; then
    mv /tmp/sysinfo/board_name /tmp/board_name.saved
    had_board_name=1
else
    had_board_name=0
fi
if /bin/sh "$SCRIPT" > /tmp/missing-board-name.log 2>&1; then
    fail "missing board_name was accepted"
fi
grep -Fq "/tmp/sysinfo/board_name is missing" /tmp/missing-board-name.log ||
    fail "missing board_name diagnostic not found"
[ ! -e /tmp/owrt-diff ] || fail "report created before board_name preflight"
assert_no_run_state
if [ "$had_board_name" = 1 ]; then mv /tmp/board_name.saved /tmp/sysinfo/board_name; fi
printf 'test-board\n' > /tmp/sysinfo/board_name

# Stub only the operations that would require a real OpenWrt overlay/chroot.
# All other commands are the actual OpenWrt rootfs utilities.
stub=/tmp/owrt-stubs
mkdir -p "$stub"
cat > "$stub/mount" <<'EOF_MOUNT'
#!/bin/sh
exit 0
EOF_MOUNT
cat > "$stub/chroot" <<'EOF_CHROOT'
#!/bin/sh
exit 0
EOF_CHROOT
cat > "$stub/uci" <<'EOF_UCI'
#!/bin/sh
exit 0
EOF_UCI
cat > "$stub/sysupgrade" <<'EOF_SYSUPGRADE'
#!/bin/sh
if [ "${OWRT_TEST_SYSUPGRADE_FAIL:-0}" = 1 ]; then
    echo "simulated sysupgrade failure" >&2
    exit 42
fi
printf '/etc/config/network\n'
EOF_SYSUPGRADE
cat > "$stub/apk" <<'EOF_APK'
#!/bin/sh
case "$1" in
    info) exit 1 ;;
    list)
        case "${OWRT_TEST_APK_NOW:-ok}" in
            fail) echo "simulated current package query failure" >&2; exit 43 ;;
            empty) exit 0 ;;
            *) echo "base-files-1.0-r1"; exit 0 ;;
        esac
        ;;
    --root)
        case "${OWRT_TEST_APK_FACTORY:-ok}" in
            fail) echo "simulated factory package query failure" >&2; exit 44 ;;
            empty) exit 0 ;;
            *) echo "base-files-1.0-r1"; exit 0 ;;
        esac
        ;;
    audit)
        [ "${2:-}" = --help ] && { echo "--system"; exit 0; }
        exit 0
        ;;
esac
exit 0
EOF_APK
chmod 700 "$stub"/*

# Minimal APK world files; the factory comparison falls back to /rom.
: > /rom/etc/apk/world
: > /etc/apk/world
PATH="$stub:$PATH"
export PATH

run_failure_case() {
    name=$1
    expected=$2
    reset_case
    if /bin/sh "$SCRIPT" > "/tmp/$name.log" 2>&1; then
        cat "/tmp/$name.log" >&2
        fail "$name unexpectedly succeeded"
    fi
    grep -Fq "$expected" "/tmp/$name.log" ||
        { cat "/tmp/$name.log" >&2; fail "$name diagnostic not found"; }
    assert_no_run_state
    [ -d /tmp/owrt-diff ] || fail "$name did not preserve its diagnostic report"
}

OWRT_TEST_SYSUPGRADE_FAIL=1
export OWRT_TEST_SYSUPGRADE_FAIL
run_failure_case sysupgrade-failure "Required command failed: sysupgrade -l"
unset OWRT_TEST_SYSUPGRADE_FAIL

OWRT_TEST_APK_NOW=fail
export OWRT_TEST_APK_NOW
run_failure_case apk-current-failure "Required command failed: apk list --installed"
unset OWRT_TEST_APK_NOW

OWRT_TEST_APK_FACTORY=fail
export OWRT_TEST_APK_FACTORY
run_failure_case apk-factory-failure "Required command failed: apk --root"
unset OWRT_TEST_APK_FACTORY

OWRT_TEST_APK_NOW=empty
export OWRT_TEST_APK_NOW
run_failure_case apk-current-empty "APK returned an empty package list"
unset OWRT_TEST_APK_NOW

OWRT_TEST_APK_FACTORY=empty
export OWRT_TEST_APK_FACTORY
run_failure_case apk-factory-empty "APK returned an empty package list"
unset OWRT_TEST_APK_FACTORY

# Missing world files must be rejected before package-list queries.
reset_case
rm -f /rom/etc/apk/world
if /bin/sh "$SCRIPT" > /tmp/apk-world-missing.log 2>&1; then
    fail "missing factory APK world file was accepted"
fi
grep -Fq "Cannot compare explicitly installed packages: APK world file missing" /tmp/apk-world-missing.log ||
    fail "missing APK world diagnostic not found"
assert_no_run_state

echo "All owrt-extra.sh failure-path tests passed."
