# Copyright (C) 2026 Cabinet Office, Japan, All rights reserved.
# Copyright (C) 2026 Lighthouse Technology & Consulting Co. Ltd., All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause
"""Adapter/facade for building and executing madocalib (rnx2rtkp) commands.

Encapsulates
------------
- Validation (reads from ViewModel interface)
- .bat generation (Windows-only; all paths quoted to tolerate spaces)
- Async execution and progress reporting (console encoding cp932)

Notes
-----
This file reduces GUI coupling to enable maintainable testing.
Threading:
    The batch execution runs in a background thread and reports progress
    to the UI via `ui.eventbus`.
Encoding:
    Subprocess streams are read using codepage `cp932` on Windows.

"""

import logging
import os
import re
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import messagebox
from typing import List

import constants as g
from core import runtime
from services.settings_service import AppSettings
from ui.eventbus import post
from utils.l6_patterns import find_l6e_patterns

logger = logging.getLogger(__name__)


@dataclass
class ValidatedInputs:
    """Validated user inputs collected from the GUI.

    Attributes:
        obs (str): Absolute path to the RINEX OBS file.
        nav (str): Absolute path to the RINEX NAV file.
        l6e_dir (str): Directory that contains L6E files.
        l6d_dir (str | None): Optional directory for **L6D** files.
        solution (str): Output solution path or a filename hint.
        interval (int): Processing interval in seconds (`>= 1`).
        ts (datetime): Start time of processing.
        te (datetime): End time of processing.
        tspan (int | None): Optional time-span window in seconds.
        tshift (int | None): Optional window shift in seconds.
        patterns_sat_l6e (list[str]): L6E file-name patterns to append.
        patterns_sat_l6d (List[str] | None): Optional L6D file-name patterns.

    """

    obs: str
    nav: str
    l6e_dir: str
    l6d_dir: str | None
    solution: str
    interval: int
    ts: datetime
    te: datetime
    tspan: int | None
    tshift: int | None
    patterns_sat_l6e: List[str]
    patterns_sat_l6d: List[str] | None


@dataclass
class CommandSpec:
    """Specification to run `rnx2rtkp` via a generated batch file.

    Attributes:
        bin_rnx2rtkp (str): Absolute path to `rnx2rtkp.exe`.
        bat_path (str): Absolute path to the generated `.bat` file.
        conf_path (str): Absolute path to the active `.conf` file.
        run_option (str): Execution mode: `"once"` or `"interval"`.
        out_folder (Path | None: Output directory for interval mode.
        out_file (str): Solution file path or filename pattern.

    """

    bin_rnx2rtkp: str
    bat_path: str
    conf_path: str
    run_option: str  # "once" | "interval"
    out_folder: Path | None
    out_file: str


class ConfigAccessor:
    """Provide access to configuration paths via `core.runtime`.

    This indirection keeps a single source of truth and decouples
    the runner from the runtime module.
    """

    def __init__(self, settings: AppSettings) -> None:
        """Bind settings accessor used to resolve configuration paths."""
        self.settings = settings

    def get_conf_path(self) -> str:
        """Return the active .conf path resolved by runtime."""
        # Delegate to runtime.get_conf_path() to avoid policy drift.
        return runtime.get_conf_path()


class Validator:
    """Validate inputs from the ViewModel-like `variables_main` object.

    Expected attributes (from existing GUI)
    ---------------------------------------
    - hcombo_file_rinex_obs/nav_path/folder_l6e/folder_l6d : Entry-like (get())
    - entry_start_date/start_time/end_date/end_time, combo_interval/timespan/spanshift :
      Entry/Combobox-like (get())
    - patterns_sat_l6e, patterns_sat_l6d : list[str]
    - get_solution_path() : returns str
    """

    def __init__(self, cfg_accessor: ConfigAccessor) -> None:
        """Initialize validator with a configuration accessor."""
        self.conf = cfg_accessor

    def validate(self, variables_main) -> ValidatedInputs:
        """Validate and normalize GUI inputs.

        Args:
            variables_main: ViewModel-like object exposing Entry/Combobox getters
                and L6 pattern lists.

        Returns:
            ValidatedInputs: Normalized inputs (paths, time range, interval,
            optional span/shift, L6 patterns).

        Raises:
            ValueError: If OBS/NAV/L6E are missing or malformed, or when
                date/time / interval is invalid.

        """
        rnx_obs = variables_main.hcombo_file_rinex_obs.get()
        rnx_nav = variables_main.hcombo_file_rinex_nav.get()
        l6e_folder = variables_main.hcombo_folder_l6e.get()
        L6d_folder = variables_main.hcombo_folder_l6d.get()
        solution = variables_main.get_solution_path()

        # Simple RINEX filename checks (retained for legacy compatibility).
        def _rinex_obs_ok(p: str) -> bool:
            if len(p) <= 3:
                return False
            return p.endswith(("obs", "rnx")) or p[-1].lower() == "o"

        def _rinex_nav_ok(p: str) -> bool:
            if len(p) <= 3:
                return False
            if p.endswith(("rnx", "nav")):
                return True
            s = p[-3:]
            return (
                len(s) == 3
                and s[0].isdigit()
                and s[1].isdigit()
                and s[2].lower() in ("g", "l", "n", "q")
            )

        if not Path(rnx_obs).is_file() or not _rinex_obs_ok(rnx_obs):
            raise ValueError("No such OBS file")
        if not Path(rnx_nav).is_file() or not _rinex_nav_ok(rnx_nav):
            raise ValueError("No such NAV file")
        patterns_l6e_now = find_l6e_patterns(l6e_folder)
        variables_main.patterns_sat_l6e = patterns_l6e_now or None
        if not variables_main.patterns_sat_l6e:
            raise ValueError("No such L6E files")

        # Datetime range
        try:
            dt_s = (
                f"{variables_main.entry_start_date.get()}"
                f" {variables_main.entry_start_time.get()}"
            )
            dt_e = (
                f"{variables_main.entry_end_date.get()}"
                f" {variables_main.entry_end_time.get()}"
            )
            ts = datetime.strptime(dt_s, "%Y/%m/%d %H:%M:%S")
            te = datetime.strptime(dt_e, "%Y/%m/%d %H:%M:%S")
            variables_main.progress_start_dt = ts
            variables_main.progress_end_dt = te
        except ValueError as e:
            raise ValueError("Error Start/End Date") from e

        # Interval seconds
        try:
            interval_int = int(variables_main.combo_interval.get())
            if interval_int < 1:
                raise ValueError()
        except Exception as e:
            raise ValueError("Error Interval") from e

        # Optional span/shift
        try:
            tspan = int(variables_main.combo_timespan.get())
        except Exception:
            tspan = None
        try:
            tshift = int(variables_main.combo_spanshift.get())
        except Exception:
            tshift = None

        patterns_sat_l6e = list(variables_main.patterns_sat_l6e or [])
        patterns_sat_l6d = (
            list(variables_main.patterns_sat_l6d)
            if getattr(variables_main, "patterns_sat_l6d", None)
            else None
        )

        return ValidatedInputs(
            obs=rnx_obs,
            nav=rnx_nav,
            l6e_dir=l6e_folder,
            l6d_dir=L6d_folder or None,
            solution=solution,
            interval=interval_int,
            ts=ts,
            te=te,
            tspan=tspan,
            tshift=tshift,
            patterns_sat_l6e=patterns_sat_l6e,
            patterns_sat_l6d=patterns_sat_l6d,
        )


class BatBuilder:
    """Generate a Windows .bat file to execute rnx2rtkp with given inputs.

    Notes
    -----
    - All paths are quoted to tolerate spaces.

    """

    def __init__(self, cfg_accessor: ConfigAccessor) -> None:
        """Initialize batch builder with configuration accessor."""
        self.conf = cfg_accessor

    @staticmethod
    def quote_path(p: str | Path) -> str:
        """Return an absolute Windows path wrapped in double quotes."""
        # Always resolve to an absolute path and wrap it in double quotes.
        s = str(Path(p).resolve())
        return f'"{s}"'

    def build(self, vin: ValidatedInputs) -> CommandSpec:
        """Build a Windows batch file that executes rnx2rtkp.

        Args:
            vin (ValidatedInputs): Pre-validated input set.

        Returns:
            CommandSpec: Paths and runtime options for execution.

        Raises:
            FileNotFoundError: If rnx2rtkp.exe is missing.

        Notes:
            All paths are quoted to tolerate spaces.
            Outputs vary depending on 'interval' mode.

        """
        bin_rnx2rtkp = runtime.get_rnx2rtkp_path()
        if not bin_rnx2rtkp:
            raise FileNotFoundError(f'No such "{g.PATH_BIN_RNX2RTKP}"')

        bat_path = runtime.get_bat_path()
        conf = self.conf.get_conf_path()

        run_option = (
            "interval"
            if (
                vin.tspan is not None
                and vin.tspan > vin.interval
                and (vin.te - vin.ts).total_seconds() > vin.tspan
            )
            else "once"
        )

        out_folder: Path | None = None
        with open(bat_path, "w", encoding="cp932", errors="ignore") as bat:
            bat.write("@echo off\n")
            bat.write(f"set BIN={self.quote_path(bin_rnx2rtkp)}\n")
            bat.write(f"set TS=-ts {vin.ts.strftime('%Y/%m/%d %H:%M:%S')}\n")
            bat.write(f"set TE=-te {vin.te.strftime('%Y/%m/%d %H:%M:%S')}\n")
            bat.write(f"set TI=-ti {vin.interval}\n")
            bat.write(f"set CONF={self.quote_path(conf)}\n")
            bat.write(f"set OBS={self.quote_path(vin.obs)}\n")
            bat.write(f"set NAV={self.quote_path(vin.nav)}\n")

            # L6E patterns
            arg_l6e = ""
            n = 1
            for pattern in vin.patterns_sat_l6e:
                temp_path = Path(vin.l6e_dir) / pattern
                bat.write(f"set L6E{n}={self.quote_path(temp_path)}\n")
                arg_l6e += f" %L6E{n}%"
                n += 1

            # L6D patterns (optional) ? built identically to L6E when present.
            arg_l6d = ""
            if vin.l6d_dir and vin.patterns_sat_l6d:
                n = 1
                for pattern in vin.patterns_sat_l6d:
                    temp_path = os.path.join(vin.l6d_dir, pattern)
                    bat.write(f"set L6D{n}={self.quote_path(temp_path)}\n")
                    arg_l6d += f" %L6D{n}%"
                    n += 1

            if run_option == "interval":
                # Build rolling/windowed spans and loop them in the batch
                sol_path = Path(vin.solution)
                out_folder = sol_path.parent / "result_exec"
                new_files = "%%Y%%m%%d%%h%%M%%S.pos"
                out = out_folder / new_files
                bat.write(f"set OUT_FILE={self.quote_path(out)}\n")

                # --- Build spans in Python (match legacy behavior) ---
                # Effective shift: if missing or <1, use tspan itself.
                ti = int(vin.interval)
                tspan = int(vin.tspan)  # interval mode implies this is not None
                tshift = (
                    int(vin.tshift) if vin.tshift and int(vin.tshift) > 0 else tspan
                )

                def _fmt(dt: datetime) -> str:
                    # yyyy/MM/dd HH:mm:ss (madocalib expects this)
                    return dt.strftime("%Y/%m/%d %H:%M:%S")

                run_spans = []
                cur = vin.ts
                while cur <= vin.te:
                    end = cur + timedelta(seconds=(tspan - ti))
                    if end >= vin.te:
                        end = vin.te
                    run_spans.append((_fmt(cur), _fmt(end)))
                    cur = cur + timedelta(seconds=tshift)
                    if cur >= vin.te:
                        break

                # --- Emit variables and loop in batch ---
                bat.write("setlocal enabledelayedexpansion\n")
                for i, (s, e) in enumerate(run_spans):
                    bat.write(f'set "START_{i}={s}"\n')
                    bat.write(f'set "END_{i}={e}"\n')
                bat.write(f'set "N={len(run_spans)-1}"\n')
                bat.write("for /l %%X in (0,1,%N%) do (\n")
                bat.write('  call set "START_CUR=%%START_%%X%%"\n')
                bat.write('  call set "END_CUR=%%END_%%X%%"\n')
                bat.write(
                    f"  %BIN% -ts !START_CUR! -te !END_CUR! %TI% -k %CONF% %OBS% %NAV%"
                    f"{arg_l6e}{arg_l6d} -o %OUT_FILE%\n"
                )
                bat.write(")\n")

            else:
                bat.write(f"set OUT={self.quote_path(Path(vin.solution))}\n")
                bat.write(
                    f"%BIN% %TS% %TE% %TI% -k %CONF% %OBS% %NAV%"
                    f"{arg_l6e}{arg_l6d} -o %OUT%\n"
                )

        return CommandSpec(
            bin_rnx2rtkp=str(bin_rnx2rtkp),
            bat_path=str(bat_path),
            conf_path=str(conf),
            run_option=run_option,
            out_folder=out_folder,
            out_file=Path(vin.solution).resolve(),
        )


class ProgressParser:
    """Parse rnx2rtkp stderr lines and compute progress percentage.

    Notes:
        Matches `processing:` or `reading:` lines followed by
        `YYYY/MM/DD hh:mm:ss` and converts them to `datetime`.

    """

    # Use a single pattern with a non-capturing alternation.
    _re = re.compile(
        r"^(?:processing|reading)\s*:\s*"
        r"(?P<y>\d{4})/(?P<m>\d{2})/(?P<d>\d{2})\s+"
        r"(?P<H>\d{2}):(?P<M>\d{2}):(?P<S>\d{2})"
    )

    @classmethod
    def parse(cls, line: str) -> datetime | None:
        """Return `datetime` extracted from a stderr line, or `None`.

        Args:
            line (str): A single stderr line.

        Returns:
            datetime | None: Parsed timestamp or `None` if not matched.

        """
        m = cls._re.search(line)
        if not m:
            return None
        return datetime(
            int(m["y"]), int(m["m"]), int(m["d"]), int(m["H"]), int(m["M"]), int(m["S"])
        )

    @staticmethod
    def to_percent(current: datetime, start: datetime, end: datetime) -> int:
        """Compute progress percentage given current, start, and end times.

        Args:
            current (datetime): Current timestamp from stderr.
            start (datetime): Start time of processing.
            end (datetime): End time of processing.

        Returns:
            int: Percentage in 0..100.

        """
        total = (end - start).total_seconds()
        if total <= 0:
            return 0
        elapsed = (current - start).total_seconds()
        return int(max(0.0, min(1.0, elapsed / total)) * 100)


class AsyncExecutor:
    """Run the .bat file asynchronously and post progress to the UI event bus."""

    def __init__(self, encoding="cp932") -> None:
        """Prepare async runner with target console encoding."""
        self.encoding = encoding

    def run(
        self,
        variables_main,
        bat_path: str,
        start_dt: datetime | None,
        end_dt: datetime | None,
    ) -> None:
        """Run a batch file asynchronously and post progress to the UI bus.

        Args:
            variables_main: UI variables used for locking and status updates.
            bat_path (str): Path to the batch file.
            start_dt (datetime | None): Progress start time;
                                           `None` to show spinner only.
            end_dt (datetime | None): Progress end time;
                                         `None` to show spinner only.

        Notes:
            Uses `cp932` to read stdout/stderr. Emits `ui_lock`/`ui_unlock`
            and `set_progress`/`reset_progress` events.

        """

        def task() -> None:
            proc = None
            stdout_buf, stderr_buf = [], []
            last_percent = None
            try:
                post("ui_lock")
                post("set_progress", percent=None, text="processing...")

                proc = subprocess.Popen(
                    bat_path,
                    shell=True,
                    text=True,
                    bufsize=1,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    encoding=self.encoding,
                    errors="replace",
                )

                def read_stdout() -> None:
                    try:
                        if not proc or not proc.stdout:
                            return
                        for line in iter(proc.stdout.readline, ""):
                            stdout_buf.append(line)
                            logger.info(line.rstrip("\n"))
                    except Exception as e:
                        logger.error("stdout reader error: %s", e)
                    finally:
                        try:
                            if proc and proc.stdout:
                                proc.stdout.close()
                        except Exception as e:
                            logger.debug("stdout close failed: %r", e)

                def read_stderr() -> None:
                    nonlocal last_percent
                    try:
                        if not proc or not proc.stderr:
                            return
                        for line in iter(proc.stderr.readline, ""):
                            stderr_buf.append(line)
                            logger.info(line.rstrip("\n"))
                            dt = ProgressParser.parse(line)
                            if not dt:
                                continue
                            if start_dt is None or end_dt is None:
                                post("set_progress", percent=None, text=line.strip())
                            else:
                                p = ProgressParser.to_percent(dt, start_dt, end_dt)
                                if last_percent is None or p != last_percent:
                                    last_percent = p
                                    post(
                                        "set_progress",
                                        percent=p,
                                        text=f"{line.strip()} {p}%",
                                    )
                    except Exception as e:
                        logger.error("stderr reader error: %s", e)
                    finally:
                        try:
                            if proc and proc.stderr:
                                proc.stderr.close()
                        except Exception as e:
                            logger.debug("stderr close failed: %r", e)

                thread_stdout = threading.Thread(target=read_stdout, daemon=True)
                thread_stderr = threading.Thread(target=read_stderr, daemon=True)
                thread_stdout.start()
                thread_stderr.start()
                rc = proc.wait()
                thread_stdout.join()
                thread_stderr.join()

                all_stderr = "".join(stderr_buf)
                if rc == 0:
                    if start_dt is not None and end_dt is not None:
                        post("set_progress", percent=100, text="100%")
                    post("reset_progress")
                    post("message", level="info", text="Done!", clear_after=0)
                else:
                    post("reset_progress")
                    post(
                        "message",
                        level="error",
                        text=f"madocalib: {all_stderr}",
                        clear_after=10000,
                    )
                    logger.error("madocalib failed rc=%s, bat=%s", rc, bat_path)
                    logger.error("stderr(last4KB): %s", all_stderr[-4096:])
            finally:
                post("ui_unlock")

        threading.Thread(target=task, daemon=True).start()


class MadocalibRunner:
    """Public facade used by GUI code to validate, build, and execute runs."""

    def __init__(self, settings: AppSettings) -> None:
        """Compose runner components (validator/builder/executor)."""
        self.cfg_accessor = ConfigAccessor(settings)
        self.validator = Validator(self.cfg_accessor)
        self.builder = BatBuilder(self.cfg_accessor)
        self.executor = AsyncExecutor(encoding="cp932")

    def execute(self, main_window, variables_main) -> None:
        """Validate inputs, build command, confirm overwrites, and execute."""
        try:
            inputs = self.validator.validate(variables_main)
            cmd_spec = self.builder.build(inputs)

            # Overwrite confirmation
            if cmd_spec.run_option == "interval":
                if cmd_spec.out_folder and cmd_spec.out_folder.exists():
                    if not messagebox.askokcancel(
                        "Confirm",
                        f"The folder already exists. Overwrite? {cmd_spec.out_folder}",
                        parent=main_window,
                    ):
                        post("message", level="info", text="Ready", clear_after=0)
                        return
            else:
                if Path(inputs.solution).exists():
                    if not messagebox.askokcancel(
                        "Confirm",
                        f"The file already exists. Overwrite? {inputs.solution}",
                        parent=main_window,
                    ):
                        post("message", level="info", text="Ready", clear_after=0)
                        return

        except Exception as e:
            post("message", level="error", text=str(e), clear_after=0)
            return

        # Execute asynchronously
        self.executor.run(variables_main, cmd_spec.bat_path, inputs.ts, inputs.te)
