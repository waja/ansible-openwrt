#!/bin/sh
set -eu
HELPER=${1:?usage: test-router-storage-mount-options.sh HELPER}
# shellcheck disable=SC1090
. "$HELPER"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

verify_mount_options ext4 commit=5 rw,relatime,errors=remount-ro /opt ||
  fail "ext4 default commit=5 should be accepted"
verify_mount_options ext4 commit=5,rw rw,relatime /opt ||
  fail "ext4 default commit=5 in an option list should be accepted"
verify_mount_options ext4 commit=5 rw,commit=5,relatime /opt ||
  fail "explicit commit=5 should be accepted"
if verify_mount_options ext4 commit=5 rw,commit=600,relatime /opt 2>/dev/null; then
  fail "default commit=5 was accepted despite explicit commit=600"
fi
if verify_mount_options ext4 auto rw,relatime /opt 2>/dev/null; then
  fail "unsupported auto option was accepted"
fi
if verify_mount_options ext4 nouser rw,relatime /opt 2>/dev/null; then
  fail "unsupported nouser option was accepted"
fi
if verify_mount_options ext4 defaults rw,relatime /opt 2>/dev/null; then
  fail "explicit defaults option was accepted"
fi
if verify_mount_options ext4 commit=10 rw,relatime /opt 2>/dev/null; then
  fail "non-default commit=10 was accepted without an effective value"
fi
if verify_mount_options vfat commit=5 rw,relatime /opt 2>/dev/null; then
  fail "ext4-specific commit default was accepted for vfat"
fi
if verify_mount_options ext4 rw ro,relatime /opt 2>/dev/null; then
  fail "rw was accepted while effective options contain ro"
fi
verify_mount_options ext4 rw rw,relatime /opt ||
  fail "effective rw should be accepted"

echo "All router storage mount option tests passed."
