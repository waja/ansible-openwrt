#!/usr/bin/env bash
# scripts/update-ci-lockfiles.sh
set -eu

readonly pip_tools_requirements="requirements/ci/pip-tools.in"
pip_tools_version="$(sed -n 's/^pip-tools==//p' "$pip_tools_requirements")"

if [ -z "$pip_tools_version" ] || [ "$(grep -c '^pip-tools==' "$pip_tools_requirements")" -ne 1 ]; then
  echo "Expected exactly one pip-tools pin in $pip_tools_requirements." >&2
  exit 1
fi
readonly shared_requirements="requirements/ci/ansible-core.in"

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
    --output-file="requirements/ci/${group}.txt" \
    "${shared_requirements}" \
    "requirements/ci/${group}.in"
done
