# Copyright (C) 2026 Cabinet Office, Japan, All rights reserved.
# Copyright (C) 2026 Lighthouse Technology & Consulting Co. Ltd., All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause
"""Thin compatibility layer for GUI code.

GUI keeps calling `execute(main_window, variables_main)` exactly as before,
while the actual logic is handled by `MadocalibRunner`.
"""


from adapters.madocalib_runner import MadocalibRunner
from core.runtime import get_settings

_runner_cache: MadocalibRunner | None = None


def _get_runner() -> MadocalibRunner:
    """Return a cached `MadocalibRunner` (module-level singleton).

    Notes:
        Not thread-safe; intended for single UI thread use.

    """
    global _runner_cache
    if _runner_cache is None:
        settings = (
            get_settings()
        )  # returns AppSettings (requires init_settings() called)
        _runner_cache = MadocalibRunner(settings=settings)
    return _runner_cache


def execute(main_window, variables_main) -> None:
    """Delegate execution to the cached runner (legacy API compatibility).

    Args:
        main_window: Tk root window.
        variables_main: ViewModel bound to the main window.

    """
    _get_runner().execute(main_window, variables_main)
