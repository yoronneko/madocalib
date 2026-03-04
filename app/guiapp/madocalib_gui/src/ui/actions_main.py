# Copyright (C) 2026 Cabinet Office, Japan, All rights reserved.
# Copyright (C) 2026 Lighthouse Technology & Consulting Co. Ltd., All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause
"""File dialog helpers for RINEX/L6/Solution paths and L6 pattern extraction.

Some helpers also propagate selections into the GUI fields.

Notes
-----
- Reports user-facing errors via the UI event bus ('message').
- Some helpers mutate Tk widgets and `VariablesMain` fields (side effects).

"""
import logging
import subprocess
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog

from core.runtime import get_rtkplot_path, get_settings, save_settings
from glue.execute_api import execute
from ui.eventbus import post
from ui.ui_helpers import set_entry_value
from ui.view_options import option_window_views
from ui.widgets import open_calendar_dialog
from utils.l6_patterns import find_l6d_patterns, find_l6e_patterns
from utils.rinex import parse_rinex_obs

logger = logging.getLogger(__name__)


def on_click_plot(main_window, variables_main, cooldown_ms: int = 800) -> None:
    """Start rtkplot.exe with the selected solution file."""

    def plot_window_views(main_window, variables_main) -> None:
        """Start the external plot viewer with the selected solution file.

        - Allows multiple instances (no guard).
        - Returns immediately so queued clicks do not re-trigger after close.
        """
        solpath = _compute_plot_path(variables_main)
        plot = get_rtkplot_path()
        if plot is None or not plot.exists():
            post(
                "message",
                level="error",
                text=f"No such {str(plot)}",
                clear_after=5000,
            )
            return

        exe = str(plot).replace("/", "\\")
        arg = str(solpath).replace("/", "\\")

        try:
            subprocess.Popen([exe, arg], shell=False)
            post("message", level="info", text="Starting rtkplot...", clear_after=1200)
        except Exception as e:
            logger.error("rtkplot failed: %s", e)
            post(
                "message",
                level="error",
                text=f"Failed to launch rtkplot: {e}",
                clear_after=6000,
            )

    if getattr(on_click_plot, "_cooling", False):
        return
    on_click_plot._cooling = True

    try:
        variables_main.btn_plot.configure(state="disabled", relief="sunken")

        plot_window_views(main_window, variables_main)
    finally:

        def _restore() -> None:
            variables_main.btn_plot.configure(state="normal", relief="raised")
            on_click_plot._cooling = False

        main_window.after(cooldown_ms, _restore)


def on_click_options(main_window, variables_main) -> None:
    """Open the Options dialog."""
    option_window_views(main_window, variables_main)


def on_click_execute(main_window, variables_main) -> None:
    """Trigger madocalib execution with validated parameters."""
    execute(main_window, variables_main)


def on_click_exit(main_window, variables_main) -> None:
    """Persist settings and close the main window."""
    gui_to_settings(variables_main)
    save_settings()
    main_window.destroy()


def on_click_file_rinex_obs(main_window, variables_main) -> None:
    """Ask user to pick an OBS file and propagate selection to the UI."""
    file = filedialog.askopenfilename(
        filetypes=[
            ("OBS files (*.obs *.rnx *.*O)", "*.obs *.rnx *.*O"),
            ("ALL files (*.*)", "*.*"),
        ]
    )
    if not file:
        return
    set_entry_value(variables_main.hcombo_file_rinex_obs, file)
    on_rinex_obs_text_changed(variables_main)


def on_click_file_rinex_nav(hcombo_file_rinex_nav) -> None:
    """Open a file dialog and set the NAV file path."""
    file = filedialog.askopenfilename(
        filetypes=[
            (
                "NAV files (*.nav *.rnx *.*G *.*L *.*N *.*Q)",
                "*.nav *.rnx *.*G *.*L *.*N *.*Q",
            ),
            ("ALL files (*.*)", "*.*"),
        ]
    )
    if not file:
        return
    set_entry_value(hcombo_file_rinex_nav, file)


def on_click_l6e_folder(main_window, variables_main) -> None:
    """Open a folder dialog for L6E data, set the path, and refresh L6E patterns."""
    folder = filedialog.askdirectory(
        title="Please select a folder containing L6 files."
    )
    if not folder:
        return
    set_entry_value(variables_main.hcombo_folder_l6e, folder)
    on_l6e_folder_text_changed(variables_main)


def on_click_l6d_folder(main_window, variables_main) -> None:
    """Open a folder dialog for L6D data, set the path, and refresh L6D patterns."""
    folder = filedialog.askdirectory(
        title="Please select a folder containing L6 files."
    )
    if not folder:
        return
    set_entry_value(variables_main.hcombo_folder_l6d, folder)
    on_l6d_folder_text_changed(variables_main)


def on_click_file_solution(hcombo_file_solution) -> None:
    """Open a save-as dialog and set the solution file path."""
    file = filedialog.askopenfilename(filetypes=[("ALL files (*.*)", "*.*")])
    if not file:
        return
    set_entry_value(hcombo_file_solution, file)


def on_click_folder_solution(hcombo_folder_solution) -> None:
    """Open a folder dialog and set the solution folder path."""
    folder = filedialog.askdirectory()
    if not folder:
        return
    set_entry_value(hcombo_folder_solution, folder)


def on_click_toggle_dir_mode(variables_main) -> None:
    """Toggle between file and folder solution modes.

    Only overwrite the solution path if the current value looks auto-generated.
    """
    rnx_obs = variables_main.hcombo_file_rinex_obs.get()
    dir_enabled = variables_main.ivar_folder_solution_enabled.get() == 1
    try:
        variables_main.hcombo_folder_solution.config(
            state="normal" if dir_enabled else "disabled"
        )
    except Exception:
        pass

    # Compute auto-suggested path from OBS + mode
    new_suggest = _compute_solution_path(rnx_obs, dir_enabled)
    current = (variables_main.hcombo_file_solution.get() or "").strip()
    # Overwrite only when the field is empty (never overwrite once populated).
    if not current:
        set_entry_value(variables_main.hcombo_file_solution, new_suggest)

    # Folder auto-suggest when Dir is ON
    if dir_enabled:
        obs_parent = Path(rnx_obs).parent.as_posix() if rnx_obs else ""
        current_folder = (variables_main.hcombo_folder_solution.get() or "").strip()
        # Overwrite only when folder is empty (never overwrite once populated).
        if not current_folder and obs_parent:
            set_entry_value(variables_main.hcombo_folder_solution, obs_parent)

    # Normalize paths on toggle
    file_now = (variables_main.hcombo_file_solution.get() or "").strip()
    folder_now = (variables_main.hcombo_folder_solution.get() or "").strip()

    if dir_enabled:
        # OFF -> ON : if File is a full path, split it into Folder + basename
        p = Path(file_now) if file_now else None
        if p and str(p.parent) not in ("", ".", "/") and p.name:
            # Always normalize at this moment regardless of existing Folder value
            set_entry_value(variables_main.hcombo_folder_solution, p.parent.as_posix())
            set_entry_value(variables_main.hcombo_file_solution, p.name)
    else:
        # ON -> OFF : if Folder + File are paired, join into a full path for File
        if folder_now and file_now:
            full = Path(folder_now) / Path(file_now).name
            set_entry_value(variables_main.hcombo_file_solution, full.as_posix())


def on_click_start_date(main_window, variables_main) -> None:
    """Open date picker and set the start date/time."""
    _open_calendar_ts(variables_main)


def on_click_end_date(main_window, variables_main) -> None:
    """Open date picker and set the end date/time."""
    _open_calendar_te(variables_main)


def on_rinex_obs_text_changed(variables_main) -> None:
    """Parse the selected OBS file."""
    rnx_obs = variables_main.hcombo_file_rinex_obs.get()
    if not rnx_obs or not Path(rnx_obs).exists():
        return
    summary = parse_rinex_obs(rnx_obs)
    if summary:
        variables_main.clear_time_start_end()
        variables_main.update_time_start_end(summary.ts, summary.te, summary.interval)
    else:
        logger.warning("RINEX parse error: %s", rnx_obs)
    _refresh_solution_from_obs_and_mode(variables_main)


def on_l6e_folder_text_changed(variables_main) -> None:
    """Scan selected L6E folder and cache detected patterns."""
    folder = (variables_main.hcombo_folder_l6e.get() or "").strip()
    if not folder:
        variables_main.patterns_sat_l6e = None
        return
    p = Path(folder)
    if not p.exists() or not p.is_dir():
        variables_main.patterns_sat_l6e = None
        return

    patterns = find_l6e_patterns(folder)
    variables_main.patterns_sat_l6e = patterns or None
    if not patterns:
        post(
            "message",
            level="error",
            text=(
                "No .l6 files found in the selected folder."
                " Please check and try again."
            ),
        )


def on_l6d_folder_text_changed(variables_main) -> None:
    """Scan selected L6D folder and cache detected patterns."""
    folder = (variables_main.hcombo_folder_l6d.get() or "").strip()
    if not folder:
        variables_main.patterns_sat_l6d = None
        return
    p = Path(folder)
    if not p.exists() or not p.is_dir():
        variables_main.patterns_sat_l6d = None
        return
    patterns = find_l6d_patterns(folder)
    variables_main.patterns_sat_l6d = patterns or None
    if not patterns:
        post(
            "message",
            level="error",
            text=(
                "No .l6 files found in the selected folder."
                " Please check and try again."
            ),
        )


def _refresh_solution_from_obs_and_mode(variables_main) -> None:
    """Recompute solution path from OBS + Dir mode, but keep user manual edits."""
    rnx_obs = variables_main.hcombo_file_rinex_obs.get()
    dir_mode = bool(variables_main.ivar_folder_solution_enabled.get() == 1)
    try:
        variables_main.hcombo_folder_solution.config(
            state="normal" if dir_mode else "disabled"
        )
    except Exception:
        pass

    new_suggest = _compute_solution_path(rnx_obs, dir_mode)
    current = (variables_main.hcombo_file_solution.get() or "").strip()
    # Overwrite only when the field is empty (never overwrite once populated).
    if not current:
        set_entry_value(variables_main.hcombo_file_solution, new_suggest)

    # Folder auto-suggest when Dir is ON
    if dir_mode:
        obs_parent = Path(rnx_obs).parent.as_posix() if rnx_obs else ""
        current_folder = (variables_main.hcombo_folder_solution.get() or "").strip()
        # Overwrite only when folder is empty (never overwrite once populated).
        if not current_folder and obs_parent:
            set_entry_value(variables_main.hcombo_folder_solution, obs_parent)


def _compute_solution_path(obs_path: str, dir_mode: bool) -> str:
    """Return the solution path derived from an OBS path and output mode.

    Args:
        obs_path (str): Path to a RINEX OBS file (string is used even if missing).
        dir_mode (bool): If True, return only `basename.pos`; otherwise return
            `<obs_dir>/basename.pos`.

    Returns:
        str: Computed solution path (or empty string if not resolvable).

    """
    obs_path = (obs_path or "").strip()
    if not obs_path:
        return ""

    p = Path(obs_path)
    stem = p.stem  # base name without extension(s)
    if not stem:
        return ""

    if dir_mode:
        # Only the file name; actual output directory is decided elsewhere (UI/adapter).
        return f"{stem}.pos"
    else:
        # Emit into the same folder as the OBS file.
        return (p.parent / f"{stem}.pos").as_posix()


def _compute_plot_path(variables_main) -> str:
    """Build a single solution-path string for plotting, respecting Dir mode."""
    from pathlib import Path

    try:
        dir_on = bool(variables_main.ivar_folder_solution_enabled.get() == 1)
    except Exception:
        dir_on = False
    file_val = (variables_main.hcombo_file_solution.get() or "").strip()
    folder_val = (variables_main.hcombo_folder_solution.get() or "").strip()

    p_file = Path(file_val) if file_val else None
    p_folder = Path(folder_val) if folder_val else None

    if dir_on:
        if p_folder and p_file and p_file.name:
            return str((p_folder / p_file.name).resolve())
        return str((p_file or Path("")).resolve())
    else:
        return str((p_file or Path("")).resolve())


def settings_to_gui(variables_main) -> None:
    """Populate GUI widgets from saved settings and initialize L6 patterns.

    Notes:
        On datetime parse failure, logs a warning and leaves cached progress
        times unset.

    """
    settings = get_settings()
    if settings is None:
        return

    set_entry_value(variables_main.entry_start_date, settings.options.start_date)
    set_entry_value(variables_main.entry_start_time, settings.options.start_time)
    set_entry_value(variables_main.entry_end_date, settings.options.end_date)
    set_entry_value(variables_main.entry_end_time, settings.options.end_time)
    set_entry_value(variables_main.combo_interval, settings.options.interval)
    set_entry_value(variables_main.combo_timespan, settings.options.timespan)
    set_entry_value(variables_main.combo_spanshift, settings.options.spanshift)

    set_entry_value(variables_main.hcombo_file_rinex_obs, settings.inputs.obs_path)
    set_entry_value(variables_main.hcombo_file_rinex_nav, settings.inputs.nav_path)
    set_entry_value(variables_main.hcombo_folder_l6e, settings.inputs.l6e_path)
    set_entry_value(variables_main.hcombo_folder_l6d, settings.inputs.l6d_path)

    variables_main.ivar_folder_solution_enabled.set(
        settings.output.enabled_solution_folder
    )
    set_entry_value(variables_main.hcombo_file_solution, settings.output.file_solution)

    # Allow editing 'folder_solution' even when the checkbox is off (temporary enable).
    variables_main.hcombo_folder_solution.config(state=tk.NORMAL)
    set_entry_value(
        variables_main.hcombo_folder_solution, settings.output.folder_solution
    )
    if not variables_main.ivar_folder_solution_enabled.get():
        variables_main.hcombo_folder_solution.config(state=tk.DISABLED)


def gui_to_settings(variables_main) -> None:
    """Persist current GUI values to settings and update histories."""
    settings = get_settings()
    if settings is None:
        return

    settings.options.start_date = variables_main.entry_start_date.get()
    settings.options.start_time = variables_main.entry_start_time.get()
    settings.options.end_date = variables_main.entry_end_date.get()
    settings.options.end_time = variables_main.entry_end_time.get()
    settings.options.interval = variables_main.combo_interval.get()
    settings.options.timespan = variables_main.combo_timespan.get()
    settings.options.spanshift = variables_main.combo_spanshift.get()

    settings.inputs.obs_path = variables_main.hcombo_file_rinex_obs.get()
    settings.inputs.nav_path = variables_main.hcombo_file_rinex_nav.get()
    settings.inputs.l6e_path = variables_main.hcombo_folder_l6e.get()
    settings.inputs.l6d_path = variables_main.hcombo_folder_l6d.get()

    settings.output.enabled_solution_folder = (
        variables_main.ivar_folder_solution_enabled.get()
    )
    settings.output.file_solution = variables_main.hcombo_file_solution.get()
    settings.output.folder_solution = variables_main.hcombo_folder_solution.get()

    # Store histories.
    settings.history.obs_histories = variables_main.hcombo_file_rinex_obs.history
    variables_main.hcombo_file_rinex_obs._add_history(settings.inputs.obs_path)

    settings.history.nav_histories = variables_main.hcombo_file_rinex_nav.history
    variables_main.hcombo_file_rinex_nav._add_history(settings.inputs.nav_path)

    settings.history.l6e_histories = variables_main.hcombo_folder_l6e.history
    variables_main.hcombo_folder_l6e._add_history(settings.inputs.l6e_path)

    settings.history.l6d_histories = variables_main.hcombo_folder_l6d.history
    variables_main.hcombo_folder_l6d._add_history(settings.inputs.l6d_path)

    settings.history.solution_folder_histories = (
        variables_main.hcombo_folder_solution.history
    )
    variables_main.hcombo_folder_solution._add_history(settings.output.folder_solution)

    settings.history.solution_file_histories = (
        variables_main.hcombo_file_solution.history
    )
    variables_main.hcombo_file_solution._add_history(settings.output.file_solution)


def _open_calendar_ts(variables_main) -> None:
    """Open date picker and write start date with `00:00:00` time."""
    try:
        parent = (
            variables_main.entry_start_date.winfo_toplevel()
            if variables_main.entry_start_date
            else None
        )
    except Exception:
        parent = None

    def _on_selected(d: date) -> None:
        try:
            if variables_main.entry_start_date:
                variables_main.entry_start_date.delete(0, "end")
                variables_main.entry_start_date.insert(0, d.strftime("%Y/%m/%d"))
            if variables_main.entry_start_time:
                variables_main.entry_start_time.delete(0, "end")
                variables_main.entry_start_time.insert(0, "00:00:00")
        except Exception as e:
            logger.debug("_open_calendar_ts/on_selected failed: %r", e)

    try:
        if parent:
            open_calendar_dialog(parent, "Select Date (Start)", _on_selected)
    except Exception as e:
        logger.debug("_open_calendar_ts failed: %r", e)


def _open_calendar_te(variables_main) -> None:
    """Open date picker and write end date with `23:59:59` time."""
    try:
        parent = (
            variables_main.entry_end_date.winfo_toplevel()
            if variables_main.entry_end_date
            else None
        )
    except Exception:
        parent = None

    def _on_selected(d: date) -> None:
        try:
            if variables_main.entry_end_date:
                variables_main.entry_end_date.delete(0, "end")
                variables_main.entry_end_date.insert(0, d.strftime("%Y/%m/%d"))
            if variables_main.entry_end_time:
                variables_main.entry_end_time.delete(0, "end")
                variables_main.entry_end_time.insert(0, "23:59:59")
        except Exception as e:
            logger.debug("_open_calendar_te/on_selected failed: %r", e)

    try:
        if parent:
            open_calendar_dialog(parent, "Select Date (End)", _on_selected)
    except Exception as e:
        logger.debug("_open_calendar_te failed: %r", e)
