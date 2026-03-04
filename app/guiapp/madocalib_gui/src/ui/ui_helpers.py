# Copyright (C) 2026 Cabinet Office, Japan, All rights reserved.
# Copyright (C) 2026 Lighthouse Technology & Consulting Co. Ltd., All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause
"""Tiny UI-only widget helpers for Tkinter/ttk."""


def set_entry_value(entry_widget, value: str) -> None:
    """Replace text inside an Entry-like widget."""
    entry_widget.delete(0, "end")
    entry_widget.insert(0, value)
