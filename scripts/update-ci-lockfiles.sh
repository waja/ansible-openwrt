#!/usr/bin/env bash
# scripts/update-ci-lockfiles.sh
set -euo pipefail

readonly pip_tools_version="7.6.2"

if ! pip-compile --version | grep -Fq "version ${pip_tools_version}"; then
  echo "pip-tools ${pip_tools_version} is required." >&2
  exit 1
fi

for group in lint ansible-test molecule; do
  pip-compile \
    --generate-hashes \
    --allow-unsafe \
    --resolver=backtracking \
    --no-emit-index-url \
    --output-file=".github/workflows/requirements-${group}.txt" \
    ".github/workflows/requirements-${group}.in"
done
