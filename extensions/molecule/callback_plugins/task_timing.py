# SPDX-License-Identifier: MIT
"""Temporary task-level timing callback for Molecule diagnostics."""

from __future__ import annotations

from collections import defaultdict
from time import monotonic

from ansible.plugins.callback import CallbackBase


DOCUMENTATION = r"""
    name: task_timing
    type: aggregate
    short_description: Report per-task wall-clock durations
    description:
      - Measures task execution duration per host.
      - Intended for temporary Molecule performance diagnostics.
    requirements:
      - Whitelisted in configuration.
"""

CALLBACK_VERSION = 2.0
CALLBACK_TYPE = "aggregate"
CALLBACK_NAME = "task_timing"
CALLBACK_NEEDS_ENABLED = True


class CallbackModule(CallbackBase):
    """Collect task durations and print a compact summary at playbook end."""

    def __init__(self):
        super().__init__()
        self._starts = {}
        self._durations = defaultdict(list)
        self._task_names = {}

    def v2_runner_on_start(self, host, task):
        key = (task._uuid, host.get_name())
        self._starts[key] = monotonic()
        self._task_names[task._uuid] = self._describe_task(task)

    def v2_runner_on_ok(self, result):
        self._finish(result)

    def v2_runner_on_failed(self, result, ignore_errors=False):
        self._finish(result)

    def v2_runner_on_skipped(self, result):
        self._finish(result)

    def v2_runner_on_unreachable(self, result):
        self._finish(result)

    def _finish(self, result):
        task = result._task
        host = result._host.get_name()
        key = (task._uuid, host)
        started = self._starts.pop(key, None)
        if started is None:
            return

        duration = monotonic() - started
        description = self._task_names.get(task._uuid, self._describe_task(task))
        status = "changed" if result.is_changed() else "ok"
        if result.is_failed():
            status = "failed"
        elif result.is_unreachable():
            status = "unreachable"
        elif result.is_skipped():
            status = "skipped"

        self._durations[(description, status)].append(duration)

    @staticmethod
    def _describe_task(task):
        role = getattr(task, "_role", None)
        role_name = role.get_name() if role else "no-role"
        action = getattr(task, "action", "unknown")
        return f"{role_name} | {task.get_name().strip()} | {action}"

    def v2_playbook_on_stats(self, stats):
        if not self._durations:
            return

        self._display.display("")
        self._display.display("TASK TIMING PROFILE (seconds; per host invocation)")
        rows = []
        for (description, status), durations in self._durations.items():
            total = sum(durations)
            rows.append((total, max(durations), len(durations), description, status))

        for total, maximum, count, description, status in sorted(rows, reverse=True):
            self._display.display(
                f"{total:8.3f}s total | {maximum:8.3f}s max | "
                f"{count:3d} run(s) | {status:10s} | {description}"
            )
