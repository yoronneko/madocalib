# Copyright (C) 2026 Cabinet Office, Japan, All rights reserved.
# Copyright (C) 2026 Lighthouse Technology & Consulting Co. Ltd., All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause
"""Main window UI for the madocalib GUI.

Builds the main Tk window, wires handlers and the event bus,
and binds widgets to VariablesMain.

"""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from core.runtime import get_conf_path, get_settings, supports_unicode
from ui.actions_main import (
    on_click_end_date,
    on_click_execute,
    on_click_exit,
    on_click_file_rinex_nav,
    on_click_file_rinex_obs,
    on_click_file_solution,
    on_click_folder_solution,
    on_click_l6d_folder,
    on_click_l6e_folder,
    on_click_options,
    on_click_plot,
    on_click_start_date,
    on_click_toggle_dir_mode,
    on_l6d_folder_text_changed,
    on_l6e_folder_text_changed,
    on_rinex_obs_text_changed,
    settings_to_gui,
)
from ui.eventbus import subscribe

# View-model for the main view
from ui.variables_main import VariablesMain

# New modularized imports
from ui.widgets import HistoryCombobox, StatusBar, TooltipBehavior

logger = logging.getLogger(__name__)


def views(main_window) -> None:
    """Build the main window and wire all event handlers.

    Args:
        main_window: Root window.

    Notes:
        Preserves legacy geometry, injects status bar, and registers
        event-bus subscribers.

    """
    # Frames
    frame_datetime = tk.Frame(main_window, width=610, height=60, bd=2)
    frame_input_files = tk.Frame(main_window, width=610, height=285, bd=2)
    frame_output_files = tk.Frame(main_window, width=610, height=60, bd=2)
    frame_actions = tk.Frame(main_window, width=610, height=50, bd=2)
    frame_status_bar = tk.Frame(
        main_window, width=610, height=100, relief=tk.SUNKEN, background="#E0E0E0"
    )

    variables_main = VariablesMain()

    # Labels
    label_time_start = tk.Label(frame_datetime, text="Time Start")
    label_time_end = tk.Label(frame_datetime, text="Time End")
    label_interval = tk.Label(frame_datetime, text="Interval(sec)")
    label_timespan = tk.Label(frame_datetime, text="Time Span(sec)")
    label_spanshift = tk.Label(frame_datetime, text="Span Shift(sec)")
    label_rinex_obs = tk.Label(frame_input_files, text="RINEX OBS file")
    label_rinex_nav = tk.Label(frame_input_files, text="RINEX NAV file")
    label_l6e_folder = tk.Label(frame_input_files, text="L6E data folder")
    label_l6d_folder = tk.Label(frame_input_files, text="L6D data folder")
    label_solution = tk.Label(frame_output_files, text="Solution")

    status = StatusBar(frame_status_bar)
    status.place()

    # Separator
    separator1 = ttk.Separator(frame_status_bar, orient="horizontal")

    # Time Start/End
    # Use the calendar glyph when `supports_unicode` returns True.
    cal_text = "🗓" if supports_unicode("🗓") else "c"
    variables_main.btn_start_date = ttk.Button(
        frame_datetime,
        text=cal_text,
        padding=(0, -10),
        command=lambda: on_click_start_date(main_window, variables_main),
    )
    variables_main.btn_end_date = ttk.Button(
        frame_datetime,
        text=cal_text,
        padding=(0, -10),
        command=lambda: on_click_end_date(main_window, variables_main),
    )
    variables_main.entry_start_date = tk.Entry(frame_datetime, width=10)
    variables_main.entry_start_time = tk.Entry(frame_datetime, width=8)
    variables_main.entry_end_date = tk.Entry(frame_datetime, width=10)
    variables_main.entry_end_time = tk.Entry(frame_datetime, width=8)
    intervals = ["", "1", "5", "10", "30", "60", "300", "600"]
    variables_main.combo_interval = ttk.Combobox(
        frame_datetime, values=intervals, width=10
    )
    intervals = ["", "300", "600", "900", "1800", "3600"]
    variables_main.combo_timespan = ttk.Combobox(
        frame_datetime, values=intervals, width=10
    )
    intervals = ["", "150", "300", "450", "900", "1800"]
    variables_main.combo_spanshift = ttk.Combobox(
        frame_datetime, values=intervals, width=10
    )

    # Output Dir checkbox
    variables_main.ivar_folder_solution_enabled = tk.IntVar()

    # History-enabled Comboboxes for paths (with initial history from config)
    settings = get_settings()

    # OBS
    svar_obs_histories = tk.StringVar()
    hist = settings.history.obs_histories
    variables_main.hcombo_file_rinex_obs = HistoryCombobox(
        frame_input_files,
        textvariable=svar_obs_histories,
        max_history=10,
        width=82,
        history=hist,
    )
    variables_main.btn_file_rinex_obs = tk.Button(
        frame_input_files,
        text="...",
        bg="lightgray",
        command=lambda: on_click_file_rinex_obs(
            main_window,
            variables_main,
        ),
    )

    # NAV
    hist = settings.history.nav_histories
    variables_main.hcombo_file_rinex_nav = HistoryCombobox(
        frame_input_files, max_history=10, width=82, history=hist
    )
    variables_main.btn_file_rinex_nav = tk.Button(
        frame_input_files,
        text="...",
        bg="lightgray",
        command=lambda: on_click_file_rinex_nav(variables_main.hcombo_file_rinex_nav),
    )

    # L6E
    svar_l6e_histories = tk.StringVar()
    hist = settings.history.l6e_histories
    variables_main.hcombo_folder_l6e = HistoryCombobox(
        frame_input_files,
        textvariable=svar_l6e_histories,
        max_history=10,
        width=82,
        history=hist,
    )
    variables_main.btn_folder_l6e = tk.Button(
        frame_input_files,
        text="...",
        bg="lightgray",
        command=lambda: on_click_l6e_folder(main_window, variables_main),
    )

    # L6D
    svar_l6d_histories = tk.StringVar()
    hist = settings.history.l6d_histories
    variables_main.hcombo_folder_l6d = HistoryCombobox(
        frame_input_files,
        textvariable=svar_l6d_histories,
        max_history=10,
        width=82,
        history=hist,
    )
    variables_main.btn_folder_l6d = tk.Button(
        frame_input_files,
        text="...",
        bg="lightgray",
        command=lambda: on_click_l6d_folder(main_window, variables_main),
    )

    # Solution Folder
    variables_main.chk_output_dir_mode = tk.Checkbutton(
        frame_output_files,
        text="Dir",
        variable=variables_main.ivar_folder_solution_enabled,
        onvalue=1,
        offvalue=0,
        command=lambda: on_click_toggle_dir_mode(variables_main),
    )

    hist = settings.history.solution_folder_histories
    variables_main.hcombo_folder_solution = HistoryCombobox(
        frame_output_files, max_history=10, width=64, history=hist
    )
    variables_main.btn_folder_solution = tk.Button(
        frame_output_files,
        text="...",
        bg="lightgray",
        command=lambda: on_click_folder_solution(variables_main.hcombo_folder_solution),
    )  # out directory

    # Solution File
    hist = settings.history.solution_file_histories
    variables_main.hcombo_file_solution = HistoryCombobox(
        frame_output_files, max_history=10, width=82, history=hist
    )
    variables_main.btn_file_solution = tk.Button(
        frame_output_files,
        text="...",
        bg="lightgray",
        command=lambda: on_click_file_solution(variables_main.hcombo_file_solution),
    )

    # Actions
    variables_main.btn_plot = tk.Button(
        frame_actions,
        text="Plot",
        bg="lightgray",
        command=lambda: on_click_plot(main_window, variables_main),
    )
    variables_main.btn_options = tk.Button(
        frame_actions,
        text="Option",
        bg="lightgray",
        command=lambda: on_click_options(main_window, variables_main),
    )
    variables_main.btn_execute = tk.Button(
        frame_actions,
        text="Execute",
        bg="lightgray",
        command=lambda: on_click_execute(main_window, variables_main),
    )
    variables_main.btn_exit = tk.Button(
        frame_actions, text="Exit", bg="lightgray", command=main_window.quit
    )

    # Load setting values into GUI
    settings_to_gui(variables_main)

    # Wire: if RINEX path changes, update NAV/OUT etc (no dialog)
    svar_obs_histories.trace_add(
        "write",
        # Propagate OBS change to NAV/OUT without opening a file dialog.
        lambda *args: on_rinex_obs_text_changed(
            variables_main,
        ),
    )
    svar_l6e_histories.trace_add(
        "write",
        lambda *args: on_l6e_folder_text_changed(variables_main),
    )
    svar_l6d_histories.trace_add(
        "write",
        lambda *args: on_l6d_folder_text_changed(variables_main),
    )

    # Place widgets (keep legacy geometry)
    # Datetime
    label_time_start.place(x=20, y=5)
    variables_main.btn_start_date.place(x=85, y=5, width=20, height=20)
    variables_main.entry_start_date.place(x=20, y=25)
    variables_main.entry_start_time.place(x=85, y=25)

    label_time_end.place(x=145, y=5)
    variables_main.btn_end_date.place(x=210, y=5, width=20, height=20)
    variables_main.entry_end_date.place(x=145, y=25)
    variables_main.entry_end_time.place(x=210, y=25)

    label_interval.place(x=270, y=5)
    variables_main.combo_interval.place(x=270, y=25)
    label_timespan.place(x=360, y=5)
    variables_main.combo_timespan.place(x=360, y=25)
    label_spanshift.place(x=450, y=5)
    variables_main.combo_spanshift.place(x=450, y=25)

    # Input files
    label_rinex_obs.place(x=20, y=5)
    variables_main.hcombo_file_rinex_obs.place(x=20, y=25)
    variables_main.btn_file_rinex_obs.place(x=540, y=25, width=40, height=20)

    label_rinex_nav.place(x=20, y=50)
    variables_main.hcombo_file_rinex_nav.place(x=20, y=70)
    variables_main.btn_file_rinex_nav.place(x=540, y=70, width=40, height=20)

    label_l6e_folder.place(x=20, y=95)
    variables_main.hcombo_folder_l6e.place(x=20, y=115)
    variables_main.btn_folder_l6e.place(x=540, y=115, width=40, height=20)

    label_l6d_folder.place(x=20, y=140)
    variables_main.hcombo_folder_l6d.place(x=20, y=160)
    variables_main.btn_folder_l6d.place(x=540, y=160, width=40, height=20)

    # Output files
    label_solution.place(x=20, y=5)
    variables_main.chk_output_dir_mode.place(x=80, y=5)
    variables_main.hcombo_folder_solution.place(x=128, y=5)
    variables_main.btn_folder_solution.place(x=540, y=5, width=40, height=20)
    variables_main.hcombo_file_solution.place(x=20, y=30)
    variables_main.btn_file_solution.place(x=540, y=30, width=40, height=20)

    # Actions
    variables_main.btn_plot.place(x=20, y=5, width=130)
    variables_main.btn_options.place(x=165, y=5, width=130)
    variables_main.btn_execute.place(x=310, y=5, width=130)
    variables_main.btn_exit.place(x=455, y=5, width=130)

    # Frames
    frame_datetime.place(x=0, y=0)
    frame_input_files.place(x=0, y=55)
    frame_output_files.place(x=0, y=250)
    frame_actions.place(x=0, y=315)
    frame_status_bar.place(x=0, y=355)

    # Status bar widgets
    separator1.place(x=0, y=0, relwidth=1)

    # Window close -> persist config
    main_window.protocol(
        "WM_DELETE_WINDOW", lambda: on_click_exit(main_window, variables_main)
    )
    variables_main.btn_exit.configure(
        command=lambda: on_click_exit(main_window, variables_main)
    )

    # Tooltip on the Options button showing the conf path.
    _conf_cur = get_conf_path()
    _tooltip_text = _conf_cur if (_conf_cur and Path(_conf_cur).is_file()) else ""
    _tooltip_opt = TooltipBehavior(
        variables_main.btn_options, text=_tooltip_text, delay_ms=300
    )

    # Register event bus subscribers
    subscribe("set_progress", status.on_progress)
    subscribe("idle_progress", status.on_idle)
    subscribe("reset_progress", status.on_reset)

    def _on_message(payload: dict) -> None:
        level = (payload or {}).get("level", "info")
        text = (payload or {}).get("text", "")
        clear_after = (payload or {}).get("clear_after", 0)
        color = "red" if level == "error" else "black"
        status.set_text(text, color=color, clear_after=clear_after)

    subscribe("message", _on_message)

    def _on_set_tooltip_opt(payload: dict) -> None:
        txt = (payload or {}).get("text", "")
        try:
            _tooltip_opt.text = txt if (txt and Path(txt).is_file()) else ""
        except Exception:
            _tooltip_opt.text = ""

    subscribe("set_tooltip_opt", _on_set_tooltip_opt)

    # Lock helpers (used by async executor)
    variables_main.lock_targets = [
        variables_main.hcombo_file_rinex_obs,
        variables_main.hcombo_file_rinex_nav,
        variables_main.hcombo_folder_l6e,
        variables_main.hcombo_folder_l6d,
        variables_main.hcombo_folder_solution,
        variables_main.hcombo_file_solution,
        variables_main.entry_start_date,
        variables_main.entry_start_time,
        variables_main.entry_end_date,
        variables_main.entry_end_time,
        variables_main.combo_interval,
        variables_main.combo_timespan,
        variables_main.combo_spanshift,
        variables_main.chk_output_dir_mode,
        variables_main.btn_file_rinex_obs,
        variables_main.btn_file_rinex_nav,
        variables_main.btn_folder_l6d,
        variables_main.btn_file_solution,
        variables_main.btn_folder_solution,
        variables_main.btn_plot,
        variables_main.btn_options,
        variables_main.btn_execute,
        variables_main.btn_exit,
        variables_main.btn_folder_l6e,
        variables_main.btn_start_date,
        variables_main.btn_end_date,
        variables_main.btn_file_solution,
    ]
    is_locked = {"value": False}

    def _apply_waiting_dir_mode_enables() -> None:
        try:
            dir_on = variables_main.ivar_folder_solution_enabled.get() == 1
        except Exception:
            dir_on = False

        try:
            if dir_on:
                variables_main.hcombo_folder_solution.configure(state="normal")
                variables_main.btn_folder_solution.configure(state="normal")
                variables_main.hcombo_file_solution.configure(state="normal")
                variables_main.btn_file_solution.configure(state="normal")
            else:
                variables_main.hcombo_folder_solution.configure(state="disabled")
                variables_main.btn_folder_solution.configure(state="disabled")
                variables_main.hcombo_file_solution.configure(state="normal")
                variables_main.btn_file_solution.configure(state="normal")
        except Exception:
            pass

    def _apply_lock(lock: bool) -> None:
        targets = set(variables_main.lock_targets)
        for w in targets:
            try:
                w.configure(state="disabled" if lock else "normal")
            except Exception:
                pass

    def _on_ui_lock(_payload=None) -> None:
        def _do() -> None:
            is_locked["value"] = True
            _apply_lock(lock=True)

        main_window.after(0, _do)

    def _on_ui_unlock(_payload=None) -> None:
        def _do() -> None:
            is_locked["value"] = False
            _apply_lock(lock=False)
            _apply_waiting_dir_mode_enables()

        main_window.after(0, _do)

    subscribe("ui_lock", _on_ui_lock)
    subscribe("ui_unlock", _on_ui_unlock)
