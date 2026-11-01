#!/usr/bin/env python3
"""Select the newest published pre-release for a package on PyPI."""

from __future__ import annotations

import json
import os
import sys
import urllib.request

from packaging.version import InvalidVersion, Version


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(f"Usage: {sys.argv[0]} PACKAGE")

    package = sys.argv[1]
    url = f"https://pypi.org/pypi/{package}/json"
    with urllib.request.urlopen(url, timeout=30) as response:
        releases = json.load(response)["releases"]

    stable_versions: list[Version] = []
    candidates: list[Version] = []
    for raw_version, files in releases.items():
        try:
            version = Version(raw_version)
        except InvalidVersion:
            continue

        if not any(not item.get("yanked", False) for item in files):
            continue

        if version.is_prerelease or version.is_devrelease:
            candidates.append(version)
        else:
            stable_versions.append(version)

    # Ignore abandoned pre-releases older than the current stable release.
    # They are not candidates for forward-compatibility testing.
    if stable_versions:
        latest_stable = max(stable_versions)
        candidates = [version for version in candidates if version > latest_stable]

    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        if candidates:
            selected = str(max(candidates))
            print(f"Selected {package} pre-release: {selected}")
            output.write(f"available=true\nversion={selected}\n")
        else:
            print(
                f"::notice::No {package} pre-release is available; "
                "no forward-compatibility test was run."
            )
            output.write("available=false\nversion=\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
