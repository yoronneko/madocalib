# Copyright (C) 2026 Cabinet Office, Japan, All rights reserved.
# Copyright (C) 2026 Lighthouse Technology & Consulting Co. Ltd., All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause
"""Reusable UI widgets.

This module provides a small set of reusable, testable UI components:
- `StatusBar`: Status message label with an optional progress bar and
  event-bus friendly handler methods.
- `HistoryCombobox`: `ttk.Combobox` with in-memory history and optional
  TkinterDnD2 file-drop support.
- `TooltipManager` / `TooltipBehavior`: A singleton tooltip window manager
  and a behavior helper to attach tooltips to any widget.
- `CustomCalendar`: Lightweight calendar view for picking a date.
- `open_calendar_dialog`: Convenience function to open a non-blocking
  date-picker dialog.
"""

from __future__ import annotations

import calendar
import logging
import tkinter as tk
from datetime import date, datetime
from tkinter import ttk
from typing import List

try:
    from tkinterdnd2 import DND_FILES
except Exception:
    DND_FILES = None

from core.runtime import set_window_icon

logger = logging.getLogger(__name__)


class StatusBar:
    """Status bar widget (message + progress) without module-level globals.

    Notes:
        Provides handler methods that can be subscribed to the event bus:
        - `on_progress(payload)`
        - `on_idle(payload)`
        - `on_reset(payload)`

    """

    def __init__(self, parent) -> None:
        """Initialize label/progress widgets and internal state.

        Args:
            parent: Parent container (Frame) to host the status bar.

        """
        self.svar_message = tk.StringVar(value="Ready")
        self.label = tk.Label(
            parent, textvariable=self.svar_message, anchor="w", background="#E0E0E0"
        )
        self.progress = ttk.Progressbar(
            parent, orient="horizontal", mode="determinate", length=100, maximum=100
        )
        self._last_percent = 0
        self._indeterminate = False
        self._clear_after_id = None

    def place(self) -> None:
        """Place the status label; progress bar is placed lazily when needed."""
        self.label.place(x=10, y=10)

    def set_text(
        self, text: str, color: str = "black", clear_after: int | None = None
    ) -> None:
        """Set status message and color; optionally clear after a delay.

        Args:
            text (str): Message to display.
            color (str): Label foreground color.
            clear_after (int | None): Milliseconds to auto-clear; `None` to keep.

        """
        self.label.configure(foreground=color)
        self.svar_message.set(text or "")

        if self._clear_after_id:
            try:
                self.label.after_cancel(self._clear_after_id)
            except Exception:
                pass
            self._clear_after_id = None

        if clear_after and int(clear_after) > 0:

            def _clear() -> None:
                self.label.configure(foreground="black")
                self.on_idle({"text": "Ready"})
                self._clear_after_id = None

            self._clear_after_id = self.label.after(int(clear_after), _clear)

    def on_progress(self, payload: dict) -> None:
        """Update progress bar from an event-bus payload.

        Args:
            payload (dict): May include `percent` (int|None) and `text` (str).

        Notes:
            If `percent` is `None`, the bar runs in indeterminate mode.

        """
        percent = (payload or {}).get("percent")
        text = (payload or {}).get("text")
        self.label.configure(foreground="black")
        if percent is None:
            if not self._indeterminate:
                self.progress.config(mode="indeterminate")
                self._indeterminate = True
            self.progress.place(x=500, y=10)
            try:
                self.progress.start(30)
            except Exception as e:
                logger.debug("progress.start failed: %r", e)
            self.svar_message.set(text or "")
        else:
            p = max(0, min(100, int(percent)))
            self._last_percent = p
            if self._indeterminate:
                try:
                    self.progress.stop()
                except Exception as e:
                    logger.debug("progress.stop failed: %r", e)
                self.progress.config(mode="determinate")
                self._indeterminate = False
            self.progress.place(x=500, y=10)
            self.progress["value"] = p
            if text is not None:
                self.svar_message.set(text)

    def on_idle(self, payload: dict) -> None:
        """Stop spinner and keep the last determinate percentage.

        Args:
            payload (dict): Optional `text` to set.

        """
        try:
            self.progress.stop()
        except Exception as e:
            logger.debug("progress.stop failed: %r", e)
        self.progress.config(mode="determinate")
        self.progress["value"] = self._last_percent
        if payload and payload.get("text"):
            self.svar_message.set(payload["text"])

    def on_reset(self, payload=None) -> None:
        """Reset the progress bar and clear the status message."""
        try:
            self.progress.stop()
        except Exception as e:
            logger.debug("progress.stop failed: %r", e)
        self.progress["value"] = 0
        try:
            self.progress.place_forget()
        except Exception as e:
            logger.debug("progress.place_forget failed: %r", e)
        self.svar_message.set("")


class HistoryCombobox(ttk.Combobox):
    """Combobox with a small in-memory history and optional file-drop.

    Attributes:
        history (list[str]): Recent entries, capped by `max_history`.
        max_history (int): Maximum number of history items.

    Notes:
        If TkinterDnD2 is present, accepts `DND_FILES` (Windows path list) drops.

    """

    history: List[str]

    def __init__(self, master, **kw) -> None:
        """Create a history-enabled Combobox.

        Args:
            master: Parent widget.
            **kw: Supports `max_history` (int) and `history` (list[str]).

        """
        self.max_history = int(kw.pop("max_history", 10))
        self.history = list(kw.pop("history", []))[: self.max_history]
        # Respect external textvariable if provided
        tv = kw.pop("textvariable", None)
        super().__init__(master, values=self.history, textvariable=tv, **kw)
        # Keep a handle (external or internal)
        if tv is None:
            self.svar_text = tk.StringVar(master)
            self.configure(textvariable=self.svar_text)
        else:
            self.svar_text = tv
        self.svar_text.trace_add("write", self._on_value_changed)
        self.bind("<Return>", self._add_history, add="+")
        self.bind("<FocusOut>", self._add_history, add="+")
        self.bind("<<ComboboxSelected>>", self._add_history, add="+")

        # --- Drag & Drop registration (TkinterDnD2) ---
        try:
            if DND_FILES:
                self.drop_target_register(DND_FILES)
                self.dnd_bind("<<Drop>>", self._on_drop)
        except Exception as e:
            logger.debug("DnD registration failed on HistoryCombobox: %r", e)

    def _on_value_changed(self, *_) -> None:
        # Hook for subclasses if needed
        pass

    def set(self, value) -> None:
        """Set current text and push it into the history."""
        self.svar_text.set(value)
        self._push_history(value)

    def get(self) -> str:
        """Return current text of the Combobox."""
        return self.svar_text.get()

    def _add_history(self, event=None) -> None:
        """Push current text into the history (bound to Enter/FocusOut)."""
        self._push_history(self.svar_text.get())

    def _push_history(self, text: str) -> None:
        """Insert `text` at history head, de-duplicating and trimming size."""
        text = (text or "").strip()
        if not text:
            return
        if text in self.history:
            self.history.remove(text)
        self.history.insert(0, text)
        if len(self.history) > self.max_history:
            self.history = self.history[: self.max_history]
        self["values"] = self.history

    def _on_drop(self, event) -> None:
        """Handle `DND_FILES` drop (brace-aware Windows path list) and set value.

        Args:
            event: TkinterDnD2 drop event whose `data` contains the path list.

        """
        data = (event.data or "").strip()
        if not data:
            return
        paths, buf, brace = [], "", False
        for ch in data:
            if ch == "{":
                brace = True
                buf = ""
            elif ch == "}":
                brace = False
                paths.append(buf)
                buf = ""
            elif ch == " " and not brace:
                if buf:
                    paths.append(buf)
                    buf = ""
            else:
                buf += ch
        if buf:
            paths.append(buf)
        if paths:
            self.set(paths[0])


class TooltipManager:
    """Manage a single tooltip window per root.

    Notes:
        Use `TooltipManager.get(root)` to obtain the singleton instance.

    """

    _instance = None

    def __init__(self, root) -> None:
        """Create a manager bound to a specific Tk root."""
        self.root = root
        self.tip = None
        self.label = None
        self.after_id = None
        self.current_widget = None
        self.pad = (12, 8)  # offset from mouse (x, y)
        self.margin = 8  # screen edge margin
        self.max_width = 360  # wraplength

    @classmethod
    def get(cls, root) -> TooltipManager:
        """Return a singleton instance associated with `root`."""
        if not cls._instance:
            cls._instance = cls(root)
        return cls._instance

    def _ensure_toplevel(self) -> None:
        """Create the top-level tooltip window on first use."""
        if self.tip is None:
            self.tip = tk.Toplevel(self.root)
            self.tip.overrideredirect(True)
            try:
                self.tip.attributes("-topmost", True)
            except Exception as e:
                logger.debug("tooltip topmost attr failed: %r", e)
            self.label = tk.Label(
                self.tip,
                text="",
                bg="#111111",
                fg="#ffffff",
                padx=8,
                pady=6,
                wraplength=self.max_width,
                relief="solid",
                borderwidth=1,
            )

    def show_after(
        self, widget, text, mouse_pos=None, delay_ms=400, placement="auto"
    ) -> None:
        """Schedule tooltip to appear after `delay_ms` for `widget`.

        Args:
            widget: Anchor widget.
            text (str): Tooltip content.
            mouse_pos (tuple[int, int] | None): Optional pointer position.
            delay_ms (int): Delay before showing.
            placement (str): "auto", "right", or "below".

        """
        # Cancel any pending show to avoid duplicated scheduling/flicker
        self.cancel()
        self.current_widget = widget

        def _show() -> None:
            if not widget.winfo_exists():
                return
            self._ensure_toplevel()
            self.label.config(text=text)
            self.label.pack_forget()
            self.label.pack()
            x, y = self._calc_position(widget, mouse_pos, placement)
            self.tip.geometry(f"+{x}+{y}")
            self.tip.deiconify()

        self.after_id = self.root.after(delay_ms, _show)

    def update_position(self, widget, mouse_pos, placement="auto") -> None:
        """Update tooltip position while visible."""
        if self.tip and self.tip.winfo_viewable():
            x, y = self._calc_position(widget, mouse_pos, placement)
            self.tip.geometry(f"+{x}+{y}")

    def hide(self) -> None:
        """Hide the tooltip window if it is visible."""
        self.cancel()
        if self.tip is not None:
            self.tip.withdraw()

    def cancel(self) -> None:
        """Cancel any pending show; does not hide an already visible tooltip."""
        if self.after_id:
            try:
                self.root.after_cancel(self.after_id)
            except Exception as e:
                logger.debug("after_cancel failed: %r", e)
            self.after_id = None

    def _calc_position(
        self, widget, mouse_pos=None, placement="auto"
    ) -> tuple[int, int]:
        """Compute on-screen (x, y) for the tooltip near `widget`.

        Args:
            widget: Anchor widget.
            mouse_pos (tuple[int, int] | None): Pointer position hint.
            placement (str): "auto", "right", or "below".

        Returns:
            tuple[int, int]: Screen coordinates for the tooltip.

        """
        if mouse_pos:
            base_x, base_y = mouse_pos
        else:
            bx = widget.winfo_rootx()
            by = widget.winfo_rooty()
            base_x = bx + widget.winfo_width() // 2
            base_y = by + widget.winfo_height()
        x = base_x + self.pad[0]
        y = base_y + self.pad[1]
        self.tip.update_idletasks()
        tw = self.tip.winfo_width()
        th = self.tip.winfo_height()
        sw = widget.winfo_screenwidth()
        sh = widget.winfo_screenheight()
        if x + tw + self.margin > sw:
            x = max(self.margin, sw - tw - self.margin)
        if y + th + self.margin > sh:
            y = max(self.margin, base_y - th - self.pad[1])
        return x, y


class TooltipBehavior:
    """Attach a tooltip behavior to a widget using `TooltipManager`.

    Args:
        widget: Target widget.
        text (str): Tooltip text (mutable).
        delay_ms (int): Delay before showing the tooltip.
        placement (str): Tooltip placement. "auto" by default.

    """

    def __init__(self, widget, text="", delay_ms=400, placement="auto") -> None:
        """Initialize a tooltip behavior for the given widget."""
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.placement = placement
        self.manager = TooltipManager.get(widget.winfo_toplevel())

        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<Motion>", self._on_motion, add="+")
        widget.bind("<FocusIn>", self._on_focus_in, add="+")
        widget.bind("<FocusOut>", self._on_focus_out, add="+")
        widget.bind("<Destroy>", self._on_destroy, add="+")

    def _on_enter(self, e) -> None:
        """Pointer enters the widget: schedule a tooltip show."""
        pos = (e.x_root, e.y_root)
        self.manager.show_after(
            self.widget,
            self.text,
            mouse_pos=pos,
            delay_ms=self.delay_ms,
            placement=self.placement,
        )

    def _on_motion(self, e) -> None:
        """Pointer moves within the widget: update tooltip position."""
        pos = (e.x_root, e.y_root)
        self.manager.update_position(self.widget, pos, placement=self.placement)

    def _on_leave(self, e) -> None:
        """Pointer leaves the widget: hide tooltip immediately."""
        self.manager.hide()

    def _on_focus_in(self, e) -> None:
        """Widget receives keyboard focus: schedule a tooltip show."""
        self.manager.show_after(
            self.widget,
            self.text,
            mouse_pos=None,
            delay_ms=self.delay_ms,
            placement=self.placement,
        )

    def _on_focus_out(self, e) -> None:
        """Widget loses keyboard focus: hide tooltip."""
        self.manager.hide()

    def _on_destroy(self, e) -> None:
        """Widget is being destroyed: cancel any pending show."""
        self.manager.cancel()


class CustomCalendar(ttk.Frame):
    """A lightweight, self-contained calendar widget for date selection.

    Args:
        master: Parent widget.
        date_pattern: Date format pattern using tokens `yyyy`, `mm`, `dd`
            (e.g., `"yyyy/mm/dd"`). Internally converted to `strftime`.
        selectmode: Selection mode (currently `"day"` is supported).
        firstweekday: `"sunday"` or `"monday"` to control the calendar layout.
        on_select: Optional callback receiving the selected `date` on user pick.
        initial_date: Optional initial date (`datetime.date` or
            a string matching `date_pattern`). Defaults to today.

    Notes:
        - The widget displays a 6x7 grid (weeks x weekdays) plus header/nav.
        - Uses custom styles: `"Selected.TButton"` and `"Today.TButton"` if
          provided by the hosting application theme.

    """

    def __init__(
        self,
        master=None,
        date_pattern="yyyy/mm/dd",
        selectmode="day",
        firstweekday="sunday",
        on_select=None,
        initial_date=None,
    ) -> None:
        """Initialize the calendar widget and prepare layout and state."""
        super().__init__(master)
        self.master = master
        self.date_pattern = date_pattern
        self.selectmode = selectmode
        self.on_select = on_select
        self.firstweekday = 6 if firstweekday == "sunday" else 0  # 6=Sun, 0=Mon

        def _to_strftime(pattern: str) -> str:
            return pattern.replace("yyyy", "%Y").replace("mm", "%m").replace("dd", "%d")

        today = date.today()
        dt = None
        if initial_date is None:
            dt = today
        elif isinstance(initial_date, date):
            dt = initial_date
        elif isinstance(initial_date, str):
            try:

                dt = datetime.strptime(
                    initial_date, _to_strftime(self.date_pattern)
                ).date()
            except Exception:
                dt = today
        else:
            dt = today

        self.year = dt.year
        self.month = dt.month
        self.selected_date = dt

        # Header / Nav / Grid
        self._build_header()
        self._build_nav()
        self._build_calendar()

        self._sync_header_labels()
        self._update_calendar()

    # Header UI (year & month spinbox)
    def _build_header(self) -> None:
        """Create the header area showing current year and month."""
        header = ttk.Frame(self)
        header.pack(pady=5)

        ttk.Label(header, text="Year:").pack(side="left", padx=(0, 4))
        self.year_label_var = tk.StringVar(value=str(self.year))
        self.year_label = ttk.Label(header, textvariable=self.year_label_var, width=6)
        self.year_label.pack(side="left", padx=(0, 20))

        ttk.Label(header, text="Month:").pack(side="left", padx=(0, 4))
        self.month_label_var = tk.StringVar(value=str(self.month))
        self.month_label = ttk.Label(header, textvariable=self.month_label_var, width=4)

        self.month_label.pack(side="left")

    # Navigation Buttons
    def _build_nav(self) -> None:
        """Create navigation buttons for month/year traversal and today."""
        nav = ttk.Frame(self)
        nav.pack()

        ttk.Button(nav, text="<<", width=4, command=self._prev_year).pack(side="left")
        ttk.Button(nav, text="<", width=4, command=self._prev_month).pack(side="left")

        ttk.Button(nav, text="Today", width=8, command=self._on_today).pack(side="left")

        ttk.Button(nav, text=">", width=4, command=self._next_month).pack(side="left")
        ttk.Button(nav, text=">>", width=4, command=self._next_year).pack(side="left")

    def _prev_month(self) -> None:
        """Navigate to the previous month (clamped at year >= 1900)."""
        self.month -= 1
        if self.month < 1:
            if self.year > 1900:
                self.month = 12
                self.year -= 1
            else:
                self.month = 1
        self._sync_header_labels()
        self._update_calendar()

    def _next_month(self) -> None:
        """Navigate to the next month (clamped at year <= 2100)."""
        self.month += 1
        if self.month > 12:
            if self.year < 2100:
                self.month = 1
                self.year += 1
            else:
                self.month = 12
        self._sync_header_labels()
        self._update_calendar()

    def _prev_year(self) -> None:
        """Navigate to the previous year (>= 1900)."""
        if self.year > 1900:
            self.year -= 1
        self._sync_header_labels()
        self._update_calendar()

    def _next_year(self) -> None:
        """Navigate to the next year (<= 2100)."""
        if self.year < 2100:
            self.year += 1
        self._sync_header_labels()
        self._update_calendar()

    def _sync_header_labels(self) -> None:
        """Refresh the year/month labels to reflect the current state."""
        self.year_label_var.set(str(self.year))
        self.month_label_var.set(str(self.month))

    def _on_today(self) -> None:
        """Jump to today and trigger selection callback if provided."""
        today = date.today()
        self.year, self.month = today.year, today.month
        self.selected_date = today
        self._sync_header_labels()
        self._update_calendar()

        if callable(self.on_select):
            self.on_select(self.selected_date)

    # CustomCalendar grid
    def _build_calendar(self) -> None:
        """Create the 6x7 day button grid and weekday headers."""
        self.grid_frame = ttk.Frame(self)
        self.grid_frame.pack(pady=5)

        days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        for i, day in enumerate(days):
            ttk.Label(self.grid_frame, text=day, padding=4).grid(row=0, column=i)

        self.day_btns = []
        for r in range(6):
            row_btns = []
            r_disp = r + 1
            for c in range(7):
                btn = ttk.Button(
                    self.grid_frame,
                    text="",
                    width=4,
                    command=lambda r=r, c=c: self._on_date_click(r, c),
                )
                btn.grid(row=r_disp, column=c, padx=1, pady=1)
                btn.date_value = None
                row_btns.append(btn)
            self.day_btns.append(row_btns)

    # Update calendar UI
    def _update_calendar(self) -> None:
        """Populate the day grid for the current `year` and `month`.

        Notes:
            - Days outside the current month are disabled and shown blank.
            - The selected date uses style `Selected.TButton` if available.
            - Today's date uses style `Today.TButton` if available.

        """
        cal = calendar.Calendar(self.firstweekday)
        weeks = cal.monthdatescalendar(self.year, self.month)

        today = date.today()

        for r in range(6):
            for c in range(7):
                btn = self.day_btns[r][c]

                if r >= len(weeks):
                    btn.config(text="", state="disabled", style="TButton")
                    btn.date_value = None
                    continue

                d = weeks[r][c]
                btn.date_value = d

                if d.month != self.month:
                    btn.config(text="", state="disabled", style="TButton")
                else:
                    btn.config(text=str(d.day), state="normal")

                    if d == self.selected_date:
                        btn.config(style="Selected.TButton")
                    elif d == today:
                        btn.config(style="Today.TButton")
                    else:
                        btn.config(style="TButton")

    # Click handler
    def _on_date_click(self, r, c) -> None:
        """Handle user click on a date button.

        Args:
            r: Row index in the 6x7 grid.
            c: Column index in the 6x7 grid.

        Notes:
            Ignores clicks on disabled/out-of-month cells. On valid selection,
            updates `selected_date`, refreshes the grid, and invokes `on_select`.

        """
        btn = self.day_btns[r][c]
        if not getattr(btn, "date_value", None):
            return
        d = btn.date_value
        if d.month != self.month:
            return

        self.selected_date = d
        self._update_calendar()

        if callable(self.on_select):
            self.on_select(self.selected_date)


def open_calendar_dialog(parent, title: str, on_selected) -> tk.Toplevel:
    """Open a simple calendar dialog and call `on_selected(date)` on pick.

    Args:
        parent: Parent window for the dialog.
        title: Dialog caption text.
        on_selected: Callable receiving a single `datetime.date`.

    Returns:
        tkinter.Toplevel: The created top-level dialog window.

    Notes:
        - Non-blocking: returns immediately after creating the dialog.
        - The dialog grabs focus (`grab_set`) so that selection behaves
          like a modal, but it can be dismissed programmatically after
          a date is picked.

    """
    win = tk.Toplevel(parent)
    win.withdraw()
    win.title(title)
    set_window_icon(win)
    win.transient(parent)
    win.grab_set()
    win.focus_set()

    def _commit(d: date) -> None:
        """Invoke the external callback and close the dialog."""
        try:
            on_selected(d)
        finally:
            win.destroy()

    # calendar body
    cal = CustomCalendar(
        win,
        selectmode="day",
        date_pattern="yyyy/mm/dd",
        firstweekday="sunday",
        on_select=_commit,
    )
    cal.pack(padx=10, pady=10)

    # footer
    btns = ttk.Frame(win)
    btns.pack(pady=(0, 10))
    win.deiconify()

    return win
