# Copyright (C) 2026 Cabinet Office, Japan, All rights reserved.
# Copyright (C) 2026 Lighthouse Technology & Consulting Co. Ltd., All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause
"""ViewModel-like container for main-window runtime variables.

This dataclass holds Tk widgets (entries/combos/buttons) and helper methods to
read/write validated values and to keep small caches (e.g., progress time range).
"""

from __future__ import annotations

import logging
import tkinter as tk
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from tkinter import ttk
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class VariablesMain:
    """Main interface to provide validated runtime variables."""

    # ---- Inputs (path entries / combos / check) ----
    hcombo_file_rinex_obs: tk.Widget | None = None  # RINEX OBS (HistoryCombobox)
    hcombo_file_rinex_nav: tk.Widget | None = None  # RINEX NAV (HistoryCombobox)
    hcombo_folder_l6d: tk.Widget | None = None  # L6D folder (HistoryCombobox)
    hcombo_folder_l6e: tk.Widget | None = None  # L6E folder (HistoryCombobox)
    hcombo_folder_solution: tk.Widget | None = None  # Output folder (HistoryCombobox)
    hcombo_file_solution: tk.Widget | None = (
        None  # Solution path/name (HistoryCombobox)
    )

    entry_start_date: tk.Entry | None = None  # TimeStart (date)
    entry_start_time: tk.Entry | None = None  # TimeStart (time)
    entry_end_date: tk.Entry | None = None  # TimeEnd (date)
    entry_end_time: tk.Entry | None = None  # TimeEnd (time)

    combo_interval: ttk.Combobox | None = None  # Interval(sec)
    combo_timespan: ttk.Combobox | None = None  # TimeSpan(sec)
    combo_spanshift: ttk.Combobox | None = None  # SpanShift(sec)

    ivar_folder_solution_enabled: tk.IntVar | None = None  # OutputDir toggle (Dir)

    # ---- Buttons (assigned by view) ----
    btn_file_rinex_obs: tk.Widget | None = None
    btn_file_rinex_nav: tk.Widget | None = None
    btn_folder_l6d: tk.Widget | None = None
    btn_folder_solution: tk.Widget | None = None
    btn_file_solution: tk.Widget | None = None
    btn_plot: tk.Widget | None = None
    btn_options: tk.Widget | None = None
    btn_execute: tk.Widget | None = None
    btn_exit: tk.Widget | None = None
    btn_folder_l6e: tk.Widget | None = None
    btn_start_date: tk.Widget | None = None
    btn_end_date: tk.Widget | None = None

    chk_output_dir_mode: tk.Checkbutton | None = None  # Checkbutton widget (Dir)

    # ---- L6 patterns (populated by file helpers) ----
    patterns_sat_l6e: list[str] | None = None
    patterns_sat_l6d: list[str] | None = None

    # ---- Time range cache (for progress %) ----
    progress_start_dt: datetime | None = None
    progress_end_dt: datetime | None = None

    # ---- Lock targets (assigned by view) ----
    lock_targets: List[tk.Widget] = field(default_factory=list)

    # ---- Helpers required by view ----
    def get_solution_path(self) -> str:
        """Return absolute solution path. Join folder+filename when Dir mode is ON."""
        try:
            if (
                self.ivar_folder_solution_enabled
                and self.ivar_folder_solution_enabled.get() == 1
            ):
                folder = (self.hcombo_folder_solution.get() or "").strip()
                fname = (self.hcombo_file_solution.get() or "").strip()
                if not fname:
                    return ""
                return (
                    str(Path(folder) / Path(fname).name)
                    if folder
                    else str(Path(fname).resolve())
                )
            else:
                return self.hcombo_file_solution.get()
        except Exception:
            return ""

    # ---- Time fields sync helpers (used after RINEX parse) ----
    def clear_time_start_end(self) -> None:
        """Clear TS/TE entries."""
        for w in (
            self.entry_start_date,
            self.entry_start_time,
            self.entry_end_date,
            self.entry_end_time,
        ):
            try:
                if w:
                    w.delete(0, "end")
            except Exception as e:
                logger.debug("clear_time_start_end: widget op failed: %r", e)

    def update_time_start_end(
        self,
        ts: datetime | None,
        te: datetime | None,
        interval: float | None,
    ) -> None:
        """Write parsed TS (=TimeStart) / TE (=TimeEnd) / Interval into GUI fields.

        Notes
        -----
        - Widget-operation exceptions are intentionally swallowed (logged at DEBUG)
          to keep the UI responsive.

        """
        if ts and self.entry_start_date and self.entry_start_time:
            try:
                self.entry_start_date.delete(0, "end")
                self.entry_start_time.delete(0, "end")
                self.entry_start_date.insert(0, ts.strftime("%Y/%m/%d"))
                self.entry_start_time.insert(0, ts.strftime("%H:%M:%S"))
                self.progress_start_dt = ts
            except Exception as e:
                logger.debug("update_time_start_end(ts): %r", e)

        if te and self.entry_end_date and self.entry_end_time:
            try:
                self.entry_end_date.delete(0, "end")
                self.entry_end_time.delete(0, "end")
                self.entry_end_date.insert(0, te.strftime("%Y/%m/%d"))
                self.entry_end_time.insert(0, te.strftime("%H:%M:%S"))
                self.progress_end_dt = te
            except Exception as e:
                logger.debug("update_time_start_end(te): %r", e)

        if interval and self.combo_interval:
            try:
                self.combo_interval.set(str(int(interval)))
            except Exception as e:
                # Keep the original value on failure.
                logger.debug("update_time_start_end(interval): %r", e)
