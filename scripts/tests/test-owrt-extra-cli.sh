#!/bin/sh
# Regression tests for owrt-extra.sh CLI and report cleanup.
set -eu

SCRIPT=${1:?usage: test-owrt-extra-cli.sh SCRIPT}
test -f "$SCRIPT"

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

expect_status() {
    expected=$1
    label=$2
    shift 2

    if busybox ash "$SCRIPT" "$@" > /tmp/owrt-cli.stdout 2> /tmp/owrt-cli.stderr; then
        actual=0
    else
        actual=$?
    fi

    if [ "$actual" -ne "$expected" ]; then
        echo "--- stdout ($label) ---" >&2
        cat /tmp/owrt-cli.stdout >&2
        echo "--- stderr ($label) ---" >&2
        cat /tmp/owrt-cli.stderr >&2
        fail "$label: expected status $expected, got $actual"
    fi
}

# An existing report is evidence and must not be overwritten by a new run.
rm -rf /tmp/owrt-diff /tmp/owrt-extra.lock /tmp/ref
mkdir -m 700 /tmp/owrt-diff
printf '%s\n' preserved > /tmp/owrt-diff/marker
test "$(cat /tmp/owrt-diff/marker)" = preserved
expect_status 1 "existing report" 
test -f /tmp/owrt-diff/marker || fail "existing report marker was removed"
test "$(cat /tmp/owrt-diff/marker)" = preserved ||
    fail "existing report marker contents changed"
grep -Fq -- "remove it explicitly with: $SCRIPT -c" /tmp/owrt-cli.stderr ||
    fail "existing report guidance missing"

# Report-only cleanup is idempotent and must not touch the reference tree.
busybox ash "$SCRIPT" -c
test ! -e /tmp/owrt-diff || fail "-c did not remove report"
busybox ash "$SCRIPT" -c
test ! -e /tmp/owrt-diff || fail "repeated -c was not idempotent"

# A pre-existing lock prevents cleanup from touching report or reference data.
mkdir -m 700 /tmp/owrt-extra.lock
mkdir -m 700 /tmp/owrt-diff
printf '%s\n' locked > /tmp/owrt-diff/marker
mkdir -p /tmp/ref/merged
expect_status 1 "cleanup with existing lock" -c
test -d /tmp/owrt-extra.lock || fail "cleanup removed the existing lock"
test "$(cat /tmp/owrt-diff/marker)" = locked ||
    fail "cleanup changed report under existing lock"
test -d /tmp/ref/merged || fail "cleanup touched reference tree under lock"
rmdir /tmp/owrt-extra.lock
busybox ash "$SCRIPT" -c
test ! -e /tmp/owrt-diff || fail "cleanup after lock release failed"
test -d /tmp/ref/merged || fail "report cleanup touched reference tree"
rm -rf /tmp/ref

# Cleanup must refuse symlinks without following them.
mkdir -m 700 /tmp/report-target
ln -s /tmp/report-target /tmp/owrt-diff
expect_status 1 "symlink report cleanup" -c
test -L /tmp/owrt-diff || fail "cleanup removed report symlink"
test -d /tmp/report-target || fail "cleanup followed report symlink"
rm /tmp/owrt-diff
rmdir /tmp/report-target

# Invalid options have a stable diagnostic and exit status.
expect_status 1 "unknown option" --invalid
test ! -s /tmp/owrt-cli.stdout || fail "unknown option wrote to stdout"
test "$(cat /tmp/owrt-cli.stderr)" = \
    "Unknown option: --invalid (allowed: -k -f -H -c -h)" ||
    fail "unexpected unknown-option diagnostic"

# A tmpfs mount test is best-effort because CI containers may lack CAP_SYS_ADMIN.
mkdir -m 700 /tmp/owrt-diff
if mount -t tmpfs tmpfs /tmp/owrt-diff 2>/dev/null; then
    expect_status 1 "mounted report cleanup" -c
    grep -Fq "Refusing to clean mounted path" /tmp/owrt-cli.stderr ||
        fail "mounted report refusal diagnostic missing"
    umount /tmp/owrt-diff
else
    echo "SKIP: mount namespace does not permit tmpfs mount test."
fi
rmdir /tmp/owrt-diff

echo "All owrt-extra CLI and cleanup tests passed."
